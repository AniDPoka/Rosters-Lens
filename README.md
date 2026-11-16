# HR Data Agent

Upload an HR spreadsheet, even a messy one. The agent cleans it, shows every change for approval, and then answers questions about it in plain English.

**Live app:** (paste your Streamlit link here)

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
- Any chart from an answer can be pinned to the dashboard.
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
- AI answers can be wrong. Check the "How I got this" panel before relying on a figure.
- Rates and averages for small groups are unreliable, and the small-group rule reduces but does not remove the chance of working out something about an individual by combining several questions.
- "Years since" columns count up to today, so for people who have left they are not length of service.
- The sample file is fictional.

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

## Built with

Python, Streamlit, Groq API (tool calling and JSON output, open-weight models), pandas, matplotlib
