"""HR Data Agent: upload a messy HR spreadsheet, approve the clean-up, then ask questions in plain English."""

import hashlib
import html
import io
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # draw charts without needing a screen
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

import agent
import cleaner
from agent import answer, understand_columns
from tools import ToolError, Toolbox

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

/* frosted glass panels: anything given a key that starts with "glass" */
[class*="st-key-glass"], [data-testid="stSidebar"], [data-testid="stExpander"] details, [data-testid="stChatMessage"] {
  background: linear-gradient(135deg, rgba(255,255,255,0.66), rgba(255,255,255,0.30));
  -webkit-backdrop-filter: blur(22px) saturate(170%);
  backdrop-filter: blur(22px) saturate(170%);
  border: 1px solid rgba(255,255,255,0.9);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.95), inset 0 -1px 0 rgba(31,95,214,0.06),
              0 22px 44px -24px rgba(20,49,92,0.30);
}
[class*="st-key-glass_chart"] { border-radius: 28px; padding: 1.25rem 1.4rem 1.1rem; }
[class*="st-key-glass_tile"]  { border-radius: 20px; padding: 0.9rem 1.2rem; }
[class*="st-key-glass_bar"]   { border-radius: 22px; padding: 0.9rem 1.2rem 1.1rem; }
[data-testid="stExpander"] details, [data-testid="stChatMessage"] { border-radius: 20px; }
[data-testid="stSidebar"] { border-width: 0 1px 0 0; box-shadow: none; }

[data-testid="stMetricLabel"] p { color: #5b7299; font-weight: 500; }
[data-testid="stMetricValue"] { font-weight: 600; letter-spacing: -0.02em; }
.chart-title { font-weight: 600; font-size: 1rem; margin: 0 0 0.35rem; }

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
[data-testid="stSelectbox"] [role="group"], [data-baseweb="select"] > div, [data-testid="stChatInput"] > div {
  background: rgba(255,255,255,0.66); border-radius: 14px; border-color: rgba(255,255,255,0.95);
}

/* the Ask questions / Dashboard switch becomes a pill with a sliding blue highlight */
.st-key-view [role="radiogroup"] {
  gap: 4px; padding: 4px; width: fit-content; border-radius: 999px; background: rgba(255,255,255,0.6);
  border: 1px solid rgba(255,255,255,0.95); box-shadow: 0 10px 22px -16px rgba(20,49,92,0.45);
}
.st-key-view [role="radiogroup"] label { margin: 0; padding: 6px 18px; border-radius: 999px; cursor: pointer; }
.st-key-view [data-testid="stRadioOption"] > div > div:not([data-testid="stMarkdownContainer"]) { display: none; }
.st-key-view [role="radiogroup"] label:has(input:checked) { background: #1f5fd6; }
.st-key-view [role="radiogroup"] label:has(input:checked) p { color: #ffffff; font-weight: 600; }
.st-key-view [role="radiogroup"] label:has(input:focus-visible) { outline: 2px solid #1f5fd6; outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) { .stButton > button, .stDownloadButton > button { transition: none; } }
</style>
"""
OUTCOME_WORDS = r"left|leav|attrit|terminat|resign|exit|churn|turnover"
GROUP_WORDS = r"department|dept|division|team|function"      # the dashboard opens on these if present
NUMBER_WORDS = r"salary|income|pay|wage|compensation"


st.set_page_config(page_title="HR Data Agent", page_icon="🧹", layout="wide")
state = st.session_state


# ---------- Talking to the AI ----------

def get_secret_key():
    try:
        return st.secrets.get("GROQ_API_KEY", "")
    except Exception:
        return ""


# Connect once per key and reuse it (Streamlit keeps the result between clicks)
connect = st.cache_resource(show_spinner=False)(agent.connect)


def build_report(chat, log):
    """A record of the whole session: what was cleaned, what was asked, and how each answer was worked out."""
    lines = ["# HR Data Agent session report", "", "## Cleaning applied"] + [f"- {entry}" for entry in log]
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
    groups = [c for c in groups if c not in flags]
    numbers = [c for c in usable if cleaner.is_number(table[c])]
    dates = [c for c in usable if cleaner.is_date(table[c])]
    questions = []
    if groups:
        questions.append(f"How many people are in each {groups[0]}?")
    if numbers and groups:
        questions.append(f"What is the average {numbers[0]} by {groups[0]}?")
    if flags and groups:
        questions.append(f"What share of people have {flags[-1]} = Yes, by {groups[0]}?")
    if flags:
        questions.append(f"What is most strongly linked to {flags[-1]} = Yes?")
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


# ---------- Charts ----------

def draw_chart(labels, values, kind, title=None):
    """Draws one chart: a line for trends over time, otherwise rounded bars with the values listed beside them."""
    with plt.rc_context({"text.color": INK, "xtick.color": MUTED, "ytick.color": INK, "font.size": 11}):
        if kind == "line":
            fig, ax = plt.subplots(figsize=(5.4, 2.9))
            positions = range(len(labels))
            ax.fill_between(positions, values, color=BLUE, alpha=0.10)
            ax.plot(positions, values, color=BLUE, linewidth=2.2, marker="o", markersize=5,
                    markerfacecolor="white", markeredgewidth=1.6)
            every = max(1, len(labels) // 10)
            ax.set_xticks(positions[::every], labels[::every], rotation=45 if len(labels) > 6 else 0)
            ax.set_ylim(bottom=0)
            ax.grid(axis="y", color=BLUE, alpha=0.12, linewidth=0.8)
        else:
            fig, ax = plt.subplots(figsize=(5.4, 0.38 * len(labels) + (1.0 if title else 0.5)))
            rows = list(range(len(labels) - 1, -1, -1))        # first group at the top
            longest = max(max(values), 0) or 1
            ax.hlines(rows, 0, longest, color=BLUE, alpha=0.10, linewidth=9, capstyle="round")   # faint track
            filled = [(row, value) for row, value in zip(rows, values) if value > 0]
            if filled:
                ax.hlines([r for r, _ in filled], 0, [v for _, v in filled], color=BLUE, linewidth=9, capstyle="round")
            for row, value in zip(rows, values):
                ax.text(longest * 1.05, row, f"{value:,.1f}".rstrip("0").rstrip("."), va="center", fontweight="bold")
            ax.set_xlim(0, longest * 1.24)
            ax.set_ylim(-0.7, len(labels) - 0.3)
            ax.set_yticks(rows, labels)
            ax.set_xticks([])
        ax.tick_params(length=0)
        for side in ax.spines.values():
            side.set_visible(False)
        if title:
            ax.set_title(title, loc="left", fontsize=12, fontweight="bold", pad=10)
        fig.tight_layout()
    return fig


@st.cache_data(show_spinner=False, max_entries=300)
def chart_pictures(labels, values, kind, title):
    """Returns two pictures of a chart: a see-through one for the screen and a white one, with its title, to download."""
    pictures = []
    for for_screen in (True, False):
        fig = draw_chart(labels, values, kind, None if for_screen else title)
        picture = io.BytesIO()
        fig.savefig(picture, format="png", dpi=160, bbox_inches="tight", transparent=for_screen,
                    facecolor="none" if for_screen else "white")
        plt.close(fig)
        pictures.append(picture.getvalue())
    return pictures


def show_chart(series, kind, title, key):
    """Shows a chart with its title and a button to download it as a picture."""
    labels = tuple(str(v)[:30] for v in series.index)
    values = tuple(float(v) for v in series.values)
    on_screen, to_download = chart_pictures(labels, values, kind, title)
    st.markdown(f'<p class="chart-title">{html.escape(title)}</p>', unsafe_allow_html=True)
    st.image(on_screen, width=620)   # never wider than this, so charts stay readable in the chat
    name = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:60] or "chart"
    st.download_button("Download chart", to_download, f"{name}.png", "image/png", key=f"png_{key}")


def show_exchange(item, number):
    with st.chat_message("user", avatar=":material/person:"):
        st.write(item["question"])
    with st.chat_message("assistant", avatar=":material/monitoring:"):
        st.markdown(item["answer"])
        if item["unverified"]:
            st.warning("Check before using: " + ", ".join(item["unverified"]) + " could not be matched to the "
                       "calculated results. Compare the answer with 'How I got this'.")
        elif item["steps"]:
            st.caption("✓ Every figure in this answer was matched to the calculated results.")
        charts = [s for s in item["steps"] if s["chart"] is not None and 2 <= len(s["chart"]) <= 30]
        if charts:
            step = charts[-1]
            title = f"{step['chart'].name} by {step['chart'].index.name}"
            show_chart(step["chart"], step.get("kind", "bar"), title, f"chat_{number}")
            if item.get("pinned"):
                st.caption("Pinned to the dashboard.")
            elif st.button("Pin to dashboard", key=f"pin_{number}"):
                state["pins"].append({"title": title, "chart": step["chart"], "kind": step.get("kind", "bar"),
                                      "question": item["question"], "note": step["note"]})
                item["pinned"] = True
                st.rerun()
        if item["steps"]:
            with st.expander("How I got this"):
                show_steps(item["steps"])


# ---------- Dashboard ----------

def dashboard_columns(table, private):
    """Sorts the usable columns into the roles a dashboard needs."""
    usable = [c for c in table.columns if c not in private]
    text = [c for c in usable if cleaner.is_text(table[c])]
    flags = [c for c in text if set(table[c].dropna().unique()) == {"Yes", "No"}]
    groups = [c for c in text if c not in flags and 2 <= table[c].nunique() <= 12]
    numbers = [c for c in usable if cleaner.is_number(table[c])]
    dates = [c for c in usable if cleaner.is_date(table[c])]
    return groups, flags, numbers, dates


def first_match(columns, words):
    """Position of the first column whose name contains one of the words, or 0 if none does."""
    return next((i for i, c in enumerate(columns) if re.search(words, c, re.I)), 0)


def show_dashboard(table, private, meanings):
    """An overview built from the data itself. It uses the same tools and privacy rules as the agent, and no AI."""
    groups, flags, numbers, dates = dashboard_columns(table, private)
    likely = [f for f in flags if re.search(OUTCOME_WORDS, f, re.I)]
    group = outcome = number = None
    controls = st.container(key="glass_bar").columns(3)
    if groups:
        group = controls[0].selectbox("Break down by", groups, index=first_match(groups, GROUP_WORDS))
    if flags:
        outcome = controls[1].selectbox("Outcome to track", flags, index=flags.index((likely or flags[-1:])[0]))
    if numbers:
        number = controls[2].selectbox("Number to average", numbers, index=first_match(numbers, NUMBER_WORDS))

    tiles = [("People", f"{len(table):,}")]
    if outcome:
        tiles.append((f"{outcome} = Yes", f"{(table[outcome].dropna() == 'Yes').mean() * 100:.1f}%"))
    if number:
        tiles.append((f"Average {number}", f"{table[number].mean():,.1f}"))
    if dates:
        tiles.append((f"Latest {dates[0]}", f"{table[dates[0]].max():%b %Y}"))
    for position, (column, (label, value)) in enumerate(zip(st.columns(len(tiles)), tiles)):
        column.container(key=f"glass_tile_{position}").metric(label, value)

    box, charts = Toolbox(table, private, meanings), []

    def add(calculate, title=None):
        try:
            calculate()
        except ToolError:
            return   # e.g. every group is too small to show
        step = box.steps[-1]
        if step["chart"] is not None and len(step["chart"]) >= 2:
            charts.append({"title": title or f"{step['chart'].name} by {step['chart'].index.name}",
                           "chart": step["chart"], "kind": step.get("kind", "bar"), "note": step["note"]})

    if group:
        add(lambda: box.count_rows(group_by=group))
    if group and outcome:
        add(lambda: box.rate_of_value(outcome, "Yes", group_by=group))
    if group and number:
        add(lambda: box.summarize_number(number, group_by=group))
    if dates:
        add(lambda: box.trend_over_time(dates[0]), f"People per year, by {dates[0]}")
    if outcome:
        add(lambda: box.find_drivers(outcome, "Yes"), f"Most linked to {outcome} = Yes (gap in % points)")

    if not charts and not state["pins"]:
        st.info("This file has no columns the dashboard can chart. It needs a category column such as department. "
                "You can still ask questions and pin their charts here.")
    columns = st.columns(2)
    for position, chart in enumerate(charts):
        with columns[position % 2].container(key=f"glass_chart_{position}"):
            show_chart(chart["chart"], chart["kind"], chart["title"], f"dash_{position}")
            if chart["note"]:
                st.caption(chart["note"])

    if state["pins"]:
        st.subheader("Pinned from your questions")
        columns = st.columns(2)
        for position, pin in enumerate(state["pins"]):
            with columns[position % 2].container(key=f"glass_chart_pin_{position}"):
                show_chart(pin["chart"], pin["kind"], pin["title"], f"pin_chart_{position}")
                st.caption(f"From: {pin['question']}" + (f" {pin['note']}" if pin["note"] else ""))
                if st.button("Remove", key=f"unpin_{position}"):
                    state["pins"].pop(position)
                    st.rerun()
    st.caption("Groups of fewer than 5 people are left out of every chart. Charts show patterns, not causes.")


# ---------- Page ----------

st.markdown(STYLE, unsafe_allow_html=True)
st.title("HR Data Agent")
st.write("Upload an HR spreadsheet, even a messy one. The agent cleans it, shows you every change "
         "for approval, and then answers your questions about it in plain English.")

with st.sidebar:
    st.header("Settings")
    own_key = st.text_input("Your own Groq API key (optional)", type="password",
                            help="Use your own key if the shared one is busy, or for non-sample data.")
    st.caption("**Privacy.** Calculations run inside this app. Nothing is sent to the AI until you ask "
               "it for suggestions or ask a question. It then receives column names, example values from "
               "columns you have not marked personal, and group-level results. Groups of fewer than 5 "
               "people are left out. The AI runs on Groq, which says it does not train on what is sent. "
               "The data still leaves this app, so use the public demo only with sample or "
               "non-confidential files.")
    if st.button("Start over"):
        state.clear()
        st.rerun()

api_key = own_key.strip() or get_secret_key()

SAMPLE_LABEL = "Try the messy IBM sample (1,470 employees)"
source = st.radio("Data", [SAMPLE_LABEL, "Upload my own file"], horizontal=True)
if source == SAMPLE_LABEL:
    file_bytes, file_name = SAMPLE.read_bytes(), SAMPLE.name
else:
    upload = st.file_uploader("Excel or CSV file", type=["xlsx", "csv", "tsv", "txt"])
    if upload is None:
        st.stop()
    if upload.size > MAX_FILE_MB * 1024 * 1024:
        st.error(f"That file is larger than {MAX_FILE_MB} MB. Remove unneeded sheets or columns and try again.")
        st.stop()
    file_bytes, file_name = upload.getvalue(), upload.name

try:
    sheets = cleaner.read_file(file_bytes, file_name)
except Exception:
    st.error("That file could not be opened. Save it as .xlsx or .csv and try again.")
    st.stop()
if not sheets:
    st.error("That file has no data in it.")
    st.stop()
sheet = st.selectbox("Which sheet?", list(sheets)) if len(sheets) > 1 else list(sheets)[0]

# A new file or sheet resets everything that was worked out for the previous one
file_id = hashlib.md5(file_bytes).hexdigest() + str(sheet)
if state.get("file_id") != file_id:
    for key in list(state.keys()):
        del state[key]
    try:
        base, notes = cleaner.structure(sheets[sheet])
    except ValueError as error:
        st.error(str(error))
        st.stop()
    except Exception:
        st.error("This sheet's layout could not be understood. It needs one table with a row of column headings.")
        st.stop()
    if len(base) > MAX_ROWS:
        notes.append(f"The file has {len(base):,} rows. This demo uses the first {MAX_ROWS:,}.")
        base = base.head(MAX_ROWS)
    proposals = cleaner.propose(base)
    preview, _ = cleaner.apply(base, [p for p in proposals if p["default"]])
    guess = [c for c in cleaner.guess_private(preview) if c in base.columns]
    state.update(file_id=file_id, base=base, notes=notes, proposals=proposals, meanings={}, stage="clean",
                 private_guess=guess, ai_note="", ai_done=False, chat=[], history=[])


# ---------- Stage 1: review the clean-up ----------

if state["stage"] == "clean":
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
            state["ai_note"] = (f"The AI added {added} suggestion(s) to the list below and marked {flagged} more "
                                "column(s) as personal. Check them before applying.")
        except Exception:
            state["ai_note"] = ("The AI is unavailable right now (the free allowance may be used up). "
                                "The rule-based clean-up below still works, and you can try again in a minute.")

    st.header("Step 1: Review the clean-up")
    with st.expander("See the file as uploaded"):
        st.dataframe(sheets[sheet].head(12).astype(str), hide_index=True)

    st.subheader("Fixed automatically")
    for note in state["notes"] or ["Nothing needed fixing in the file's layout."]:
        st.markdown(f"- {note}")

    st.subheader("Personal columns")
    private = st.multiselect(
        "These columns are never sent to the AI or used in analysis. Check this list first, and add any "
        "column that could identify a person.", list(state["base"].columns), key="private_cols")

    st.subheader("Suggested fixes")
    if state["ai_note"]:
        st.info(state["ai_note"])
    if not state["ai_done"]:
        if st.button("Ask the AI for more suggestions", disabled=not api_key):
            state["run_ai"] = True
            st.rerun()
        st.caption("Optional. Sends the column names and example values from columns not marked personal above. "
                   "The AI explains what each column means and spots labels that mean the same thing, such as "
                   "'HR' and 'Human Resources'." + ("" if api_key else " Needs a Groq API key in the sidebar."))
    if not state["proposals"]:
        st.write("No fixes are suggested.")
    ticked, chosen, now_ticked = state.get("ticked", {}), [], {}
    for number, proposal in enumerate(state["proposals"]):
        label = proposal["label"] + ("  ·  AI suggestion, please check" if proposal["source"] == "ai" else "")
        now_ticked[number] = st.checkbox(label, value=ticked.get(number, proposal["default"]), key=f"fix_{number}")
        if now_ticked[number]:
            chosen.append(proposal)
        st.caption(proposal["detail"])

    if st.button("Apply and continue", type="primary"):
        clean, log = cleaner.apply(state["base"], chosen)
        # earlier answers were worked out on the previous version of the data, so the chat starts again
        state.update(clean=clean, log=state["notes"] + log, private=list(private), ticked=now_ticked,
                     stage="ask", chat=[], history=[], pins=[])
        st.rerun()
    st.stop()


# ---------- Stage 2: ask questions ----------

clean, private = state["clean"], state["private"]
st.header("Step 2: Explore your data")
a, b, c = st.columns(3)
a.metric("Rows", f"{len(clean):,}")
b.metric("Columns", len(clean.columns))
c.metric("Fixes applied", len(state["log"]))

with st.expander("What was cleaned"):
    for line in state["log"] or ["Nothing needed cleaning."]:
        st.markdown(f"- {line}")
    st.download_button("Download cleaned data (CSV)", clean.to_csv(index=False).encode("utf-8"),
                       "cleaned_data.csv", "text/csv")
    st.download_button("Download cleaning log", "\n".join(state["log"]), "cleaning_log.txt")
with st.expander("Columns in the cleaned data"):
    st.dataframe(column_summary(clean, private, state["meanings"]), hide_index=True)
if st.button("Back to clean-up"):
    state["stage"] = "clean"
    st.rerun()

state.setdefault("pins", [])
view = st.radio("View", ["Ask questions", "Dashboard"], horizontal=True, key="view", label_visibility="collapsed")
if view == "Dashboard":
    show_dashboard(clean, private, state["meanings"])
    st.stop()

for number, item in enumerate(state["chat"]):
    show_exchange(item, number)

if state["chat"]:
    st.download_button("Download session report", build_report(state["chat"], state["log"]), "session_report.md")

question = st.chat_input("Ask a question, e.g. Which department has the highest turnover?")
if not state["chat"]:
    st.caption("Or try one of these:")
    for number, suggestion in enumerate(suggest_questions(clean, private)):
        if st.button(suggestion, key=f"suggestion_{number}"):
            question = suggestion

if question:
    if not api_key:
        st.error("No AI key is set up. Paste a Groq API key in the sidebar.")
        st.stop()
    if len(state["chat"]) >= MAX_QUESTIONS:
        st.warning("This session has reached its question limit. Click 'Start over' in the sidebar.")
        st.stop()
    toolbox = Toolbox(clean, private, state["meanings"])
    try:
        with st.spinner("Working on it..."):
            client, model = connect(api_key)
            recent = [content for turn in state["history"][-3:] for content in turn]
            earlier = [text for item in state["chat"][-3:] for text in item["outputs"]]
            text, turn, unmatched = answer(client, model, toolbox, recent, question[:500], earlier)
    except Exception:
        st.error("The AI is unavailable right now (the free allowance may be used up). "
                 "Wait a minute and try again, or paste your own key in the sidebar.")
        st.stop()
    state["history"].append(turn)
    state["chat"].append({"question": question, "answer": text, "steps": toolbox.steps,
                          "outputs": toolbox.outputs, "unverified": unmatched, "pinned": False})
    st.rerun()
