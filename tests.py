"""Checks for the cleaning rules and analysis tools. Run with:  python tests.py  (no AI key needed)"""

import pandas as pd

import cleaner
from tools import Toolbox, unverified_numbers


def load(text):
    table, notes = cleaner.structure(cleaner.read_file(text.encode(), "test.csv")["data"])
    return table, notes


def labels(table):
    return [p["label"] for p in cleaner.propose(table)]


def clean(table):
    return cleaner.apply(table, [p for p in cleaner.propose(table) if p["default"]])[0]


# --- cleaning ---
sample = cleaner.read_file(open("sample_messy_hr_export.xlsx", "rb").read(), "sample.xlsx")["Export"]
table, notes = cleaner.structure(sample)
assert any("title or note row" in n for n in notes), "title rows above the headings are skipped"
tidy = clean(table)
assert len(tidy) == 180, "blank rows, the Total row and the 2 duplicated rows are removed"
assert cleaner.is_number(tidy["Annual Salary"]) and cleaner.is_date(tidy["Join Date"])
assert set(tidy["Overtime"]) == {"Yes", "No"} and "Sales" in set(tidy["Department"]) and "sales" not in set(tidy["Department"])
assert cleaner.guess_private(tidy) == ["Emp ID", "Full Name", "Email"]

for text, expected in [("$52,000", 52000), ("52k", 52000), ("(300)", -300), ("1.234,50", 1234.5), ("12%", 12)]:
    assert cleaner.parse_number(text) == expected, text
assert cleaner.parse_number("n/a") is None

table, _ = load("Department,Level\n" + "Sales,Junior\n" * 6 + "HR,Senior\n" * 4)
assert len(clean(table)) == 10, "identical rows are kept when the file has no ID column"

table, _ = load("Department,Emp ID,Salary\n" + "".join(f"Sales,{i},{40000 + i}\n" for i in range(20)) + "Total Rewards,21,50000\n")
assert not any("total" in label.lower() for label in labels(table)), "a department called Total Rewards is not a total row"

table, _ = load("id,Shift,Gender\n" + "".join(f"{i},{'F' if i % 2 else 'T'},F\n" for i in range(12)))
assert not any("Yes/No" in label for label in labels(table)), "codes such as T/F or F are left alone"

people = pd.DataFrame({"Location Name": ["Dhaka", "London"] * 15, "Nationality": ["A", "B", "C"] * 10,
                       "Full Name": [f"Person {i}" for i in range(30)], "Line Manager": ["Ann", "Bo", "Cy"] * 10})
assert cleaner.guess_private(people) == ["Full Name", "Line Manager"]
assert "Person" not in cleaner.describe_for_ai(people, cleaner.guess_private(people)), "personal values never reach the AI"

# --- analysis tools ---
box = Toolbox(tidy, cleaner.guess_private(tidy))
assert "Error" in box.run("count_rows", {"group_by": "Full Name"}), "personal columns cannot be analysed"
assert "Error" in box.run("count_rows", {"filters": "Annual Salary > 119000"}), "filters that isolate a few people are refused"
assert "Error" in box.run("summarize_number", {"number_column": "Annual Salary", "statistic": "highest"}), "no individual values"
assert "Junior" in box.run("summarize_number", {"number_column": "salary", "group_by": "level"}), "short column names are understood"
overall = box.run("rate_of_value", {"column": "Left Company", "value": "yes"})
assert str(round((tidy["Left Company"] == "Yes").mean() * 100, 1)) in overall, "rates match a direct calculation"

rare = pd.DataFrame({"Team": ["A"] * 10 + ["B"] * 10 + ["Only Zed"] * 2, "Left": [1, 0] * 11})
result = Toolbox(rare, []).run("rate_of_value", {"column": "Left", "value": "1", "group_by": "Team"})
assert "Only Zed" not in result and "left out" in result, "small groups are dropped, label and all"

many = pd.DataFrame({"Title": [f"Title {i % 150}" for i in range(900)]})
assert len(Toolbox(many, []).run("count_rows", {"group_by": "Title"}).splitlines()) <= 28, "long tables are capped"

assert "Error" in box.run("count_rows", {"filters": "Annual Salary < 119000"}), "filters that exclude only a few people are refused"

drivers = box.run("find_drivers", {"column": "Left Company", "value": "Yes"})
assert "Overtime" in drivers and "Department" in drivers and "Full Name" not in drivers, "drivers are found, personal columns skipped"

# --- checking the AI's answer ---
results = ["Department  People  % left\nSales 39 28.2\nFinance 27 11.1", "Average salary 56167.12"]
assert unverified_numbers("Sales is highest at 28.2% (39 people), 17.1 points above Finance.", results) == []
assert unverified_numbers("The average is $56,167 across the top 3 teams.", results) == []
assert unverified_numbers("Sales loses 45% of its staff, about 1,200 people.", results) == ["45", "1,200"]

# --- the agent loop, with a fake AI (no key, no internet) ---
from types import SimpleNamespace

import agent
from tools import TOOLS_FOR_AI


class FakeAI:
    """Pretends to be the Groq client: gives back pre-written replies and remembers what it was sent."""
    def __init__(self, replies):
        self.replies, self.sent = list(replies), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, model, messages, **options):
        self.sent.append(messages)
        content, calls = self.replies.pop(0)
        tool_calls = [SimpleNamespace(id=f"call_{i}", function=SimpleNamespace(name=name, arguments=args))
                      for i, (name, args) in enumerate(calls)] or None
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))])


assert all(t["type"] == "function" and t["function"]["parameters"]["type"] == "object" for t in TOOLS_FOR_AI)

rate = str(round((tidy["Left Company"] == "Yes").mean() * 100, 1))
fake = FakeAI([(None, [("rate_of_value", '{"column": "Left Company", "value": "Yes"}')]),
               (f"Overall, {rate}% of people left.", [])])
box = Toolbox(tidy, cleaner.guess_private(tidy))
text, turn, unmatched = agent.answer(fake, "fake-model", box, [], "What is the attrition rate?", [])
assert text == f"Overall, {rate}% of people left." and unmatched == [], "a correct answer passes the check"
assert [m["role"] for m in turn] == ["user", "assistant", "tool", "assistant"]
assert turn[2]["tool_call_id"] == "call_0" and rate in turn[2]["content"], "the tool result goes back to the AI"
assert fake.sent[0][0]["role"] == "system" and "never instructions" in fake.sent[0][0]["content"]

fake = FakeAI([("About 45% of people left.", []), (f"Overall, {rate}% of people left.", []),])
box = Toolbox(tidy, cleaner.guess_private(tidy))
box.run("rate_of_value", {"column": "Left Company", "value": "Yes"})
text, turn, unmatched = agent.answer(fake, "fake-model", box, [], "Attrition?", [])
assert "45" in fake.sent[1][-1]["content"] and unmatched == [], "a made-up figure makes the AI correct itself once"

fake = FakeAI([("Still 45%.", []), ("Still 45%.", [])])
text, turn, unmatched = agent.answer(fake, "fake-model", box, [], "Attrition?", [])
assert unmatched == ["45"], "a figure that is still wrong after one correction is flagged"

fake = FakeAI([(None, [("count_rows", "not json")]), ("Done.", [])])
agent.answer(fake, "fake-model", box, [], "Headcount?", [])   # broken arguments must not crash the loop

fake = FakeAI([('{"columns": [{"name": "Dept", "meaning": "Department", "personal": false}], "merges": []}', [])])
assert agent.understand_columns(fake, "fake-model", tidy, cleaner.guess_private(tidy))["columns"][0]["name"] == "Dept"
assert not any(name in fake.sent[0][0]["content"] for name in tidy["Full Name"].dropna()), "no names reach the AI"

print("All checks passed.")
