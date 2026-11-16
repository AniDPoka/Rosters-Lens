"""The analysis tools the AI agent is allowed to use. All numbers are calculated here, not by the AI."""

import math
import re

import pandas as pd

from cleaner import is_date, is_number

MIN_GROUP = 5    # results for fewer people than this are left out
MAX_GROUPS = 25  # longest table sent to the AI
RELIABLE = 20    # groups smaller than this give shaky rates and averages


class ToolError(Exception):
    pass


def _key(name):
    return re.sub(r"[\s_\-]+", "", str(name)).lower()


class Toolbox:
    def __init__(self, table, private, meanings=None):
        self.table = table
        self.private = set(private)
        self.meanings = meanings or {}
        self.steps = []    # a record of every tool call, shown to the user as "how I got this"
        self.outputs = []  # the exact text given to the AI, used to check its answer afterwards

    # ----- helpers -----

    def _column(self, name):
        usable = [c for c in self.table.columns if c not in self.private]
        matches = [c for c in self.table.columns if _key(c) == _key(name)]
        if not matches and len(_key(name)) >= 3:
            # "salary" finds "Annual Salary", but only when exactly one column fits
            close = [c for c in usable if _key(name) in _key(c)]
            matches = close if len(close) == 1 else []
        if not matches:
            raise ToolError(f"There is no column called '{name}'. Available columns: {', '.join(usable)}")
        if matches[0] in self.private:
            raise ToolError(f"'{matches[0]}' is a personal column and cannot be used in analysis.")
        return matches[0]

    def _filter(self, filters):
        data = self.table
        # conditions are separated by ';' (or by 'and' when a new condition clearly follows)
        for condition in re.split(r";|\s+and\s+(?=[^=<>!;]+(?:>=|<=|!=|=|>|<))", filters or "", flags=re.I):
            if not condition.strip():
                continue
            match = re.match(r"^\s*(.+?)\s*(>=|<=|!=|=|>|<)\s*(.+?)\s*$", condition)
            if not match:
                raise ToolError(f"Could not understand the filter '{condition.strip()}'. Use e.g. Department = Sales; Age > 30")
            col, op, value = self._column(match.group(1)), match.group(2), match.group(3).strip("'\" ")
            series = data[col]
            if is_date(series):
                if re.fullmatch(r"\d{4}", value):
                    series, target = series.dt.year, int(value)
                else:
                    target = pd.to_datetime(value, errors="coerce")
                    if pd.isna(target):
                        raise ToolError(f"'{value}' is not a date.")
            elif is_number(series):
                try:
                    target = float(value)
                except ValueError:
                    raise ToolError(f"'{col}' holds numbers, so '{value}' cannot be compared with it.")
            else:
                if op not in ("=", "!="):
                    raise ToolError(f"'{col}' holds text, so only = and != work on it.")
                series, target = series.astype(str).str.lower(), value.lower()
                if op == "=" and not (series == target).any():
                    options = ", ".join(map(str, data[col].dropna().unique()[:15]))
                    raise ToolError(f"No rows have {col} = '{value}'. Values in that column: {options}")
            mask = {"=": series == target, "!=": series != target, ">": series > target,
                    ">=": series >= target, "<": series < target, "<=": series <= target}[op]
            data = data[mask.fillna(False)]
        if 0 < len(data) < MIN_GROUP:
            raise ToolError(f"That filter leaves fewer than {MIN_GROUP} people, so the result is hidden for privacy.")
        if data.empty:
            raise ToolError("No rows match that filter.")
        if 0 < len(self.table) - len(data) < MIN_GROUP:
            # otherwise "everyone" minus "everyone except 2 people" would reveal those 2 people
            raise ToolError(f"That filter excludes fewer than {MIN_GROUP} people, so the result is hidden: "
                            "it could reveal them when compared with the overall figure.")
        return data

    def _matches(self, data, col, value):
        """True/False for each row: does this column hold this value?"""
        if is_number(data[col]):
            try:
                matches = data[col] == float(value)   # so that 1 matches 1.0
            except ValueError:
                raise ToolError(f"'{col}' holds numbers, so '{value}' cannot be looked for in it.")
        else:
            matches = data[col].astype(str).str.lower() == str(value).lower()
        if not matches.any():
            options = ", ".join(f"{v:g}" if is_number(data[col]) else str(v) for v in data[col].unique()[:15])
            raise ToolError(f"No rows have {col} = '{value}'. Values in that column: {options}")
        return matches

    def _groups(self, data, col):
        """Numbers with many values become ranges, dates become years, everything else is used as is."""
        series = data[col]
        if is_date(series):
            return series.dt.year.astype("Int64").astype(str).replace("<NA>", "(blank)")
        if is_number(series) and series.nunique() > 8:
            ranges = pd.qcut(series, 4, duplicates="drop")
            lowest = series.min()
            # tidy edges: "4,976 to 5,993" for big numbers, "6.2 to 9.7" for small ones
            edge = (lambda v: f"{v:,.0f}") if series.abs().max() >= 100 else (lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
            return ranges.astype(object).map(
                lambda r: "(blank)" if pd.isna(r) else f"{edge(max(r.left, lowest))} to {edge(r.right)}")
        if is_number(series):
            return series.map(lambda v: "(blank)" if pd.isna(v) else f"{v:g}")
        return series.fillna("(blank)").astype(str)

    def _finish(self, tool, arguments, table, value_column, note="", keep="first", kind="bar"):
        """Leaves out small groups, records the step for the user, and returns text for the AI."""
        small = table["People"] < MIN_GROUP
        shown = table[~small].reset_index(drop=True)
        if small.any():
            # small groups are dropped label and all, so a rare label can never point at one person
            note += f" {int(small.sum())} group(s) with fewer than {MIN_GROUP} people were left out for privacy."
        if len(shown) > MAX_GROUPS:
            note += f" Showing {MAX_GROUPS} of {len(shown)} groups."
            shown = (shown.tail(MAX_GROUPS) if keep == "last" else shown.head(MAX_GROUPS)).reset_index(drop=True)
        if shown.empty:
            raise ToolError(f"Every group has fewer than {MIN_GROUP} people, so nothing can be shown.")
        shaky = shown[shown["People"] < RELIABLE]
        if len(shaky) and len(shown.columns) > 2:
            # name the small groups, so the AI cannot attach the warning to the wrong one
            names = ", ".join(str(v) for v in shaky.iloc[:, 0])
            note += f" {len(shaky)} group(s) have fewer than {RELIABLE} people, so their figures are unreliable: {names}."
        chart = shown.set_index(shown.columns[0])[value_column] if len(shown) > 1 else None
        self.steps.append({"tool": tool, "arguments": arguments, "table": shown, "chart": chart, "kind": kind,
                           "note": note.strip()})
        return shown.to_string(index=False) + ("\n" + note.strip() if note.strip() else "")

    # ----- the tools -----

    def describe_data(self):
        lines = [f"{len(self.table)} rows. Columns:"]
        for col in self.table.columns:
            series, meaning = self.table[col], self.meanings.get(col, "")
            meaning = f" ({meaning})" if meaning else ""
            blank = f", {series.isna().mean() * 100:.0f}% blank" if series.isna().any() else ""
            if col in self.private:
                lines.append(f"- {col}{meaning}: personal column, not available for analysis")
            elif is_date(series):
                lines.append(f"- {col}{meaning}: dates from {series.min():%Y-%m-%d} to {series.max():%Y-%m-%d}{blank}")
            elif is_number(series):
                lines.append(f"- {col}{meaning}: numbers, {series.min():g} to {series.max():g}, average {series.mean():.1f}{blank}")
            else:
                values = ", ".join(map(str, series.dropna().unique()[:12]))
                more = "" if series.nunique() <= 12 else f" and {series.nunique() - 12} more"
                lines.append(f"- {col}{meaning}: text. Values: {values}{more}{blank}")
        self.steps.append({"tool": "describe_data", "arguments": {}, "table": None, "chart": None,
                           "note": "Looked at the list of columns."})
        return "\n".join(lines)

    def count_rows(self, group_by="", filters=""):
        data = self._filter(filters)
        if not group_by:
            table = pd.DataFrame({"Group": ["All"], "People": [len(data)]})
            return self._finish("count_rows", {"filters": filters}, table, "People")
        col = self._column(group_by)
        counts = self._groups(data, col).value_counts()
        table = pd.DataFrame({col: counts.index, "People": counts.values,
                              "Share (%)": (counts.values / len(data) * 100).round(1)})
        return self._finish("count_rows", {"group_by": col, "filters": filters}, table, "People")

    def summarize_number(self, number_column, statistic="average", group_by="", filters=""):
        col = self._column(number_column)
        if not is_number(self.table[col]):
            raise ToolError(f"'{col}' does not hold numbers. Use count_rows or rate_of_value for it instead.")
        functions = {"average": "mean", "mean": "mean", "median": "median", "total": "sum", "sum": "sum"}
        if statistic.lower() not in functions:
            raise ToolError("statistic must be average, median or total. Individual values (highest, lowest) are not available.")
        data = self._filter(filters)
        data = data[data[col].notna()]
        label = f"{statistic.capitalize()} {col}"
        if not group_by:
            table = pd.DataFrame({"Group": ["All"], "People": [len(data)],
                                  label: [round(float(data[col].agg(functions[statistic.lower()])), 2)]})
            return self._finish("summarize_number", {"number_column": col, "statistic": statistic, "filters": filters}, table, label)
        by = self._column(group_by)
        grouped = data.groupby(self._groups(data, by))[col].agg(["size", functions[statistic.lower()]])
        table = pd.DataFrame({by: grouped.index, "People": grouped["size"].values, label: grouped.iloc[:, 1].round(2).values})
        table = table.sort_values(label, ascending=False).reset_index(drop=True)
        return self._finish("summarize_number", {"number_column": col, "statistic": statistic, "group_by": by, "filters": filters},
                            table, label)

    def rate_of_value(self, column, value, group_by="", filters=""):
        col = self._column(column)
        data = self._filter(filters)
        data = data[data[col].notna()]
        matches = self._matches(data, col, value)
        label = f"% with {col} = {value}"
        if not group_by:
            table = pd.DataFrame({"Group": ["All"], "People": [len(data)], label: [round(matches.mean() * 100, 1)]})
            return self._finish("rate_of_value", {"column": col, "value": value, "filters": filters}, table, label)
        by = self._column(group_by)
        grouped = matches.groupby(self._groups(data, by)).agg(["size", "mean"])
        table = pd.DataFrame({by: grouped.index, "People": grouped["size"].values, label: (grouped["mean"] * 100).round(1).values})
        table = table.sort_values(label, ascending=False).reset_index(drop=True)
        return self._finish("rate_of_value", {"column": col, "value": value, "group_by": by, "filters": filters}, table, label)

    def trend_over_time(self, date_column, period="year", filters=""):
        col = self._column(date_column)
        if not is_date(self.table[col]):
            raise ToolError(f"'{col}' does not hold dates.")
        codes = {"year": "Y", "quarter": "Q", "month": "M"}
        if period.lower() not in codes:
            raise ToolError("period must be year, quarter or month.")
        data = self._filter(filters)
        counts = data[col].dropna().dt.to_period(codes[period.lower()]).value_counts().sort_index()
        table = pd.DataFrame({period.capitalize(): counts.index.astype(str), "People": counts.values})
        return self._finish("trend_over_time", {"date_column": col, "period": period, "filters": filters}, table, "People", keep="last", kind="line")

    def compare_two_numbers(self, column_a, column_b):
        a, b = self._column(column_a), self._column(column_b)
        for col in (a, b):
            if not is_number(self.table[col]):
                raise ToolError(f"'{col}' does not hold numbers.")
        pair = self.table[[a, b]].dropna()
        if len(pair) < 10:
            raise ToolError("There are too few rows with both values to compare.")
        r = pair[a].corr(pair[b])
        strength = "strong" if abs(r) >= 0.6 else "moderate" if abs(r) >= 0.3 else "weak or no"
        direction = "" if abs(r) < 0.3 else (" positive" if r > 0 else " negative")
        text = f"Correlation between {a} and {b}: {r:.2f} ({strength}{direction} link) across {len(pair)} rows."
        self.steps.append({"tool": "compare_two_numbers", "arguments": {"column_a": a, "column_b": b},
                           "table": None, "chart": None, "note": text})
        return text + " Correlation shows a pattern, not a cause."

    def find_drivers(self, column, value, filters=""):
        """Scans every usable column for the biggest gaps in how often an outcome happens."""
        col = self._column(column)
        data = self._filter(filters)
        data = data[data[col].notna()]
        matches = self._matches(data, col, value)
        rows = []
        for other in data.columns:
            if other == col or other in self.private:
                continue
            stats = matches.groupby(self._groups(data, other)).agg(["size", "mean"])
            stats = stats[(stats["size"] >= RELIABLE) & (stats.index != "(blank)")]
            if not 2 <= len(stats) <= 12:
                continue
            high, low = stats["mean"].idxmax(), stats["mean"].idxmin()
            p1, n1, p2, n2 = stats.loc[high, "mean"], stats.loc[high, "size"], stats.loc[low, "mean"], stats.loc[low, "size"]
            # a standard check of whether a gap this size could easily happen by chance
            pooled = (p1 * n1 + p2 * n2) / (n1 + n2)
            spread = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
            z = abs(p1 - p2) / spread if spread else 0
            rows.append({"Factor": other, "Highest group": f"{high} ({p1 * 100:.1f}%, {n1} people)",
                         "Lowest group": f"{low} ({p2 * 100:.1f}%, {n2} people)",
                         "Gap (points)": round((p1 - p2) * 100, 1),
                         "Evidence": "Strong" if z >= 2.58 else "Some" if z >= 1.96 else "Weak, could be chance"})
        if not rows:
            raise ToolError(f"No column has at least two groups of {RELIABLE}+ people to compare.")
        table = pd.DataFrame(rows).sort_values("Gap (points)", ascending=False).head(8).reset_index(drop=True)
        note = (f"Outcome: {col} = {value}, {matches.mean() * 100:.1f}% overall across {len(data)} people. "
                f"Only groups of {RELIABLE}+ people are compared. Gaps show patterns, not causes, and factors "
                "can overlap (for example overtime may be concentrated in one department).")
        self.steps.append({"tool": "find_drivers", "arguments": {"column": col, "value": value, "filters": filters},
                           "table": table, "chart": table.set_index("Factor")["Gap (points)"], "note": note})
        return table.to_string(index=False) + "\n" + note

    def run(self, name, arguments):
        """Runs one tool and remembers exactly what the AI was told."""
        result = self._run(name, arguments)
        self.outputs.append(result)
        return result

    def _run(self, name, arguments):
        """Runs one tool by name. Problems come back as text so the AI can correct itself."""
        if name not in DECLARED:
            return f"Error: there is no tool called {name}."
        try:
            clean = {k: str(v) for k, v in (arguments or {}).items()
                     if k in DECLARED[name] and v is not None and str(v).strip() != ""}
            return getattr(self, name)(**clean)
        except TypeError:
            return f"Error: {name} is missing a required argument. It needs: {', '.join(REQUIRED[name])}."
        except ToolError as error:
            self.steps.append({"tool": name, "arguments": arguments, "table": None, "chart": None,
                               "note": f"Could not do this: {error}"})
            return f"Error: {error}"
        except Exception as error:
            return f"Error: this tool failed ({type(error).__name__}). Try a different approach."


def _tool(name, description, **parameters):
    required = [p for p, text in parameters.items() if not text.startswith("Optional")]
    return {"name": name, "description": description,
            "parameters": {"type": "object", "required": required,
                           "properties": {p: {"type": "string", "description": text} for p, text in parameters.items()}}}


FILTER_HELP = "Optional. Conditions separated by ';', e.g. 'Department = Sales; Age >= 30'. Operators: = != > >= < <=."
GROUP_HELP = "Optional. Column to split the result by."

DECLARATIONS = [
    _tool("describe_data", "Lists every column with its type, meaning and example values. Use this first."),
    _tool("count_rows", "Counts people, in total or split by a column (headcount by department, hires by year).",
          group_by=GROUP_HELP, filters=FILTER_HELP),
    _tool("summarize_number", "Average, median or total of a number column, overall or split by a column.",
          number_column="The number column, e.g. salary.", statistic="Optional. average (default), median or total.",
          group_by=GROUP_HELP, filters=FILTER_HELP),
    _tool("rate_of_value", "Percentage of people who have a given value in a column, overall or split by a column. "
          "Use for rates such as attrition (Left = Yes), overtime, or remote work.",
          column="The column to check.", value="The value to look for, e.g. Yes.", group_by=GROUP_HELP, filters=FILTER_HELP),
    _tool("trend_over_time", "Counts people per year, quarter or month of a date column (e.g. hires per year).",
          date_column="The date column.", period="Optional. year (default), quarter or month.", filters=FILTER_HELP),
    _tool("find_drivers", "Scans every column to find what is most strongly linked to an outcome, e.g. what is "
          "linked to Left = Yes. Use for 'why', 'what drives' or 'what explains' questions.",
          column="The outcome column, e.g. Left Company.", value="The outcome value, e.g. Yes.", filters=FILTER_HELP),
    _tool("compare_two_numbers", "Measures whether two number columns move together (correlation).",
          column_a="First number column.", column_b="Second number column."),
]
DECLARED = {d["name"]: set(d.get("parameters", {}).get("properties", {})) for d in DECLARATIONS}
REQUIRED = {d["name"]: d.get("parameters", {}).get("required", []) for d in DECLARATIONS}
# The same tools in the shape Groq expects (the OpenAI "function" format)
TOOLS_FOR_AI = [{"type": "function", "function": declaration} for declaration in DECLARATIONS]


# ---------- Checking the AI's answer ----------

_NUMBER = re.compile(r"(?<![A-Za-z\d.])\d[\d,]*(?:\.\d+)?")


def _numbers(text):
    found = []
    for token in _NUMBER.findall(text or ""):
        token = token.rstrip(",")
        try:
            found.append((token, float(token.replace(",", ""))))
        except ValueError:
            pass
    return found


def unverified_numbers(answer, sources):
    """Returns the figures in the AI's answer that cannot be traced to the calculated results.

    A figure passes if it equals a calculated number (allowing for rounding) or the difference
    between two of them. Whole numbers up to 10 pass, since they are usually words like 'top 3'.
    """
    known = {value for text in sources for _, value in _numbers(text)}
    if len(known) <= 80:
        known |= {abs(a - b) for a in known for b in known}
    unmatched = []
    for token, value in _numbers(answer):
        decimals = len(token.split(".")[1]) if "." in token else 0
        if decimals == 0 and value <= 10:
            continue
        tolerance = 0.5 * 10 ** -decimals + 1e-9
        if not any(abs(k - value) <= tolerance for k in known) and token not in unmatched:
            unmatched.append(token)
    return unmatched
