"""Turns a messy spreadsheet into a clean table, and explains every change it makes."""

import csv
import io
import re

import pandas as pd

MISSING = {"", "n/a", "na", "n.a.", "-", "--", "null", "nan", "?", "#n/a", "not available"}
YES = {"y", "yes", "true"}
NO = {"n", "no", "false"}
MONTHS = r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
DATE_LIKE = re.compile(rf"(?:\d{{1,4}}[-/.]\d{{1,2}}[-/.]\d{{1,4}})|(?:{MONTHS})", re.I)
# column names that identify a person whatever they contain
ALWAYS_PERSONAL = re.compile(
    r"(e-?mail|phone|mobile|address|ssn|social sec|passport|national (id|ins)|\bnid\b|tax id|iban|bank"
    r"|account (no|num)|manager|supervisor|reports to|approver)", re.I)
NOT_PERSONAL = re.compile(r"(job|role|team|dept|department|level|grade|band|rating|score|type|status)", re.I)
ID_NAME = re.compile(r"(id|no|num|number|code|#)\.?$", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def is_number(s):
    return pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)


def is_date(s):
    return pd.api.types.is_datetime64_any_dtype(s)


def is_text(s):
    return not is_number(s) and not is_date(s)


# ---------- Step 1: read the file ----------

def read_file(data, filename):
    """Returns {sheet name: raw table}. Nothing is interpreted yet: every cell is kept as found."""
    if filename.lower().endswith((".xlsx", ".xlsm", ".xls")):
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, header=None, dtype=object)
        return {name: table for name, table in sheets.items() if not table.dropna(how="all").empty}
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    lines = [line for line in text.splitlines() if line.strip()]
    # the separator is whichever of , ; tab | appears most consistently
    sample = lines[:50]
    separator = max(",;\t|", key=lambda sep: sum(line.count(sep) for line in sample))
    rows = list(csv.reader(io.StringIO(text), delimiter=separator))
    width = max((len(row) for row in rows), default=0)
    rows = [row + [None] * (width - len(row)) for row in rows]
    return {"data": pd.DataFrame(rows, dtype=object)}


# ---------- Step 2: fixes every file needs ----------

def _blank(value):
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


def _find_header_row(raw):
    """The header is the first well-filled row that is mostly words rather than numbers."""
    top = raw.head(25)
    filled = top.apply(lambda row: sum(not _blank(v) for v in row), axis=1)
    if filled.max() == 0:
        return 0
    for position, (_, row) in enumerate(top.iterrows()):
        cells = [str(v).strip() for v in row if not _blank(v)]
        if len(cells) < 0.6 * filled.max():
            continue
        words = sum(not re.fullmatch(r"[-+$£€]?[\d.,%\s]+", c) for c in cells)
        if words >= 0.8 * len(cells):
            return position
    return 0


def structure(raw):
    """Finds the real table inside the sheet. Returns (table, list of notes about what was done)."""
    notes = []
    raw = raw.loc[:, [not all(_blank(v) for v in raw[c]) for c in raw.columns]]
    keep = [not all(_blank(v) for v in row) for row in raw.itertuples(index=False)]
    empty_rows = len(keep) - sum(keep)
    raw = raw[keep].reset_index(drop=True)
    if raw.empty:
        raise ValueError("The file has no data in it.")

    header_at = _find_header_row(raw)
    if header_at > 0:
        notes.append(f"Skipped {header_at} title or note row(s) above the column headings.")
    if all(_plain_number(v) for v in raw.iloc[header_at] if not _blank(v)):
        notes.append("Warning: no row of column headings was found, so the first row was used as headings. "
                     "Add a heading row to the file for reliable results.")

    names, seen = [], {}
    for position, value in enumerate(raw.iloc[header_at]):
        name = re.sub(r"\s+", " ", str(value)).strip() if not _blank(value) else f"Column {position + 1}"
        seen[name] = seen.get(name, 0) + 1
        names.append(name if seen[name] == 1 else f"{name} ({seen[name]})")
    body = raw.iloc[header_at + 1:].copy()
    body.columns = names

    repeated = body.apply(lambda row: [str(v).strip() for v in row] == [str(v).strip() for v in raw.iloc[header_at]], axis=1)
    if len(body) and repeated.any():
        notes.append(f"Removed {int(repeated.sum())} repeated heading row(s) from inside the data.")
        body = body[~repeated]

    # trim spaces and turn "N/A", "-", "null" and similar into proper blanks
    placeholders = 0
    for col in body.columns:
        values = []
        for v in body[col]:
            if isinstance(v, str):
                v = re.sub(r"\s+", " ", v).strip()
            if _blank(v):
                v = None
            elif isinstance(v, str) and v.lower() in MISSING:
                v, placeholders = None, placeholders + 1
            values.append(v)
        body[col] = pd.Series(values, index=body.index, dtype=object)
    if placeholders:
        notes.append(f"Treated {placeholders} placeholder cell(s) such as 'N/A' or '-' as blank.")

    before = len(body)
    body = body.dropna(how="all").reset_index(drop=True)
    empty_rows += before - len(body)
    if empty_rows:
        notes.append(f"Removed {empty_rows} empty row(s).")
    if body.empty:
        raise ValueError("The file has column headings but no rows of data.")

    # columns that are already clean numbers or true dates need no decision from the user
    numbers = dates = 0
    for col in body.columns:
        present = body[col].dropna()
        if present.empty:
            continue
        if all(isinstance(v, (pd.Timestamp,)) or type(v).__name__ in ("datetime", "date") for v in present):
            body[col] = pd.to_datetime(body[col], errors="coerce")
            dates += 1
        elif all(_plain_number(v) for v in present):
            body[col] = pd.to_numeric(body[col].map(lambda v: None if v is None else str(v)), errors="coerce")
            numbers += 1
        else:
            body[col] = body[col].map(lambda v: None if v is None else str(v)).astype(object)
    if numbers or dates:
        notes.append(f"Recognised {numbers} number column(s) and {dates} date column(s) that were already clean.")
    return body, notes


def _plain_number(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    return bool(re.fullmatch(r"-?\d+(\.\d+)?", str(value).strip()))


# ---------- Step 3: fixes the user gets to approve ----------

def parse_number(value, dot_thousands=False):
    """'$52,000', '52k', '12%', '(300)', '45.000,50' -> a number. Returns None if it is not a number."""
    text = re.sub(r"(usd|eur|gbp|inr|aed|cad|aud|sgd|rs\.?|[$£€₹%\s])", "", str(value).lower())
    if "," in text and "." in text:
        # whichever comes last is the decimal mark: 1,234.5 or 1.234,5
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", "") if re.search(r"\d{1,3}(,\d{3})+(?!\d)", text) else text.replace(",", ".")
    elif dot_thousands:
        text = text.replace(".", "")
    match = re.fullmatch(r"(\()?(-?\d+(?:\.\d+)?)(k|m)?\)?", text)
    if not match:
        return None
    number = float(match.group(2)) * {"k": 1e3, "m": 1e6, None: 1}[match.group(3)]
    return -number if match.group(1) else number


def _dot_thousands(present):
    """True when a column writes thousands with dots (45.000), as is common outside the US and UK."""
    dotted = present[present.str.contains(".", regex=False) & ~present.str.contains(",", regex=False)]
    return len(dotted) >= 2 and dotted.str.fullmatch(r"[^\d]*\d{1,3}(\.\d{3})+[^\d]*").all()


def _parse_dates(series):
    """Returns (parsed dates, note about any assumption made)."""
    text = series.dropna().astype(str)
    parts = text.str.extract(r"^(\d{1,2})[-/.](\d{1,2})[-/.]\d{2,4}")
    first, second = pd.to_numeric(parts[0], errors="coerce"), pd.to_numeric(parts[1], errors="coerce")
    day_first, note = False, ""
    if (first > 12).any():
        day_first = True
    elif not (second > 12).any() and first.notna().any():
        note = " Dates like 03/04/2021 were read as month/day/year."
    parsed = pd.to_datetime(series, errors="coerce", dayfirst=day_first, format="mixed")
    return parsed, note


def _best_label(group):
    """Of several spellings prefer 'Sales' over 'SALES' over 'sales', then the most common."""
    counts = group.value_counts()
    rank = lambda v: 0 if (v != v.lower() and v != v.upper()) else 1 if v == v.upper() else 2
    return sorted(counts.index, key=lambda v: (rank(v), -counts[v]))[0]


def _examples(values, limit=3):
    return ", ".join(f"'{v}'" for v in list(dict.fromkeys(values))[:limit])


def propose(table):
    """Looks for problems and returns a list of suggested fixes. Nothing is changed here."""
    proposals = []

    def add(kind, label, detail, column=None, payload=None, source="rule", default=True):
        proposals.append({"kind": kind, "label": label, "detail": detail, "column": column,
                          "payload": payload, "source": source, "default": default})

    # total / summary rows
    lead = table.iloc[:, :3].astype(str).apply(lambda col: col.str.lower().str.strip())
    is_total = lead.apply(lambda col: col.str.fullmatch(r"(grand\s+|sub\s*-?)?totals?:?|sum:?|average:?|avg:?|mean:?")).any(axis=1)
    sparse = table.isna().mean(axis=1) >= 0.4
    total_rows = list(table.index[is_total & (sparse | (table.index >= len(table) - 3))])
    if total_rows:
        add("drop_rows", f"Remove {len(total_rows)} total/summary row(s)",
            "Rows such as 'Total' or 'Average' would be counted as if they were people.", payload=total_rows)

    duplicates = int(table.drop(index=total_rows).duplicated().sum())
    if duplicates:
        # Without an ID-like column, two identical rows can be two different people
        has_identifier = any(table[c].nunique() > 0.9 * max(table[c].notna().sum(), 1) for c in table.columns)
        if has_identifier:
            add("drop_duplicates", f"Remove {duplicates} exact duplicate row(s)",
                "These rows are identical to another row in every column, including an ID-like column.")
        else:
            add("drop_duplicates", f"Remove {duplicates} identical row(s)? Unticked because they may be different people",
                "This file has no ID or name column, so identical rows may be separate people who share the "
                "same details. Tick only if you know they are copies.", default=False)

    for col in table.columns:
        series = table[col]
        if not is_text(series):
            if is_date(series):
                add("years_since", f"Add a 'Years since {col}' column",
                    "Useful for tenure or age. Counted up to today, so for people who have left it is not their length of service.", column=col)
            continue
        present = series.dropna().astype(str)
        if present.empty:
            continue
        lowered = set(present.str.lower())

        if lowered <= YES | NO and lowered & YES and lowered & NO and set(present) - {"Yes", "No"}:
            add("yes_no", f"'{col}': use Yes/No consistently",
                f"{_examples(sorted(set(present)), 5)} become 'Yes' or 'No'.", column=col)
            continue

        dots = _dot_thousands(present)
        parsed_numbers = present.map(lambda v: parse_number(v, dots))
        if parsed_numbers.notna().mean() >= 0.9:
            unreadable = present[parsed_numbers.isna()]
            detail = f"For example {_examples(present[parsed_numbers.notna()])} become plain numbers."
            if dots:
                first = present[parsed_numbers.notna()].iloc[0]
                detail += f" Dots are read as thousands separators, so '{first}' becomes {parse_number(first, True):,.0f}."
            if len(unreadable):
                detail += f" {len(unreadable)} value(s) could not be read and will be blank, e.g. {_examples(unreadable, 2)}."
            add("to_number", f"'{col}': convert text to numbers", detail, column=col)
            continue

        if present.str.contains(DATE_LIKE).mean() >= 0.85:
            parsed, note = _parse_dates(series)
            unreadable = present[parsed[present.index].isna()]
            if len(unreadable) <= 0.15 * len(present):
                detail = f"For example {_examples(present)} become real dates.{note}"
                if len(unreadable):
                    detail += f" {len(unreadable)} value(s) could not be read and will be blank, e.g. {_examples(unreadable, 2)}."
                add("to_date", f"'{col}': convert text to dates", detail, column=col)
                add("years_since", f"Add a 'Years since {col}' column",
                    "Useful for tenure or age. Counted up to today, so for people who have left it is not their length of service.", column=col)
                continue

        if present.nunique() <= 60:
            groups = present.groupby(present.str.lower()).agg(_best_label)
            variants = present.groupby(present.str.lower()).nunique()
            mapping = {v: groups[v.lower()] for v in set(present) if v != groups[v.lower()]}
            if mapping:
                shown = "; ".join(f"'{old}' → '{new}'" for old, new in list(mapping.items())[:3])
                add("merge", f"'{col}': fix inconsistent capital letters ({int((variants > 1).sum())} label(s))",
                    shown, column=col, payload=mapping)
    return proposals


def merge_proposal(table, column, canonical, variants):
    """Builds a proposal from an AI suggestion that several labels mean the same thing."""
    if column not in table.columns or not is_text(table[column]):
        return None
    present = set(table[column].dropna().astype(str))
    mapping = {v: canonical for v in variants if v in present and v != canonical}
    if not mapping:
        return None
    return {"kind": "merge", "label": f"'{column}': treat {_examples(sorted(mapping), 4)} as '{canonical}'",
            "detail": "Suggested by the AI because these labels look like the same thing. Untick if they are different.",
            "column": column, "payload": mapping, "source": "ai", "default": True}


def apply(table, proposals):
    """Applies the approved fixes in order. Returns (clean table, log of what was done)."""
    table, log = table.copy(), []
    for p in proposals:
        col = p["column"]
        if p["kind"] == "drop_rows":
            table = table.drop(index=[i for i in p["payload"] if i in table.index])
        elif p["kind"] == "drop_duplicates":
            table = table.drop_duplicates()
        elif p["kind"] == "yes_no":
            table[col] = table[col].map(
                lambda v: None if v is None or pd.isna(v) else ("Yes" if str(v).lower() in YES else "No")).astype(object)
        elif p["kind"] == "to_number":
            dots = _dot_thousands(table[col].dropna().astype(str))
            table[col] = pd.to_numeric(table[col].map(lambda v: None if v is None or pd.isna(v) else parse_number(v, dots)))
        elif p["kind"] == "to_date":
            table[col] = _parse_dates(table[col])[0]
        elif p["kind"] == "merge":
            if not is_text(table[col]):
                continue
            table[col] = table[col].map(lambda v: p["payload"].get(v, v)).astype(object)
        elif p["kind"] == "years_since":
            if not is_date(table[col]):
                continue
            years = (pd.Timestamp.today().normalize() - table[col]).dt.days / 365.25
            table[f"Years since {col}"] = years.round(1)
        log.append(p["label"] + ("" if p["source"] == "rule" else " (AI suggestion)"))
    return table.reset_index(drop=True), log


# ---------- Privacy ----------

def guess_private(table):
    """Columns that identify a person: names, emails, phone numbers, ID numbers, managers, free text."""
    private = []
    for col in table.columns:
        series = table[col].dropna()
        if series.empty:
            continue
        unique_share = series.nunique() / len(series)
        flag_like = series.nunique() <= 2          # e.g. "Is Manager: Yes/No" is not personal
        if ALWAYS_PERSONAL.search(col) and not NOT_PERSONAL.search(col) and not flag_like:
            private.append(col)
        elif re.search(r"name", col, re.I) and not NOT_PERSONAL.search(col) and unique_share > 0.5:
            private.append(col)                    # "Full Name" yes, "Location Name" no
        elif ID_NAME.search(col) and unique_share > 0.9:
            private.append(col)
        elif series.astype(str).str.contains(EMAIL).mean() > 0.5:
            private.append(col)
        elif is_text(table[col]) and unique_share > 0.8 and series.nunique() >= 8:
            private.append(col)
    return private


def describe_for_ai(table, private):
    """A short description of each column that is safe to send to the AI: no personal values."""
    lines = []
    for col in table.columns:
        series = table[col]
        if col in private:
            lines.append(f"- {col}: [personal column, values withheld]")
        elif is_number(series):
            lines.append(f"- {col}: numbers from {series.min():g} to {series.max():g}")
        elif is_date(series):
            lines.append(f"- {col}: dates")
        else:
            if series.nunique() > 30:
                lines.append(f"- {col}: text with {series.nunique()} distinct values")
            else:
                values = [EMAIL.sub("[email]", str(v))[:40] for v in series.dropna().unique()]
                lines.append(f"- {col}: text with {len(values)} distinct values: {values}")
    return "\n".join(lines)
