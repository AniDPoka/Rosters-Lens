"""Builds the demo file ibm_hr_messy.xlsx from IBM's clean HR attrition data.

Real HR exports are rarely clean, so this script adds the kinds of mess the app is built to fix:
title rows, blank rows, a repeated heading, a Total row, duplicated rows, placeholders like 'N/A',
money written as text, Yes/No written five ways, and the same department spelled differently.

Survey scores such as JobSatisfaction are stored by IBM as codes 1 to 4. A real HR export would show
the words, so they are written out using IBM's codebook (data/ibm_codebook.json), e.g. 1 = Low.

It also adds three columns that IBM's file does not have, so the demo shows more features:
- Employee Name and Work Email: made-up values, to show that personal columns are withheld.
- Hire Date: worked out from YearsAtCompany, so 'hires per year' can be shown.

The mess is chosen so that nothing real is lost: once the app's fixes are approved, every IBM figure
(1,470 people, 237 leavers, every salary and score) comes back exactly. tests.py checks this.

Run from the project folder:  .venv/bin/python data/make_messy_sample.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
SOURCE = HERE / "ibm_hr_attrition.csv"
OUTPUT = HERE.parent / "ibm_hr_messy.xlsx"
SNAPSHOT = pd.Timestamp("2025-12-31")   # the pretend date the export was taken

rng = np.random.default_rng(7)          # fixed seed, so the file comes out the same every time
people = pd.read_csv(SOURCE)
count = len(people)


def some(share):
    """Picks a random share of the rows (True/False for each row)."""
    return rng.random(count) < share


# --- extra columns ---
first = ["Aisha", "Ben", "Chen", "Dina", "Emre", "Farah", "Gabe", "Hana", "Ivan", "Jia", "Kofi", "Lena",
         "Maya", "Nikhil", "Omar", "Priya", "Quinn", "Rosa", "Sami", "Tara", "Uma", "Victor", "Wen", "Yusuf"]
last = ["Ahmed", "Brown", "Costa", "Das", "Evans", "Fischer", "Garcia", "Haddad", "Ito", "Jensen", "Khan",
        "Lopez", "Mensah", "Novak", "Okafor", "Patel", "Rossi", "Silva", "Tanaka", "Usman", "Weber", "Zhang"]
names = [f"{rng.choice(first)} {chr(65 + rng.integers(26))}. {rng.choice(last)}" for _ in range(count)]   # e.g. Aisha K. Ahmed
emails = [f"{n.lower().replace('. ', '.').replace(' ', '.')}{number}@example.com" for n, number in zip(names, people["EmployeeNumber"])]
emails = ["" if blank else e for e, blank in zip(emails, some(0.04))]     # a few missing emails

days_back = people["YearsAtCompany"] * 365 + rng.integers(0, 365, count)
hired = SNAPSHOT - pd.to_timedelta(days_back, unit="D")
hire_text = [d.strftime("%d %b %Y") if rng.random() < 0.6 else d.strftime("%Y-%m-%d") for d in hired]

# --- mess that a clean-up can undo without losing anything ---
income = people["MonthlyIncome"].astype(object)
styles = rng.random(count)
income[styles < 0.25] = [f"${v:,}" for v in people["MonthlyIncome"][styles < 0.25]]
income[(styles >= 0.25) & (styles < 0.40)] = [f"{v:,} USD" for v in people["MonthlyIncome"][(styles >= 0.25) & (styles < 0.40)]]


def messy_yes_no(column):
    yes_words, no_words = ["Y", "yes", "YES"], ["N", "no"]
    out = people[column].astype(object)
    for i in np.where(some(0.2))[0]:
        out[i] = rng.choice(yes_words if out[i] == "Yes" else no_words)
    return out


department = people["Department"].astype(object)
spelling = rng.random(count)
department[(department == "Research & Development") & (spelling < 0.10)] = "R&D"
department[(department == "Research & Development") & (spelling > 0.90)] = "research & development"
department[(department == "Sales") & (spelling < 0.10)] = "SALES"
department[(department == "Human Resources") & (spelling < 0.30)] = "HR"

over18 = people["Over18"].astype(object)
over18[some(0.03)] = "N/A"
over18[some(0.02)] = "-"

table = people.copy()
codebook = json.loads((HERE / "ibm_codebook.json").read_text())
for column, words in codebook.items():
    if column in table:
        table[column] = table[column].astype(str).map(words)    # 1 → "Low", 4 → "Very High"
table["MonthlyIncome"], table["Department"], table["Over18"] = income, department, over18
table["Attrition"], table["OverTime"] = messy_yes_no("Attrition"), messy_yes_no("OverTime")
table.insert(1, "Employee Name", names)
table.insert(2, "Work Email", emails)
table["Hire Date"] = hire_text
table = table[["EmployeeNumber"] + [c for c in table.columns if c != "EmployeeNumber"]]   # ID first

# --- layout mess: title rows, blank rows, a repeated heading, duplicates and a Total row ---
heading = list(table.columns)
rows = table.astype(object).values.tolist()
for i in [41, 518, 1203]:                       # three people exported twice
    rows.insert(i + 1, list(rows[i]))
blank = [""] * len(heading)
rows.insert(400, blank)
rows.insert(750, list(heading))                 # the heading repeated, like a page break
rows.insert(1100, blank)
total = [""] * len(heading)
total[0], total[heading.index("MonthlyIncome")] = "Total", int(people["MonthlyIncome"].sum())
sheet = [["IBM HR Analytics - Employee Export"] + [""] * (len(heading) - 1),
         [f"Exported {SNAPSHOT:%d %b %Y}. Confidential."] + [""] * (len(heading) - 1),
         blank, heading] + rows + [blank, total]

pd.DataFrame(sheet).to_excel(OUTPUT, sheet_name="Export", header=False, index=False)
print(f"Wrote {OUTPUT.name}: {len(sheet)} spreadsheet rows for {count} people.")
