"""Roster Lens: upload a messy HR spreadsheet, approve the clean-up, then ask questions in plain English."""

import hashlib
import html
import re
import textwrap
import time
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import agent
import cleaner
from agent import answer, make_chart, understand_columns
from tools import MIN_GROUP, ToolError, Toolbox

SAMPLE = Path(__file__).parent / "ibm_hr_messy.xlsx"   # IBM's HR data, made messy by data/make_messy_sample.py
MAX_FILE_MB = 10
MAX_ROWS = 20000
MAX_QUESTIONS = 30
INK, BLUE, MUTED = "#14315c", "#1f5fd6", "#5b7299"   # the whole look uses these three colours plus white

# The "liquid glass" look: soft blue light behind the page, and see-through frosted panels on top of it.
STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&display=swap');

.stApp {
  background:
    radial-gradient(820px 600px at 8% -6%, #a8c6ff 0%, transparent 62%),
    radial-gradient(700px 560px at 100% 18%, #c3d8ff 0%, transparent 60%),
    radial-gradient(760px 620px at 30% 62%, #d3e3ff 0%, transparent 62%),
    radial-gradient(980px 720px at 78% 104%, #9dbfff 0%, transparent 60%),
    #f3f8ff;
  background-attachment: fixed;
}
.stApp, .stApp p, .stApp label, .stApp li, .stApp h1, .stApp h2, .stApp h3, .stApp button, .stApp input,
.stApp textarea, [data-testid="stMetricValue"], [data-testid="stMetricLabel"] {
  font-family: 'Manrope', 'Segoe UI', system-ui, sans-serif !important;
  color: #14315c;
}
.stApp h1 { font-weight: 700; letter-spacing: -0.02em; }
.stApp h2, .stApp h3 { font-weight: 600; letter-spacing: -0.01em; }
[data-testid="stHeader"], [data-testid="stBottom"], [data-testid="stBottom"] > div { background: transparent; }
[data-testid="stChatMessageAvatarCustom"], [data-testid="stChatMessage"] [data-testid*="Avatar"] { background: #1f5fd6; color: #ffffff; }
[data-testid="stChatMessage"] [data-testid*="Avatar"] * { color: #ffffff; }
[data-testid="stCaptionContainer"] p { color: #5b7299; }

/* frosted glass panels: anything given a key that starts with "glass".
   The blur sits on a separate layer behind the panel (::before). If it were on the panel itself, the
   browser would trap a chart's full-screen view inside the panel, so full screen would not work. */
[class*="st-key-glass"], [data-testid="stSidebar"], [data-testid="stExpander"] details, [data-testid="stChatMessage"] {
  position: relative;
  isolation: isolate;
  border: 1px solid rgba(255,255,255,0.9);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.95), inset 0 -1px 0 rgba(31,95,214,0.06),
              0 22px 44px -24px rgba(20,49,92,0.30);
}
[class*="st-key-glass"]::before, [data-testid="stSidebar"]::before, [data-testid="stExpander"] details::before,
[data-testid="stChatMessage"]::before {
  content: ""; position: absolute; inset: 0; z-index: -1; border-radius: inherit; pointer-events: none;
  background: linear-gradient(135deg, rgba(255,255,255,0.66), rgba(255,255,255,0.30));
  -webkit-backdrop-filter: blur(22px) saturate(170%);
  backdrop-filter: blur(22px) saturate(170%);
}
/* while a chart is in full screen, lift its panel above every other panel */
[class*="st-key-glass"]:has(button[aria-label="Close fullscreen"]) { z-index: 1000060; }
[data-testid="stMetricLabel"] p { white-space: normal; overflow: visible; }

/* panel shapes */
[class*="st-key-glass_findings"] { border-radius: 24px; padding: 1.1rem 1.4rem 0.9rem; }
[class*="st-key-glass_chart"] { border-radius: 28px; padding: 1.25rem 1.4rem 1.1rem; }
[class*="st-key-glass_tile"]  { border-radius: 20px; padding: 0.9rem 1rem; }
[class*="st-key-glass_bar"]   { border-radius: 22px; padding: 0.9rem 1.2rem 1.1rem; }
[data-testid="stExpander"] details, [data-testid="stChatMessage"] { border-radius: 20px; }
[data-testid="stSidebar"] { border-width: 0 1px 0 0; box-shadow: none; }

/* headline numbers (KPI cards) */
[data-testid="stMetricLabel"] p { color: #5b7299; font-weight: 500; }
[data-testid="stMetricValue"] { font-weight: 600; letter-spacing: -0.02em; }
[class*="st-key-glass_tile"] [data-testid="stMetricValue"] { font-size: 1.7rem; }
[data-testid="stMetricValue"] > div { overflow: visible; text-overflow: clip; }
/* KPI cards share one row and only wrap onto a new row below 110px each (the wrapper is what sits in the row) */
[data-testid="stLayoutWrapper"]:has(> [class*="st-key-glass_tile"]) { flex: 1 1 0; min-width: 110px; }

.chart-title { font-weight: 700; font-size: 1.05rem; margin: 0 0 0.35rem; }
.block-container, [data-testid="stMainBlockContainer"] { padding-top: 2.5rem; }
.stApp h4 { font-family: 'Manrope', 'Segoe UI', system-ui, sans-serif !important; color: #14315c; font-weight: 700; }

/* buttons, menus and text boxes are small pieces of the same glass */
.stButton > button, .stDownloadButton > button {
  border-radius: 999px; border: 1px solid rgba(255,255,255,0.95); background: rgba(255,255,255,0.62);
  color: #1f5fd6; font-weight: 600; box-shadow: 0 8px 18px -12px rgba(20,49,92,0.45);
  transition: background 0.15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover { background: #ffffff; border-color: #ffffff; color: #1f5fd6; }
.stButton > button p, .stDownloadButton > button p { color: inherit; }
.stButton > button[kind="primary"] { background: #1f5fd6; border-color: #1f5fd6; color: #ffffff; }
.stButton > button[kind="primary"]:hover { background: #184fb8; border-color: #184fb8; color: #ffffff; }
.stApp button:focus-visible { outline: 2px solid #1f5fd6; outline-offset: 2px; }
[data-testid="stChatInput"] > div { background: rgba(255,255,255,0.66); border-radius: 14px; border-color: rgba(255,255,255,0.95); }
[class*="st-key-glass_pick"], [class*="st-key-glass_private"], [class*="st-key-glass_fixes"] {
  border-radius: 24px; padding: 1.2rem 1.4rem 1.1rem;
}
[class*="st-key-glass_pick"] h4 { padding-top: 0; }
[class*="st-key-glass_databar"] { border-radius: 18px; padding: 0.45rem 0.6rem 0.45rem 1.1rem; }
[class*="st-key-glass_databar"] p { margin: 0; }

/* buttons keep their words on one line; light (tertiary) buttons have no pill until hovered */
.stButton > button p, .stDownloadButton > button p, [data-testid="stPopover"] button p { white-space: nowrap; }
.stButton > button[kind="tertiary"] {
  background: transparent; border-color: transparent; box-shadow: none; padding: 0.3rem 0.75rem;
}
.stButton > button[kind="tertiary"]:hover { background: rgba(255,255,255,0.75); border-color: #ffffff; }
[data-testid="stPopover"] > div > button {
  border-radius: 999px; background: rgba(255,255,255,0.62); border: 1px solid rgba(255,255,255,0.95); color: #1f5fd6;
}
/* the chart toolbar keeps Show data (the chart as a table), Download as PNG and Fullscreen */
button[aria-label="Copy Vega-Lite spec"] { display: none; }

/* dropdowns are liquid glass: a frosted box that glows when hovered or open, an arrow that turns over,
   and a frosted list that drops down into place */
[data-baseweb="select"] > div {
  background: linear-gradient(135deg, rgba(255,255,255,0.82), rgba(255,255,255,0.40)) !important;
  -webkit-backdrop-filter: blur(14px) saturate(160%); backdrop-filter: blur(14px) saturate(160%);
  border: 1px solid rgba(255,255,255,0.95) !important; border-radius: 14px !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.95), 0 8px 20px -14px rgba(20,49,92,0.45);
  transition: background 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
}
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"] {
  background: linear-gradient(135deg, rgba(255,255,255,0.82), rgba(255,255,255,0.40)) !important;
  border-color: rgba(255,255,255,0.95) !important; border-radius: 14px !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.95); transition: box-shadow 0.25s ease, border-color 0.25s ease;
}
[data-baseweb="input"] input, [data-baseweb="base-input"] input { background: transparent !important; }
[data-baseweb="input"]:focus-within { border-color: rgba(31,95,214,0.45) !important;
  box-shadow: inset 0 1px 0 #ffffff, 0 0 0 4px rgba(31,95,214,0.12); }
[data-baseweb="select"] > div:hover {
  background: linear-gradient(135deg, rgba(255,255,255,0.95), rgba(255,255,255,0.60)) !important;
  box-shadow: inset 0 1px 0 #ffffff, 0 12px 26px -14px rgba(31,95,214,0.50);
}
[data-baseweb="select"]:has(input[aria-expanded="true"]) > div {
  border-color: rgba(31,95,214,0.45) !important;
  box-shadow: inset 0 1px 0 #ffffff, 0 0 0 4px rgba(31,95,214,0.12), 0 14px 30px -14px rgba(31,95,214,0.55);
}
[data-baseweb="select"] svg { transition: transform 0.3s ease; }
[data-baseweb="select"]:has(input[aria-expanded="true"]) svg { transform: rotate(180deg); }

/* the drop-down uses "translate" and "scale", not "transform": Streamlit positions the list with
   "transform", so animating that made the list start at the top of the screen and then jump */
@keyframes rl-drop { from { opacity: 0; translate: 0 -6px; scale: 0.98; } to { opacity: 1; translate: 0 0; scale: 1; } }
[data-baseweb="popover"] > div, [data-testid="stPopoverBody"], [data-testid="stSelectboxVirtualDropdown"] {
  background: linear-gradient(160deg, rgba(255,255,255,0.80), rgba(226,236,255,0.55)) !important;
  -webkit-backdrop-filter: blur(26px) saturate(180%); backdrop-filter: blur(26px) saturate(180%);
  border: 1px solid rgba(255,255,255,0.95); border-radius: 18px;
  box-shadow: inset 0 1px 0 #ffffff, 0 26px 50px -22px rgba(20,49,92,0.45);
  /* the 40ms pause keeps the list invisible while Streamlit moves it from the top of the page to its box */
  animation: rl-drop 0.2s ease 40ms backwards;
}
[data-baseweb="popover"] ul { background: transparent !important; padding: 4px; }
[data-testid="stSelectboxVirtualDropdown"] { padding: 4px; overflow: hidden; }
[data-testid="stSelectboxVirtualDropdown"] [role="listbox"] { background: transparent !important; }
[data-testid="stSelectboxVirtualDropdown"] [role="option"] {
  border-radius: 10px; color: #14315c; font-family: 'Manrope', 'Segoe UI', system-ui, sans-serif !important;
  transition: background 0.15s ease, padding-left 0.15s ease; }
[data-testid="stSelectboxVirtualDropdown"] [role="option"]:hover,
[data-testid="stSelectboxVirtualDropdown"] [role="option"][aria-selected="true"] {
  background: rgba(31,95,214,0.10) !important; padding-left: 1.1rem; }
[data-baseweb="popover"] li { background: transparent; border-radius: 10px; color: #14315c; margin: 1px 0;
  font-family: 'Manrope', 'Segoe UI', system-ui, sans-serif !important; transition: background 0.15s ease, padding-left 0.15s ease; }
[data-baseweb="popover"] li:hover, [data-baseweb="popover"] li[aria-selected="true"] {
  background: rgba(31,95,214,0.10); padding-left: 1.1rem; }

/* expandable sections open smoothly too */
[data-testid="stExpanderDetails"] { animation: rl-fade-up 0.3s ease backwards; }

/* the Dashboard / Ask questions tabs are a pill switch. Streamlit's own sliding underline
   (.react-aria-SelectionIndicator) is stretched into the blue pill, so the pill glides between tabs. */
[data-testid="stTabs"] [role="tablist"] {
  gap: 4px; padding: 4px; width: fit-content; border-radius: 999px; background: rgba(255,255,255,0.6);
  border: 1px solid rgba(255,255,255,0.95); box-shadow: 0 10px 22px -16px rgba(20,49,92,0.45); margin-bottom: 0.6rem;
}
[data-testid="stTabs"] [role="tab"] {
  position: relative; isolation: isolate; padding: 6px 18px; border-radius: 999px; height: auto; background: transparent;
}
[data-testid="stTabs"] [role="tab"] p { font-weight: 600; color: #14315c; transition: color 0.3s ease; }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] p { color: #ffffff; }
[data-testid="stTabs"] .react-aria-SelectionIndicator {
  top: 0; bottom: 0; height: 100% !important; border-radius: 999px; background: #1f5fd6 !important; z-index: -1;
  transition: translate 0.4s cubic-bezier(0.65, 0, 0.35, 1), width 0.4s cubic-bezier(0.65, 0, 0.35, 1) !important;
}

/* gentle motion: tab contents and new panels fade up into place instead of popping in.
   "backwards" means the animation leaves no style behind when it ends: a leftover transform would
   trap a chart's full-screen view inside its panel. */
@keyframes rl-fade-up { from { opacity: 0; translate: 0 8px; } to { opacity: 1; translate: 0 0; } }
[data-testid="stTabs"] [role="tabpanel"] { animation: rl-fade-up 0.4s ease backwards; }
[class*="st-key-glass"] { animation: rl-fade-up 0.45s ease backwards; }
@media (prefers-reduced-motion: reduce) {
  [data-testid="stTabs"] [role="tabpanel"], [class*="st-key-glass"], [data-baseweb="popover"] > div,
  [data-testid="stSelectboxVirtualDropdown"],
  [data-testid="stPopoverBody"], [data-testid="stExpanderDetails"] { animation: none; }
  [data-testid="stTabs"] .react-aria-SelectionIndicator { transition: none !important; }
}
[data-testid="InputInstructions"] { display: none; }
/* while the page redraws, Streamlit greys out the old content; that flicker reads as a stutter, so it is
   turned off (the screen slot already clears old screens) */
[data-stale="true"], .stale-element { opacity: 1 !important; transition: none !important; }   /* the "Press Enter to submit" hint */
[class*="st-key-glass_maker"] { border-radius: 22px; padding: 0.9rem 1.2rem 0.6rem; }

@media (prefers-reduced-motion: reduce) { .stButton > button, .stDownloadButton > button { transition: none; } }
</style>
"""
OUTCOME_WORDS = r"left|leav|attrit|terminat|resign|exit|churn|turnover|ausgetreten|austritt|baja"
# values that mean someone has left, e.g. "Employment Status: Terminated"
LEAVE_VALUES = r"terminat|^left$|leaver|resign|^exit|inactive|former|separat|quit|dismiss|ausgetreten"
GROUP_WORDS = r"department|dept|division|team|function|abteilung|departamento|bereich"      # the dashboard opens on these if present
NUMBER_WORDS = r"salary|income|pay|wage|compensation|gehalt|lohn|salaire|salario|sueldo"
ROLE_WORDS = r"role|title|position"                   # the dashboard compares by these first
TENURE_WORDS = r"years at|tenure|service"                 # length of service, shown as a headline number


st.set_page_config(page_title="Roster Lens", page_icon="🔍", layout="wide")
state = st.session_state


# ---------- Talking to the AI ----------

def get_secret_key():
    try:
        return st.secrets.get("GROQ_API_KEY", "")
    except Exception:
        return ""


def connect(api_key):
    """Connects to the AI once per visit. The connection is kept in this visitor's session only,
    never in a cache shared between visitors."""
    fingerprint = hashlib.sha256(api_key.encode()).hexdigest()   # so the key itself is not stored
    if state.get("ai_for") != fingerprint:
        state["ai"], state["ai_for"] = agent.connect(api_key), fingerprint
    return state["ai"]


def build_report(chat, log):
    """A record of the whole session: what was cleaned, what was asked, and how each answer was worked out."""
    lines = ["# Roster Lens session report", "", "## Cleaning applied"] + [f"- {entry}" for entry in log]
    for number, item in enumerate(chat, 1):
        lines += ["", f"## Question {number}: {item['question']}", "", item["answer"], ""]
        if item["unverified"]:
            lines.append(f"WARNING: these figures could not be matched to the calculations: {', '.join(item['unverified'])}")
        for step in item["steps"]:
            arguments = ", ".join(f"{k}: {v}" for k, v in (step["arguments"] or {}).items() if v)
            lines.append(f"Calculation: {step['tool']} ({arguments})")
            if step["table"] is not None:
                lines += ["```", step["table"].to_string(index=False), "```"]
            if step["note"]:
                lines.append(step["note"])
    return "\n".join(lines)


# ---------- Small helpers ----------

def suggest_questions(table, private):
    """Starter questions built from the columns that are actually in the file."""
    usable = [c for c in table.columns if c not in private]
    groups = [c for c in usable if cleaner.is_text(table[c]) and 2 <= table[c].nunique() <= 12]
    flags = [c for c in groups if set(table[c].dropna().unique()) <= {"Yes", "No"}]
    groups = sorted((c for c in groups if c not in flags), key=lambda c: not re.search(GROUP_WORDS, c, re.I))
    numbers = sorted((c for c in usable if cleaner.is_number(table[c])), key=lambda c: not re.search(NUMBER_WORDS, c, re.I))
    dates = [c for c in usable if cleaner.is_date(table[c])]
    questions = []
    if groups:
        questions.append(f"How many people are in each {groups[0]}?")
    if numbers and groups:
        questions.append(f"What is the average {numbers[0]} by {groups[0]}?")
    flags = sorted(flags, key=lambda f: not re.search(OUTCOME_WORDS, f, re.I))     # attrition first
    if flags and groups:
        questions.append(f"What is the {rate_name(flags[0]).lower()} by {groups[0]}?")
    if flags:
        questions.append(f"What is most linked to {'people leaving' if re.search(OUTCOME_WORDS, flags[0], re.I) else flags[0]}?")
    if dates:
        questions.append(f"How many people per year, by {dates[0]}?")
    return questions[:4]


def column_summary(table, private, meanings):
    rows = []
    for col in table.columns:
        kind = "Date" if cleaner.is_date(table[col]) else "Number" if cleaner.is_number(table[col]) else "Text"
        rows.append({"Column": col, "Type": kind, "Meaning": meanings.get(col, ""),
                     "Blank (%)": round(table[col].isna().mean() * 100, 1),
                     "Used in analysis": "No (personal)" if col in private else "Yes"})
    return pd.DataFrame(rows)


def show_steps(steps):
    for number, step in enumerate(steps, 1):
        arguments = ", ".join(f"{k}: {v}" for k, v in (step["arguments"] or {}).items() if v)
        st.markdown(f"**Step {number}:** `{step['tool']}`" + (f" ({arguments})" if arguments else ""))
        if step["table"] is not None:
            st.dataframe(step["table"].astype(str), hide_index=True)
        if step["note"]:
            st.caption(step["note"])


# ---------- Friendly names ----------

def rate_name(column, value="Yes"):
    """What to call the share of people with a value: 'Attrition rate', or '% Over Time'."""
    if str(value).lower() != "yes":
        return "Attrition rate" if re.search(LEAVE_VALUES, str(value), re.I) else f"% {value}"
    if re.search(r"attrit|turnover|churn", column, re.I):
        return "Attrition rate"
    if re.search(OUTCOME_WORDS, column, re.I):
        return "Leaving rate"
    return f"% {column}"


def metric_name(series_name):
    """Turns a tool's column heading into a plain title, e.g. '% with Attrition = Yes' → 'Attrition rate'."""
    match = re.fullmatch(r"% with (.+) = (.+)", str(series_name))
    if match:
        column, value = match.groups()
        return rate_name(column) if value.lower() == "yes" else f"% {column}: {value}"
    return {"People": "Employees", "Gap (points)": "Gap (% points)"}.get(series_name, str(series_name))


def chart_title(series):
    if series.index.name == "Factor":
        return "What is most linked to the outcome"
    return f"{metric_name(series.name)} by {series.index.name}"


def short_note(note):
    """Keeps only the parts of a tool's note a dashboard reader needs (privacy and small groups)."""
    keep = [s.strip() for s in re.split(r"(?<=\.)\s+", note or "") if re.search(r"privacy|unreliable", s)]
    return " ".join(keep)


# ---------- Charts ----------

def safe_field(name):
    """Chart column names can't contain dots, brackets or quotes, so those are left out."""
    return re.sub(r"[.\[\]\\'\"]", "", str(name)).strip() or "Value"


def label_expression(field, series_name, biggest):
    """The text shown on each bar, worked out inside the chart, e.g. 39.8 → '39.8%'."""
    value = f"datum['{field}']"
    if str(series_name).startswith("%"):
        return f"format({value}, '.1f') + '%'"
    if "Gap" in str(series_name):
        return f"({value} >= 0 ? '+' : '') + format({value}, '.1f') + ' pts'"
    return f"format({value}, '{',.0f' if abs(biggest) >= 100 else ',.1f'}')"


def interactive_chart(series, kind, title, people=None, average=None, details=None):
    """An Altair chart in the app's colours: bars (or a line for trends), values on the bars, details on hover.
    The chart's own data uses plain column names, because "Show data" in its toolbar displays it as a table."""
    group = safe_field(series.index.name or "Group")
    value = safe_field(metric_name(series.name))
    if value == group:
        value = f"{value} (value)"
    frame = pd.DataFrame({group: [str(v)[:40] for v in series.index], value: [float(v) for v in series.values]})
    tooltip = [alt.Tooltip(field=group, type="nominal"), alt.Tooltip(field="shown", type="nominal", title=value)]
    if people is not None:
        frame["Employees"] = list(people)
        tooltip.append(alt.Tooltip(field="Employees", type="quantitative", format=","))
    if details is not None:
        frame["Details"] = list(details)
        tooltip.append(alt.Tooltip(field="Details", type="nominal"))
    font = "Manrope, Segoe UI, sans-serif"
    text = label_expression(value, series.name, frame[value].abs().max())
    base = alt.Chart(frame).transform_calculate(shown=text)
    if kind == "line":
        base = base.encode(x=alt.X(field=group, type="ordinal", title=None, sort=None, axis=alt.Axis(labelAngle=0, labelOverlap=True)),
                           y=alt.Y(field=value, type="quantitative", title=None,
                                   axis=alt.Axis(grid=True, gridColor="#dbe6fb", domain=False, ticks=False, tickCount=4)),
                           tooltip=tooltip)
        chart = (base.mark_area(color=BLUE, opacity=0.12) + base.mark_line(color=BLUE, strokeWidth=2.5)
                 + base.mark_point(color=BLUE, fill="white", size=40, filled=True, strokeWidth=2)).properties(height=260)
    else:
        top = max(frame[value].max(), average or 0, 0) or 1
        bottom = min(frame[value].min(), 0)
        base = base.encode(
            y=alt.Y(field=group, type="nominal", sort=None, title=None, axis=alt.Axis(labelLimit=190, domain=False, ticks=False, labelPadding=8)),
            x=alt.X(field=value, type="quantitative", title=None, axis=None, scale=alt.Scale(domain=[bottom, top * 1.35])),
            tooltip=tooltip)
        bars = base.mark_bar(color=BLUE, cornerRadiusEnd=6, size=18)
        labels = base.mark_text(align="left", dx=6, color=INK, fontWeight=600, font=font).encode(text=alt.Text(field="shown", type="nominal"))
        chart = bars + labels
        if average is not None:
            line = alt.Chart(pd.DataFrame({value: [average]})).transform_calculate(shown=text)
            chart = chart + line.mark_rule(color=MUTED, strokeDash=[4, 4], strokeWidth=1.5).encode(
                x=alt.X(field=value, type="quantitative"), tooltip=[alt.Tooltip(field="shown", type="nominal", title="Company average")])
        chart = chart.properties(height=max(110, 34 * len(frame)))
    # the title is part of the chart, so it also appears in full screen and in the downloaded picture
    lines = textwrap.wrap(title, 26)   # long titles go onto two lines instead of being cut off
    chart = chart.properties(title=alt.Title(lines, anchor="start", fontSize=16, fontWeight=700, color=INK,
                                             font=font, offset=14),
                             padding={"left": 4, "top": 4, "bottom": 4, "right": 48})   # room for the last label
    return (chart.configure(background="transparent", font=font)
            .configure_view(stroke=None)
            .configure_axis(labelColor=INK, labelFontSize=12, labelFont=font))


def show_chart(series, kind, title, people=None, average=None, note="", details=None):
    """Shows one chart. Its toolbar (top right, on hover) has full screen and 'Download as PNG'."""
    st.altair_chart(interactive_chart(series, kind, title, people, average, details), theme=None, width="stretch")
    if note:
        st.caption(note)


def typed(text):
    """Gives the answer back a word at a time, so it appears as if being typed. The answer was already
    checked in full before this starts, so nothing unchecked is ever shown."""
    for word in re.split(r"(\s+)", text):
        yield word
        if word.strip():
            time.sleep(0.025)


def step_words(name, arguments):
    """A plain-English line for each calculation, shown while the AI works."""
    by = f" by {arguments['group_by']}" if arguments.get("group_by") else ""
    where = f" for {arguments['filters']}" if arguments.get("filters") else ""
    lines = {
        "describe_data": "Looking at the columns",
        "count_rows": f"Counting people{by}{where}",
        "summarize_number": f"Working out the {arguments.get('statistic') or 'average'} {arguments.get('number_column', '')}{by}{where}",
        "rate_of_value": f"Working out the {rate_name(arguments.get('column', '')).lower()}{by}{where}",
        "trend_over_time": f"Counting people per {arguments.get('period') or 'year'} by {arguments.get('date_column', '')}",
        "compare_two_numbers": f"Comparing {arguments.get('column_a', '')} and {arguments.get('column_b', '')}",
        "find_drivers": f"Scanning every column for links to {arguments.get('column', 'the outcome')}{where}",
    }
    return lines.get(name, "Calculating") + "…"


def show_exchange(item, number):
    with st.chat_message("user", avatar=":material/person:"):
        st.write(item["question"])
    with st.chat_message("assistant", avatar=":material/monitoring:"):
        st.markdown(item["answer"])
        show_answer_parts(item, number)


def show_answer_parts(item, number):
    """Everything under an answer's text: the check result, the chart, pinning, and how it was worked out."""
    if item["unverified"]:
        st.warning("Check before using: " + ", ".join(item["unverified"]) + " could not be matched to the "
                   "calculated results. Compare the answer with 'How I got this'.")
    elif item["steps"]:
        st.caption("✓ Every figure in this answer was matched to the calculated results.")
    charts = [s for s in item["steps"] if s["chart"] is not None and 2 <= len(s["chart"]) <= 30]
    if charts:
        step = charts[-1]
        title = chart_title(step["chart"])
        people = step["table"]["People"] if "People" in step["table"] and step["chart"].name != "People" else None
        show_chart(step["chart"], step.get("kind", "bar"), title, people)
        if item.get("pinned"):
            st.caption("Pinned to the dashboard.")
        else:
            def pin():
                state["pins"].append({"title": title, "chart": step["chart"], "kind": step.get("kind", "bar"),
                                      "question": item["question"], "people": people})
                item["pinned"] = True
            st.button("Pin to dashboard", key=f"pin_{number}", type="tertiary", icon=":material/push_pin:", on_click=pin)
    if item["steps"]:
        with st.expander("How I got this"):
            show_steps(item["steps"])


# ---------- Dashboard ----------

def show_chart_maker(table, private, meanings, scope=""):
    """A box where anyone can ask for any chart. The AI picks the calculation; pandas does it.

    `table` is the data the dashboard is showing, so a chart made while viewing one department covers
    only that department. `scope` (e.g. "Department: Sales") is added to the chart's title.
    """
    with st.container(key="glass_maker"):
        with st.form("chart_request", clear_on_submit=True, border=False):
            with st.container(horizontal=True, vertical_alignment="bottom"):
                request = st.text_input("Add any chart", placeholder="e.g. average income by gender, or hires per year")
                made = st.form_submit_button("Add chart", icon=":material/add_chart:", type="primary")
        if made and request.strip():
            if not api_key:
                st.warning("Charts on request need an AI key. Add one under Settings in the sidebar.")
            else:
                try:
                    with st.spinner("Making your chart..."):
                        client, model = connect(api_key)
                        step, message = make_chart(client, model, Toolbox(table, private, meanings), request[:200])
                except Exception:
                    step, message = None, "The AI is busy right now (the free allowance may be used up). Try again in a minute."
                if step is None:
                    st.warning(message)
                else:
                    table_used = step["table"]
                    people = table_used["People"] if "People" in table_used and step["chart"].name != "People" else None
                    title = chart_title(step["chart"]) + (f" ({scope})" if scope else "")
                    state["pins"].insert(0, {"title": title, "chart": step["chart"],
                                             "kind": step.get("kind", "bar"), "question": request, "people": people})
    if state["pins"]:
        st.markdown('<p class="chart-title">Your charts</p>', unsafe_allow_html=True)
        for position, pin in enumerate(state["pins"]):
            if position % 2 == 0:
                row = st.columns(2)
            with row[position % 2].container(key=f"glass_chart_pin_{position}"):
                show_chart(pin["chart"], pin["kind"], pin["title"], pin.get("people"), note=f"You asked: {pin['question']}")
                if st.button("Remove", key=f"unpin_{position}", type="tertiary", icon=":material/close:"):
                    state["pins"].pop(position)
                    st.rerun(scope="fragment")


def dashboard_columns(table, private):
    """Sorts the usable columns into the roles a dashboard needs.

    Outcomes are (column, value) pairs that can be counted as a rate: a Yes/No column ("Attrition = Yes"),
    a column such as "Intends to leave" with Yes among a few answers, or a two-value status column such
    as "Employment Status" whose values include one that means leaving ("Terminated").
    """
    usable = [c for c in table.columns if c not in private]
    text = [c for c in usable if cleaner.is_text(table[c])]
    outcomes = []
    for c in text:
        values = set(table[c].dropna().astype(str))
        leaving = [v for v in values if re.search(LEAVE_VALUES, v, re.I)]
        if "Yes" in values and 2 <= len(values) <= 4:
            outcomes.append((c, "Yes"))
        elif len(values) == 2 and len(leaving) == 1:
            outcomes.append((c, leaving[0]))
    # leaving-type outcomes first, so the dashboard opens on attrition when the file has it
    outcomes.sort(key=lambda o: not (re.search(OUTCOME_WORDS, o[0], re.I) or o[1] != "Yes"))
    used = {c for c, _ in outcomes}
    groups = [c for c in text if c not in used and 2 <= table[c].nunique() <= 12]
    numbers = [c for c in usable if cleaner.is_number(table[c])]
    dates = [c for c in usable if cleaner.is_date(table[c])]
    return groups, outcomes, numbers, dates


def first_match(columns, words, default=0):
    """Position of the first column whose name contains one of the words."""
    return next((i for i, c in enumerate(columns) if re.search(words, c, re.I)), default)


def tool_table(box, run):
    """Runs one analysis tool and returns its table, or None if the privacy rules or the data stop it."""
    try:
        run()
    except ToolError:
        return None
    return box.steps[-1]["table"]


def money_like(column):
    return bool(re.search(NUMBER_WORDS, column, re.I))


@st.fragment   # changing a filter redraws only the dashboard, not the whole page
def show_dashboard(table, private, meanings):
    """A dashboard built from the data itself. It uses the same tools and privacy rules as the agent, and no AI."""
    groups, outcomes, numbers, dates = dashboard_columns(table, private)
    if not groups:
        st.info("The dashboard needs a category column, such as Department. You can still ask questions.")
        return
    box = Toolbox(table, private, meanings)

    # --- the controls ---
    team_col = groups[first_match(groups, GROUP_WORDS)]
    others = [g for g in groups if g != team_col] or groups
    measures = sorted(numbers, key=lambda n: not money_like(n))                         # pay first
    counts = table[team_col].value_counts()
    teams = [t for t, n in counts.items() if n >= MIN_GROUP and len(table) - n >= MIN_GROUP]
    with st.container(key="glass_bar", horizontal=True, vertical_alignment="bottom"):
        team = st.selectbox(team_col, ["All"] + sorted(teams), width="stretch")
        compare = st.selectbox("Compare by", others, index=first_match(others, ROLE_WORDS), width="stretch")
        options = st.popover("Options", icon=":material/tune:")
    with options:
        outcome = st.selectbox("Outcome", outcomes, format_func=lambda o: f"{rate_name(*o)} ({o[0]})") if outcomes else None
        measure = st.selectbox("Average of", measures) if measures else None
    where = "" if team == "All" else f"{team_col} = {team}"
    filtered = table if not where else table[table[team_col] == team]
    tenure = next((n for n in numbers if re.search(TENURE_WORDS, n, re.I)), None)
    extra = next((o for o in outcomes if o != outcome), None)
    oc, ov = outcome or (None, None)          # e.g. ("Attrition", "Yes") or ("Employment Status", "Terminated")
    xc, xv = extra or (None, None)

    # --- headline numbers, compared with the whole company when one team is chosen ---
    def headline(run, everyone):
        here = tool_table(box, run)
        whole = tool_table(box, everyone) if where else None
        value = None if here is None else float(here.iloc[0, -1])
        gap = None if whole is None or value is None else value - float(whole.iloc[0, -1])
        return value, gap

    # each tile: (label, value, change, colour of the change, what the change is compared with)
    share = f"{len(filtered) / len(table) * 100:.0f}%" if where else None
    tiles = [("People", f"{len(filtered):,}", share, "off", "of all")]
    rate = None
    if outcome:
        rate, gap = headline(lambda: box.rate_of_value(oc, ov, filters=where), lambda: box.rate_of_value(oc, ov))
        if rate is not None:   # for attrition, higher is worse, so a rise shows in red
            tiles.append((rate_name(oc, ov), f"{rate:.1f}%", None if gap is None else f"{gap:+.1f} pts", "inverse", "vs all"))
    for column in dict.fromkeys(c for c in (measure, tenure) if c):     # pay, then years at the company
        value, gap = headline(lambda: box.summarize_number(column, filters=where), lambda: box.summarize_number(column))
        if value is not None:
            big = abs(value) >= 100
            tiles.append((f"Avg {column}", f"{value:,.0f}" if big else f"{value:,.1f}",
                          None if gap is None else (f"{gap:+,.0f}" if big else f"{gap:+.1f}"), "normal", "vs all"))
    if extra:
        value, gap = headline(lambda: box.rate_of_value(xc, xv, filters=where), lambda: box.rate_of_value(xc, xv))
        if value is not None:
            tiles.append((rate_name(xc, xv), f"{value:.1f}%", None if gap is None else f"{gap:+.1f} pts", "off", "vs all"))
    row = st.container(horizontal=True, wrap=True)          # cards move to a second row on narrow screens
    for position, (label, value, delta, colour, against) in enumerate(tiles):
        row.container(key=f"glass_tile_{position}", width="stretch").metric(
            label, value, delta, delta_color=colour, delta_arrow="off" if colour == "off" else "auto",
            delta_description=against if delta else None)

    # --- the calculations behind the charts and the key findings ---
    by_rate = tool_table(box, lambda: box.rate_of_value(oc, ov, group_by=compare, filters=where)) if outcome else None
    by_count = tool_table(box, lambda: box.count_rows(group_by=compare, filters=where))
    by_measure = tool_table(box, lambda: box.summarize_number(measure, group_by=compare, filters=where)) if measure else None
    drivers = tool_table(box, lambda: box.find_drivers(oc, ov, filters=where)) if outcome else None
    by_flag = tool_table(box, lambda: box.rate_of_value(oc, ov, group_by=xc, filters=where)) if outcome and extra and xv == "Yes" else None
    leave_col = next((d for d in dates if cleaner.LEAVE_DATE.search(d)), None)
    starts = [d for d in dates if d != leave_col]
    hire_col = next((d for d in starts if re.search(r"hire|join|start|eintritt", d, re.I)), starts[0] if starts else None)
    hires = tool_table(box, lambda: box.trend_over_time(hire_col, filters=where)) if hire_col else None
    leavers = tool_table(box, lambda: box.trend_over_time(leave_col, filters=where)) if leave_col else None
    notes = {step["tool"] + str(step["arguments"].get("group_by", "")): short_note(step["note"]) for step in box.steps}

    findings = []
    if by_rate is not None and len(by_rate) > 1 and rate:
        top = by_rate.iloc[0]
        findings.append(f"**{top[compare]}** has the highest {rate_name(oc, ov).lower()}: **{top.iloc[-1]:.1f}%**, "
                        f"against {rate:.1f}% across {team if where else 'the company'}.")
    if drivers is not None and len(drivers):
        first = drivers.iloc[0]
        high, low = (re.match(r"(.*) \(([\d.]+)%", first[c]) for c in ("Highest group", "Lowest group"))
        if high and low:
            findings.append(f"**{first['Factor']}** shows the biggest gap: {high.group(1)} {high.group(2)}% vs "
                            f"{low.group(1)} {low.group(2)}%.")
    if by_flag is not None and set(by_flag[xc]) >= {"Yes", "No"}:
        yes, no = (by_flag.set_index(xc).iloc[:, -1][v] for v in ("Yes", "No"))
        findings.append(f"People with **{xc}**: {yes:.1f}% {rate_name(oc, ov).lower()}, against {no:.1f}% for those without.")
    if by_measure is not None and len(by_measure) > 1:
        high, low = by_measure.iloc[0], by_measure.iloc[-1]
        shown = (lambda v: f"{v:,.0f}") if abs(high.iloc[-1]) >= 100 else (lambda v: f"{v:,.1f}")
        if shown(high.iloc[-1]) != shown(low.iloc[-1]):          # skip it when there is no real difference
            findings.append(f"Average {measure} ranges from {shown(low.iloc[-1])} ({low[compare]}) to "
                            f"**{shown(high.iloc[-1])}** ({high[compare]}).")
    # --- key findings, straight under the headline numbers ---
    if findings:
        with st.container(key="glass_findings"):
            st.markdown('<p class="chart-title">Key findings</p>', unsafe_allow_html=True)
            st.markdown("\n".join(f"{number}. {line}" for number, line in enumerate(findings, 1)))
            st.caption("Patterns, not proof of causes. Groups under 5 people are hidden.")

    # --- "Add any chart", and the charts people made, above the ready-made ones ---
    # new charts cover what the dashboard is showing: the chosen department, or everyone
    show_chart_maker(filtered, private, meanings, f"{team_col}: {team}" if where else "")

    # --- the ready-made charts, most important first ---
    charts = []
    if by_rate is not None and len(by_rate) > 1:
        charts.append((by_rate, f"{rate_name(oc, ov)} by {compare}", "bar", rate, notes.get("rate_of_value" + compare)))
    if drivers is not None and len(drivers) > 1:
        charts.append((drivers.head(6), f"What is most linked to {rate_name(oc, ov).lower()}", "drivers", None,
                       "Each bar is the gap between the group most likely and least likely to leave. Hover for details."))
        # the strongest links get their own charts, found automatically from the scan above
        strongest = [f for f in drivers["Factor"] if f not in (compare, team_col)][:2]
        for factor in strongest:
            data = tool_table(box, lambda: box.rate_of_value(oc, ov, group_by=factor, filters=where))
            if data is not None and len(data) > 1:
                charts.append((in_order(data), f"{rate_name(oc, ov)} by {factor}", "bar", rate,
                               f"Found automatically: one of the strongest links to {rate_name(oc, ov).lower()}."))
    if by_count is not None and len(by_count) > 1:
        charts.append((by_count, f"People by {compare}", "bar", None, notes.get("count_rows" + compare)))
    if by_measure is not None and len(by_measure) > 1:
        charts.append((by_measure, f"Average {measure} by {compare}", "bar", None, notes.get("summarize_number" + compare)))
    if hires is not None and len(hires) > 1:
        title = "Hires per year" if re.search(r"hire|join|start", hire_col, re.I) else f"People per year by {hire_col}"
        charts.append((hires, title, "line", None, notes.get("trend_over_time")))
    if leavers is not None and len(leavers) > 1:
        charts.append((leavers, "Leavers per year", "line", None, ""))

    for position, (data, title, kind, average, note) in enumerate(charts):
        if position % 2 == 0:
            row = st.columns(2)          # a new row every two charts, so the rows line up
        with row[position % 2].container(key=f"glass_chart_{position}"):
            if kind == "drivers":
                series = data.set_index("Factor")["Gap (points)"]
                series.name = "Gap (points)"
                details = [f"{h} vs {l}" for h, l in zip(data["Highest group"], data["Lowest group"])]
                show_chart(series, "bar", title, note=note, details=details)
            else:
                value = "People" if "Share (%)" in data else data.columns[-1]   # head counts, not shares
                series = data.set_index(data.columns[0])[value]
                people = data["People"] if value != "People" else None
                show_chart(series, kind, title, people, average, note or "")


def in_order(data):
    """Ranges such as '0 to 3', '3 to 5' are shown in number order; other groups keep their order."""
    starts = pd.to_numeric(data.iloc[:, 0].astype(str).str.split(" ").str[0], errors="coerce")
    return data.iloc[starts.argsort()] if starts.notna().all() else data


# ---------- Page ----------

PRIVACY_NOTE = "Your file is not saved or shared. The AI never sees names or single rows."
KEEP_ON_NEW_FILE = {"source", "file_bytes", "file_name", "file_label", "ai", "ai_for"}


def took_upload():
    """Runs when a file is uploaded: keeps its contents in this session only, in memory."""
    upload = state.get("upload")
    if upload is None:
        return
    if upload.size > MAX_FILE_MB * 1024 * 1024:
        state["upload_error"] = f"That file is larger than {MAX_FILE_MB} MB. Remove unneeded sheets or columns and try again."
        return
    state.update(source="upload", file_bytes=upload.getvalue(), file_name=upload.name, file_label=upload.name,
                 upload_error="")


def use_sample():
    # file_name must keep its .xlsx ending: the reader uses it to know how to open the file
    state.update(source="sample", file_bytes=SAMPLE.read_bytes(), file_name=SAMPLE.name,
                 file_label="Sample data (IBM, 1,470 employees)", upload_error="")


def start_over():
    """Forgets everything from this visit: the file, the clean-up, the questions and the AI connection."""
    state.clear()


st.markdown(STYLE, unsafe_allow_html=True)

with st.sidebar:
    st.header("Settings")
    with st.expander("Use your own AI key"):
        own_key = st.text_input("Groq API key", type="password", help="Free at console.groq.com/keys")
    st.caption(f":material/lock: {PRIVACY_NOTE}")
    st.button("Start over", icon=":material/restart_alt:", on_click=start_over)

api_key = own_key.strip() or get_secret_key()

# --- the welcome page: choose the data ---
LANDING_STYLE = """
<style>
/* the welcome page has no sidebar, and its content sits in the middle of the screen */
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] { display: none; }
[data-testid="stMainBlockContainer"] { max-width: 980px; padding-top: 9vh; }
.hero { text-align: center; margin-bottom: 2.2rem; }
.hero h1 { font-size: clamp(2.4rem, 6vw, 3.6rem); margin: 0 0 0.6rem; padding: 0; }
.hero p { color: #5b7299; font-size: 1.15rem; margin: 0 auto; max-width: 560px; }
@media (min-width: 640px) { [class*="st-key-glass_pick"] { min-height: 235px; } }   /* equal cards side by side */
.steps { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 2.2rem; }
.step { flex: 1 1 200px; padding: 0.9rem 1.1rem; border-radius: 18px; background: rgba(255,255,255,0.45);
        border: 1px solid rgba(255,255,255,0.85); }
.steps, .steps *, .privacy { font-family: 'Manrope', 'Segoe UI', system-ui, sans-serif !important; }
.step b { display: block; color: #1f5fd6; margin-bottom: 0.15rem; }
.step span { color: #5b7299; font-size: 0.92rem; line-height: 1.45; }
.privacy { text-align: center; color: #5b7299 !important; font-size: 0.92rem; margin-top: 1.4rem; }
</style>
"""

# The welcome page lives in one placeholder. Every other screen empties it straight away, so the
# welcome cards never linger on screen while the next screen is still being worked out.
page = st.empty()
if not state.get("source"):
    with page.container():
        st.markdown(LANDING_STYLE, unsafe_allow_html=True)
        st.markdown('<div class="hero"><h1>Roster Lens</h1><p>Clean a messy HR spreadsheet, explore it on a '
                    'dashboard, and ask questions in plain English.</p></div>', unsafe_allow_html=True)
        left, right = st.columns(2, gap="medium")
        with left.container(key="glass_pick_sample"):
            st.markdown("#### :material/dataset: Try the sample")
            st.caption("IBM's HR data: 1,470 employees, with real-world mess added to show the clean-up.")
            st.button("Use sample data", type="primary", icon=":material/arrow_forward:", on_click=use_sample)
        with right.container(key="glass_pick_upload"):
            st.markdown("#### :material/upload_file: Use your own file")
            st.caption(f"Excel or CSV, up to {MAX_FILE_MB} MB.")
            st.file_uploader("Your file", type=["xlsx", "csv", "tsv", "txt"], key="upload", on_change=took_upload,
                             label_visibility="collapsed")
        if state.get("upload_error"):
            st.error(state["upload_error"])
        st.markdown('<div class="steps">'
                    '<div class="step"><b>1. Clean</b><span>Approve each fix. Your file is never changed.</span></div>'
                    '<div class="step"><b>2. Explore</b><span>A dashboard with key numbers and findings.</span></div>'
                    '<div class="step"><b>3. Ask</b><span>Plain-English answers, every figure checked.</span></div>'
                    '</div><div class="privacy">🔒 Your file is not saved or shared. It stays in this browser tab '
                    'and is gone when you close it.</div>', unsafe_allow_html=True)
    st.stop()

page.empty()
st.title("Roster Lens")
file_bytes, file_name = state["file_bytes"], state["file_name"]
try:
    sheets = cleaner.read_file(file_bytes, file_name)
except Exception:
    st.error("That file could not be opened. Save it as .xlsx or .csv and try again.")
    st.button("Choose another file", on_click=start_over)
    st.stop()
if not sheets:
    st.error("That file has no data in it.")
    st.button("Choose another file", on_click=start_over)
    st.stop()

# the bar that shows which data is in use
with st.container(key="glass_databar", horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
    st.markdown(f":material/description: **{html.escape(state['file_label'])}**")
    names = list(sheets)
    biggest = max(range(len(names)), key=lambda i: sheets[names[i]].size)   # open the sheet with the most data
    sheet = (st.selectbox("Sheet", names, index=biggest, format_func=lambda n: f"Sheet: {n}",
                          label_visibility="collapsed", width=220) if len(names) > 1 else names[0])
    with st.container(horizontal=True, vertical_alignment="center", width="content", gap="small"):
        data_actions = st.container(horizontal=True, vertical_alignment="center", width="content", gap="small")
        st.button("Change data", icon=":material/swap_horiz:", on_click=start_over, type="tertiary")

# A new file or sheet resets everything that was worked out for the previous one
file_id = hashlib.md5(file_bytes).hexdigest() + str(sheet)
if state.get("file_id") != file_id:
    for key in [k for k in state.keys() if k not in KEEP_ON_NEW_FILE]:
        del state[key]
    try:
        with st.spinner("Reading your file..."):
            base, notes = cleaner.structure(sheets[sheet])
    except ValueError as error:
        st.error(str(error))
        st.stop()
    except Exception:
        st.error("This sheet's layout could not be understood. It needs one table with a row of column headings.")
        st.stop()
    if len(base) > MAX_ROWS:
        notes.append(f"The file has {len(base):,} rows. This app uses the first {MAX_ROWS:,}.")
        base = base.head(MAX_ROWS)
    proposals = cleaner.propose(base)
    preview, _ = cleaner.apply(base, [p for p in proposals if p["default"]])
    guess = [c for c in cleaner.guess_private(preview) if c in base.columns]
    state.update(file_id=file_id, base=base, notes=notes, proposals=proposals, meanings={}, stage="clean",
                 private_guess=guess, ai_note="", ai_done=False, chat=[], history=[])


# ---------- Stage 1: review the clean-up ----------

def show_own_fix():
    """Lets the user add a fix of their own, which then appears in the list like any other."""
    with st.expander("Add your own fix", icon=":material/add_circle:"):
        preview, _ = cleaner.apply(state["base"], [p for p in state["proposals"] if p["default"]])
        kind = st.selectbox("What to do", list(cleaner.USER_FIXES), format_func=cleaner.USER_FIXES.get, key="own_kind")
        column = st.selectbox("Column", list(state["base"].columns), key="own_column")
        old = new = ""
        values = preview[column].dropna().astype(str).value_counts().index[:60] if column in preview else []
        if kind in ("replace", "drop_where"):
            old = st.selectbox("Value", list(values), key="own_old") if len(values) else ""
        if kind in ("rename", "replace", "fill_blank"):
            new = st.text_input({"rename": "New name", "replace": "Replace with", "fill_blank": "Fill with"}[kind],
                                key="own_new")
        ready = kind == "drop_column" or (kind == "drop_where" and old) or new.strip()
        st.button("Add this fix", icon=":material/add:", disabled=not ready,
                  on_click=lambda: state["proposals"].append(cleaner.user_fix(kind, column, old, new.strip())))


def show_cleanup():
    """Screen 1: check the clean-up."""
    if "private_cols" not in state:
        state["private_cols"] = list(state.get("private", state["private_guess"]))

    # The AI is asked only after the user has checked the personal columns and clicked the button
    if state.pop("run_ai", False):
        withheld = list(state["private_cols"])
        try:
            with st.spinner("Asking the AI about the columns..."):
                client, model = connect(api_key)
                preview, _ = cleaner.apply(state["base"], [p for p in state["proposals"] if p["default"]])
                info = understand_columns(client, model, preview, withheld)
            added = flagged = 0
            for item in info.get("columns", []):
                if item.get("name") in preview.columns:
                    state["meanings"][item["name"]] = str(item.get("meaning", ""))[:80]
                    if item.get("personal") and item["name"] in state["base"].columns and item["name"] not in withheld:
                        withheld.append(item["name"])
                        flagged += 1
            for item in info.get("merges", []):
                extra = cleaner.merge_proposal(preview, item.get("column"), str(item.get("canonical", "")),
                                               [str(v) for v in item.get("variants", [])])
                if extra and extra["column"] not in withheld:
                    state["proposals"].append(extra)
                    added += 1
            state["private_cols"] = withheld
            state["ai_done"] = True
            state["ai_note"] = (f"The AI added {added} suggestion(s) and marked {flagged} more column(s) as personal. "
                                "Check them before applying.")
        except Exception:
            state["ai_note"] = ("The AI is busy right now (the free allowance may be used up). "
                                "The clean-up below still works. Try again in a minute.")

    st.subheader("Check the clean-up")
    st.caption("Nothing changes until you click Apply. Your original file is never changed.")

    with st.container(key="glass_private"):
        st.markdown("**:material/visibility_off: Kept private**")
        private = st.multiselect("Columns the AI and charts never use", list(state["base"].columns), key="private_cols",
                                 label_visibility="collapsed", placeholder="Add a column that could identify someone",
                                 help="Names, IDs and emails are found for you. Add any other column that could "
                                      "point to one person.")
        st.caption("Found for you. The AI and charts never use these columns.")

    with st.container(key="glass_fixes"):
        st.markdown("**:material/build: Suggested fixes**")
        if state["ai_note"]:
            st.info(state["ai_note"])
        if not state["proposals"]:
            st.write("No fixes are needed.")
        ticked = state.get("ticked", {})
        for number, proposal in enumerate(state["proposals"]):
            label = proposal["label"] + {"ai": "  ·  AI suggestion", "user": "  ·  your fix"}.get(proposal["source"], "")
            st.checkbox(label, value=ticked.get(number, proposal["default"]), key=f"fix_{number}", help=proposal["detail"])
        show_own_fix()
        if not state["ai_done"]:
            st.button("Find more with AI", icon=":material/auto_awesome:", disabled=not api_key, type="tertiary",
                      help="Finds labels that mean the same thing, like 'HR' and 'Human Resources'. "
                           "Sends column names and example values from non-personal columns only.",
                      on_click=lambda: state.update(run_ai=True))

    with st.expander(f"Already fixed automatically ({len(state['notes'])})"):
        for note in state["notes"] or ["Nothing needed fixing in the file's layout."]:
            st.markdown(f"- {note}")
    with st.expander("Original file (first 12 rows)"):
        st.dataframe(sheets[sheet].head(12).astype(str), hide_index=True)

    st.button("Apply and open dashboard", type="primary", icon=":material/arrow_forward:", on_click=apply_cleanup)


def apply_cleanup():
    """Runs when Apply is clicked (before the page redraws, so the switch happens in one step)."""
    ticked = {n: state.get(f"fix_{n}", p["default"]) for n, p in enumerate(state["proposals"])}
    chosen = [p for n, p in enumerate(state["proposals"]) if ticked[n]]
    clean, log = cleaner.apply(state["base"], chosen)
    # a renamed private column must stay private under its new name
    renames = {p["column"]: p["payload"]["new"].strip() for p in chosen if p["kind"] == "rename"}
    private = [renames.get(c, c) for c in state["private_cols"] if renames.get(c, c) in clean]
    # earlier answers were worked out on the previous version of the data, so the chat starts again
    state.update(clean=clean, log=state["notes"] + log, private=private, ticked=ticked,
                 stage="ask", chat=[], history=[], pins=[])


# ---------- Stage 2: dashboard and questions ----------

def show_workspace():
    """Screen 2: the dashboard and questions."""
    clean, private = state["clean"], state["private"]
    state.setdefault("pins", [])
    with data_actions:   # these two sit in the top bar, next to "Change data"
        with st.popover("Data details", icon=":material/table_view:"):
            st.markdown(f"**{len(clean):,} rows, {len(clean.columns)} columns.** Changes made:")
            for line in state["log"] or ["Nothing needed cleaning."]:
                st.markdown(f"- {line}")
            st.dataframe(column_summary(clean, private, state["meanings"]), hide_index=True)
            st.download_button("Download cleaned data (CSV)", clean.to_csv(index=False).encode("utf-8"),
                               "cleaned_data.csv", "text/csv")
        st.button("Edit clean-up", icon=":material/tune:", type="tertiary",
                  on_click=lambda: state.update(stage="clean"))
    # Tabs switch in the browser without re-running the app, so moving between them is instant
    dashboard_tab, questions_tab = st.tabs(["Dashboard", "Ask questions"], key="view_tabs")
    with dashboard_tab:
        show_dashboard(clean, private, state["meanings"])
    with questions_tab:
        show_questions(clean, private)


@st.fragment   # asking a question redraws only this tab
def show_questions(clean, private):
    for number, item in enumerate(state["chat"]):
        show_exchange(item, number)
    live = st.container()   # a new question and its answer go here: under the earlier ones, above the box
    if state["chat"]:
        st.download_button("Download session report", build_report(state["chat"], state["log"]), "session_report.md")

    question = st.chat_input("Ask a question, e.g. Which department has the highest turnover?")
    suggestions = st.empty()
    if not state["chat"]:
        with suggestions.container():
            st.caption("Or try one of these:")
            for number, suggestion in enumerate(suggest_questions(clean, private)):
                if st.button(suggestion, key=f"suggestion_{number}"):
                    question = suggestion
    if not question:
        return
    suggestions.empty()   # the starter questions go away as soon as one is asked
    if not api_key:
        st.error("No AI key is set up. Add one under Settings in the sidebar.")
        return
    if len(state["chat"]) >= MAX_QUESTIONS:
        st.warning("This session has reached its question limit. Click 'Start over' in the sidebar.")
        return
    toolbox = Toolbox(clean, private, state["meanings"])
    with live.chat_message("user", avatar=":material/person:"):
        st.write(question)
    try:
        with live.status("Thinking…", expanded=True) as progress:
            client, model = connect(api_key)
            recent = [content for turn in state["history"][-3:] for content in turn]
            earlier = [text for item in state["chat"][-3:] for text in item["outputs"]]
            text, turn, unmatched = answer(client, model, toolbox, recent, question[:500], earlier,
                                           on_step=lambda name, arguments: progress.write(step_words(name, arguments)))
            progress.update(label="Done" if unmatched else "Done. Every figure checked.", state="complete", expanded=False)
    except Exception:
        live.error("The AI is unavailable right now (the free allowance may be used up). "
                   "Wait a minute and try again, or paste your own key in the sidebar.")
        return
    state["history"].append(turn)
    # the checked answer types itself out, then its chart and details appear underneath in the same
    # message. Nothing above is redrawn, so the page does not jump.
    item = {"question": question, "answer": text, "steps": toolbox.steps, "outputs": toolbox.outputs,
            "unverified": unmatched, "pinned": False}
    state["chat"].append(item)
    with live.chat_message("assistant", avatar=":material/monitoring:"):
        st.write_stream(typed(text))
        show_answer_parts(item, len(state["chat"]) - 1)


# ---------- Which screen to show ----------
# Each screen has its own slot on the page. The other screen's slot is emptied first, so the old screen
# disappears at once instead of lingering next to the new one while it is being built.
cleanup_slot, workspace_slot = st.empty(), st.empty()
if state["stage"] == "clean":
    workspace_slot.empty()
    with cleanup_slot.container():
        show_cleanup()
else:
    cleanup_slot.empty()
    with workspace_slot.container():
        show_workspace()
