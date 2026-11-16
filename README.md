# Roster Lens

Upload an HR spreadsheet, even a messy one. The agent cleans it, shows every change for approval, and then answers questions about it in plain English.

**Live app:** [roster-lens.streamlit.app](https://roster-lens.streamlit.app)

## What it does

**Stage 1: Clean**
- Finds the real table inside the sheet: skips title rows, blank rows, repeated headings, and "Total" rows.
- Converts text to proper numbers and dates, such as `$52,000`, `52k`, or `3 Mar 2021`.
- Makes labels consistent, such as `Y`/`yes` to `Yes`, or `sales`/`SALES` to `Sales`.
- On request, uses AI to explain what each column means and to suggest labels that mean the same thing, such as `HR` and `Human Resources`.
- Shows every proposed fix with a tick box. Nothing changes until the user approves it, and the original file is never modified.

**Stage 2: Ask**
- The user types a question, such as "Which department has the highest turnover?"
- An AI agent chooses from seven analysis tools (count, average, rate, trend, comparison, describe, and a driver scan), runs them, and explains the result.
- The driver scan answers "what is linked to people leaving?" by comparing every column and rating the evidence for each gap as strong, some, or weak.
- Every answer includes a "How I got this" panel with the steps taken and the exact figures used.

**Charts and dashboard**
- Answers that compare groups come with a chart: bars for comparisons, a line for trends over time. Each chart can be downloaded as a picture.
- A dashboard view builds itself from the cleaned data: headline numbers, headcount, outcome rate and averages by a chosen category, people per year, and the factors most linked to the chosen outcome. It uses no AI calls.
- Any chart from an answer can be pinned to the dashboard, and the "Add any chart" box makes a new chart from a plain request such as "average income by gender". The AI only chooses the calculation; pandas does it, with the same privacy rules.
- The interface uses a frosted-glass style in blue and white. The colours are set in `.streamlit/config.toml` and the styling is at the top of `app.py`.

## Design choices

- **Answers are checked.** Every figure in an answer is compared with the calculated results. If one cannot be traced, the agent is made to correct itself once, and anything still unmatched is flagged on screen.
- **Auditable.** A session report with every question, answer, and calculation can be downloaded.
- **The AI never does the maths.** All numbers are calculated by pandas code. The AI decides which calculation to run and explains the result.
- **Rules first, AI second.** Cleaning uses fixed rules so the same file always cleans the same way. AI is used only for judgement calls, and its suggestions are labelled.
- **Privacy by design.** Columns with names, emails, IDs, or managers are detected and withheld from the AI and from analysis. Nothing is sent to the AI until the user has checked that list and asks for suggestions or asks a question. Groups of fewer than five people are left out of results, label included, and filters that exclude only a few people are refused so they cannot be revealed by subtraction. The AI receives column names, example values from non-personal columns, and group-level results, never individual rows.
- **Cautious cleaning.** Fixes that could delete real people, such as removing identical rows from a file with no ID column, are offered unticked with a warning.
- **Honest about limits.** The agent is instructed to say when the data cannot answer a question, and to avoid claiming causes from patterns.

## Limits

- Works on Excel and CSV files containing one table per sheet. Heavily formatted reports with merged cells or several tables on one sheet may not be understood.
- The AI runs on Groq's free tier. Groq states that it does not train on what is sent, but the data still leaves the app, so use the public demo only with sample or non-confidential files. The free tier also has daily limits, so the demo may pause when they are used up.
- Uploaded files are never saved or shared: they stay in the visitor's own browser session and are gone when the page closes. The app sends no usage statistics.
- AI answers can be wrong. Check the "How I got this" panel before relying on a figure.
- Rates and averages for small groups are unreliable, and the small-group rule reduces but does not remove the chance of working out something about an individual by combining several questions.
- Without a leaving-date column, "Years since" columns count up to today, so for people who have left they are not length of service. With one, a "Years of service" column is offered that stops at the leaving date.
- The demo data is fictional (see below). Hire Date, Employee Name and Work Email were added for the demo.

## Demo data

The demo uses IBM's **HR Analytics Employee Attrition** dataset: 1,470 fictional employees created by IBM data
scientists, with 35 columns such as job role, overtime, income, satisfaction scores and whether the person left.
It is the same dataset widely shared on Kaggle. Source: [IBM/employee-attrition-aif360](https://github.com/IBM/employee-attrition-aif360)
(Apache License 2.0). The original file is kept unchanged in `data/ibm_hr_attrition.csv`.

Real HR exports are rarely clean, so `data/make_messy_sample.py` turns it into `ibm_hr_messy.xlsx`: title rows,
blank rows, a repeated heading, a Total row, duplicated people, salaries written as `$5,993` or `5,993 USD`,
Yes/No written five ways, and `R&D` next to `Research & Development`. It also adds made-up names and emails
(to show personal columns being withheld) and a hire date worked out from years at the company.

The mess is chosen so nothing real is lost. After the suggested fixes are approved, the data matches IBM's
original exactly: 1,470 people, 237 leavers (16.1%), and every salary. `tests.py` checks this.

What the agent finds in it, for example: Sales Representatives leave most often (39.8%, against 2.5% for
Research Directors), and people who work overtime leave at 30.5% against 10.4% for those who do not.

## Run it yourself

1. Fork this repository.
2. Create a free Groq API key at [console.groq.com/keys](https://console.groq.com/keys). No card is needed.
3. Deploy on [Streamlit Community Cloud](https://share.streamlit.io) with `app.py` as the main file, and add `GROQ_API_KEY = "your-key"` under the app's Secrets.

## How the code is organised

- `app.py`: the web page, charts and dashboard
- `agent.py`: the AI agent loop that picks tools and checks the answer
- `cleaner.py`: reading files, finding problems, applying approved fixes, detecting personal columns
- `.streamlit/config.toml`: the colour theme
- `tools.py`: the analysis tools the agent can call, with the privacy rules
- `tests.py`: checks for the cleaning rules, the tools and the agent loop. Run `python tests.py` (no AI key needed)
- `data/`: IBM's original data, the script that makes the messy demo file, and a small file used by the tests

## Built with

Python, Streamlit, Groq API (tool calling and JSON output, open-weight models), pandas, Altair
