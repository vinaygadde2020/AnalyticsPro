"""
data/analyst.py
===============
The rule-based engine behind the "Ask Your Data" page.

It is deterministic keyword matching over the *actual* dataset: no language
model, no network calls, no API keys. A question is routed to one of a fixed set
of handlers (``SUPPORTED_OPERATIONS``); anything else gets an honest "not
supported" answer plus suggestions.

Suggested prompts are generated from column roles (see data/columns.py) and each
one is checked against the router, so every button maps to a handler that can
answer it. Identifier columns are never suggested as metrics.

Pure pandas; no Streamlit imports.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from data.aggregation import aggregate_values, normalize_aggregation
from data.columns import classify_columns, columns_by_role, rank_measures
from data.intent import parse_chart_intent

#: (handler name, what it does, example question) - shown to users on the page.
SUPPORTED_OPERATIONS: tuple[tuple[str, str, str], ...] = (
    ("row_count", "Count rows and columns", "How many rows are there?"),
    ("missing", "Find missing values per column", "Are there missing values?"),
    ("duplicates", "Count fully duplicated rows", "Are there duplicate rows?"),
    ("correlation", "Strongest relationship between numeric columns", "Which columns are correlated?"),
    ("unique", "Distinct values per column (including identifiers)", "How many unique values are in each column?"),
    ("column_types", "What each column is used for (measure, category, identifier, ...)", "What are the column types?"),
    ("column_stat", "One statistic for one numeric column", "What is the average <numeric column>?"),
    ("value_counts", "How many records fall in each category", "How many records per <category column>?"),
    ("summary", "Summary statistics for numeric columns", "Show summary statistics"),
    ("chart", "Bar chart, trend, distribution or scatter plot from a plain-English request",
     "Show top 10 <category> by <numeric column>"),
)

_AGG_WORDS = {
    "average": "Average", "avg": "Average", "mean": "Average", "total": "Sum", "sum": "Sum",
    "median": "Median", "minimum": "Min", "min": "Min", "lowest": "Min",
    "maximum": "Max", "max": "Max", "highest": "Max", "largest": "Max",
}


@dataclass
class Route:
    """Which handler will answer a question and any parameters found in it."""
    handler: str
    params: dict = field(default_factory=dict)


@dataclass
class Answer:
    """A computed answer the page can render. ``level`` is success/info/warning."""
    handler: str
    level: str
    message: str
    table: pd.DataFrame | None = None
    chart_intent: dict | None = None
    bar_from_table: bool = False


def _words(text: str) -> set[str]:
    """Lower-case words of a question as a set."""
    return set(re.findall(r"[a-z0-9]+", text))


def _has(text: str, words: set[str], terms: list[str]) -> bool:
    """True if any term is a whole word (or, for phrases, a substring) of the question."""
    return any((t in text) if " " in t else (t in words) for t in terms)


def _column_mentioned(columns: list, text: str) -> Any:
    """First column whose whole name appears in the text (case-insensitive)."""
    for col in columns:
        if re.search(rf"(?<![a-z0-9]){re.escape(str(col).lower())}(?![a-z0-9])", text):
            return col
    return None


def route_question(question: str, df: pd.DataFrame) -> Route | None:
    """Decide which handler answers ``question``, or ``None`` if none can.

    Order matters: dataset-level questions first, then column-specific ones,
    then plain-English chart requests as the final fallback.
    """
    if df is None or df.empty or not str(question).strip():
        return None
    q = str(question).lower().strip()
    words = _words(q)
    roles = classify_columns(df)
    categories = [c for c, r in roles.items() if r in ("category", "boolean")]
    all_numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    mentioned_numeric = _column_mentioned(all_numeric, q)
    mentioned_category = _column_mentioned(categories, q)
    # "How many records per region?" names a category, so it must win over the generic row count.
    if mentioned_category and _has(q, words, ["how many", "count", "breakdown", "frequency", "distribution"]) \
            and mentioned_numeric is None \
            and not _has(q, words, ["missing", "null", "nulls", "blank", "empty", "duplicate", "duplicates", "unique", "distinct"]):
        return Route("value_counts", {"column": mentioned_category})


    if _has(q, words, ["how many rows", "number of rows", "row count", "record count",
                       "how many records", "how many columns", "number of columns", "shape", "size"]):
        return Route("row_count")
    if _has(q, words, ["missing", "null", "nulls", "blank", "empty", "nan"]):
        return Route("missing")
    if _has(q, words, ["duplicate", "duplicates", "duplicated"]):
        return Route("duplicates")
    if _has(q, words, ["correlation", "correlated", "relationship between", "relationships"]):
        return Route("correlation")
    if _has(q, words, ["unique values", "distinct values", "unique count", "how many categories", "cardinality"]):
        return Route("unique")
    if _has(q, words, ["column types", "data types", "dtypes", "what columns", "list columns",
                       "list the columns", "show columns", "column roles", "what kind of columns"]):
        return Route("column_types")

    agg_word = next((w for w in q.replace("?", " ").split() if w in _AGG_WORDS), None)
    has_by = "by" in words or "per" in words or "each" in words
    if agg_word and mentioned_numeric and not has_by and not mentioned_category \
            and not _has(q, words, ["trend", "over", "top", "chart", "plot"]):
        return Route("column_stat", {"column": mentioned_numeric, "aggregation": _AGG_WORDS[agg_word]})
    if _has(q, words, ["summary", "describe", "statistics", "stats"]):
        return Route("summary")
    if parse_chart_intent(question, df):
        return Route("chart")
    return None


# --------------------------------------------------------------------------- handlers
def _row_count(df: pd.DataFrame, _params: dict) -> Answer:
    """Handler: number of rows and columns."""
    return Answer("row_count", "success",
                  f"This dataset contains **{len(df):,} rows** and **{len(df.columns):,} columns**.")


def _missing(df: pd.DataFrame, _params: dict) -> Answer:
    """Handler: missing cells per column."""
    miss = df.isna().sum()
    miss = miss[miss > 0].sort_values(ascending=False)
    if miss.empty:
        return Answer("missing", "success", "There are no missing cells in the active dataset.")
    table = miss.rename("Missing cells").rename_axis("Column").reset_index()
    return Answer("missing", "info",
                  f"The dataset contains **{int(miss.sum()):,} missing cells** across **{len(miss):,} columns**.",
                  table=table, bar_from_table=True)


def _duplicates(df: pd.DataFrame, _params: dict) -> Answer:
    """Handler: number of fully duplicated rows."""
    dups = int(df.duplicated().sum())
    return Answer("duplicates", "info", f"Found **{dups:,} fully duplicated rows** in the active dataset.")


def _correlation(df: pd.DataFrame, _params: dict) -> Answer:
    """Handler: strongest Pearson correlation among measure columns."""
    nums = [c for c, r in classify_columns(df).items() if r == "measure"]
    if len(nums) < 2:
        return Answer("correlation", "info", "At least two numeric measure columns are needed for correlation analysis.")
    corr = df[nums].apply(pd.to_numeric, errors="coerce").corr()
    best = None
    for i, left in enumerate(nums):
        for right in nums[i + 1:]:
            value = corr.loc[left, right]
            if pd.notna(value) and (best is None or abs(value) > abs(best[0])):
                best = (float(value), left, right)
    if best is None:
        return Answer("correlation", "info", "There are not enough valid numeric values to calculate pairwise correlations.")
    value, left, right = best
    direction = "positive" if value > 0 else "negative" if value < 0 else "no"
    return Answer("correlation", "info",
                  f"The strongest pairwise linear relationship is between **{left}** and **{right}** "
                  f"(Pearson r = **{value:.3f}**, a {direction} correlation). Correlation does not prove causation.",
                  table=corr.round(3))


def _unique(df: pd.DataFrame, _params: dict) -> Answer:
    """Handler: distinct and missing values per column (identifiers included)."""
    table = pd.DataFrame({
        "Column": df.columns.astype(str),
        "Unique values": [int(df[c].nunique(dropna=True)) for c in df.columns],
        "Missing": [int(df[c].isna().sum()) for c in df.columns],
    })
    return Answer("unique", "info", "Distinct and missing values per column (identifier columns included).", table=table)


def _column_types(df: pd.DataFrame, _params: dict) -> Answer:
    """Handler: the role each column plays (measure, category, identifier, ...)."""
    roles = classify_columns(df)
    table = pd.DataFrame({"Column": [str(c) for c in roles], "Used as": list(roles.values()),
                          "Data type": [str(df[c].dtype) for c in roles]})
    return Answer("column_types", "info",
                  "How each column is treated. Identifiers are not offered as metrics unless you ask for them by name.",
                  table=table)


def _column_stat(df: pd.DataFrame, params: dict) -> Answer:
    """Handler: one statistic (average, total, ...) of one numeric column."""
    col, label = params["column"], params["aggregation"]
    value = aggregate_values(df[col], label)
    if value is None:
        return Answer("column_stat", "warning", f"`{col}` has no numeric values to calculate a {label.lower()} from.")
    shown = f"{value:,.0f}" if label == "Count" else f"{value:,.2f}"
    verb = {"Average": "average", "Sum": "total", "Median": "median", "Min": "minimum",
            "Max": "maximum", "Count": "count of values"}[normalize_aggregation(label)]
    return Answer("column_stat", "success", f"The {verb} of `{col}` is **{shown}**.")


def _value_counts(df: pd.DataFrame, params: dict) -> Answer:
    """Handler: how many records fall in each value of a category column."""
    col = params["column"]
    counts = df[col].astype(object).where(df[col].notna(), "(missing)").astype(str).value_counts().head(15)
    table = counts.rename("Records").rename_axis(str(col)).reset_index()
    return Answer("value_counts", "info", f"Records per `{col}` (top {len(table)}).", table=table, bar_from_table=True)


def _summary(df: pd.DataFrame, _params: dict) -> Answer:
    """Handler: describe() statistics for numeric columns."""
    nums = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
    if not nums:
        return Answer("summary", "info", "No numeric columns are available for summary statistics.")
    table = df[nums].describe().T.reset_index().rename(columns={"index": "Metric"})
    return Answer("summary", "info", "Summary statistics for numeric columns.", table=table)


def _chart(df: pd.DataFrame, params: dict) -> Answer:
    """Handler: describe a chart request so the page can draw it."""
    intent = parse_chart_intent(params["question"], df)
    if not intent:
        return _unsupported(df, params)
    return Answer("chart", "success", intent["title"], chart_intent=intent)


def _unsupported(df: pd.DataFrame, _params: dict | None = None) -> Answer:
    """Honest answer for questions no handler can answer."""
    return Answer(
        "unsupported", "warning",
        "I couldn't confidently map that question to a supported analysis. I answer questions about row counts, "
        "missing values, duplicates, summary statistics, a statistic for one column, records per category, "
        "distributions, scatter plots and a metric by category. Answers are computed from your active dataset; "
        "no external AI service is called.",
    )


_HANDLERS = {
    "row_count": _row_count, "missing": _missing, "duplicates": _duplicates, "correlation": _correlation,
    "unique": _unique, "column_types": _column_types, "column_stat": _column_stat,
    "value_counts": _value_counts, "summary": _summary, "chart": _chart,
}


def answer_question(question: str, df: pd.DataFrame) -> Answer:
    """Answer a question about ``df`` (never raises for ordinary input)."""
    if df is None or df.empty:
        return Answer("unsupported", "info", "Upload a dataset with at least one row to ask questions about it.")
    route = route_question(question, df)
    if route is None:
        return _unsupported(df)
    params = dict(route.params, question=question)
    return _HANDLERS[route.handler](df, params)


# --------------------------------------------------------------------------- suggestions
def suggest_prompts(df: pd.DataFrame, limit: int = 6) -> list[str]:
    """Example questions built from this dataset's real columns.

    Metrics are only columns classified as ``measure`` (never identifiers);
    groupings are only ``category`` columns; trends need a ``date`` column.
    Each candidate is kept only if the router maps it to a handler, so every
    suggestion can be answered. Falls back to dataset-level questions when the
    data has no measures or categories (for example an ID-heavy table).
    """
    if df is None or df.empty or len(df.columns) == 0:
        return []
    by_role = columns_by_role(df)
    measures, categories, dates = rank_measures(by_role["measure"]), by_role["category"], by_role["date"]
    candidates: list[str] = []
    if categories and measures:
        candidates += [f"Show top 10 {categories[0]} by {measures[0]}",
                       f"Show average {measures[0]} by {categories[0]}"]
    if dates and measures:
        candidates.append(f"Show {measures[0]} trend over {dates[0]}")
    if measures:
        candidates += [f"Show distribution of {measures[0]}", f"What is the average {measures[0]}?"]
    if len(measures) >= 2:
        candidates.append(f"Show scatter plot of {measures[0]} vs {measures[1]}")
    if categories:
        candidates.append(f"How many records per {categories[0]}?")
    if df.isna().any().any():
        candidates.append("Are there missing values?")
    candidates += ["How many rows and columns are there?", "What are the column types?"]
    if df.duplicated().any():
        candidates.insert(0, "Are there duplicate rows?")

    suggestions: list[str] = []
    for text in candidates:
        if text in suggestions:
            continue
        route = route_question(text, df)
        if route is not None and answer_question(text, df).handler != "unsupported":
            suggestions.append(text)
        if len(suggestions) >= limit:
            break
    return suggestions


# --------------------------------------------------------------------------- insights
def automatic_insights(df: pd.DataFrame) -> list[str]:
    """Plain-language findings computed from the data (markdown strings).

    Spread and correlation use only ``measure`` columns, and the "most common
    value" uses the first real ``category`` column, so identifiers are never
    reported as findings.
    """
    if df is None or df.empty:
        return []
    by_role = columns_by_role(df)
    measures, categories = by_role["measure"], by_role["category"]
    findings: list[str] = []
    missing_cells = int(df.isna().sum().sum())
    duplicate_rows = int(df.duplicated().sum())
    if missing_cells:
        by_col = df.isna().sum().sort_values(ascending=False)
        findings.append(f"**Missing data:** {missing_cells:,} cells are missing. `{by_col.index[0]}` has the most "
                        f"missing values ({int(by_col.iloc[0]):,}).")
    else:
        findings.append("**Completeness:** no missing cells were detected in the active dataset.")
    if duplicate_rows:
        findings.append(f"**Duplicates:** {duplicate_rows:,} fully duplicated rows were found. Review them before "
                        "deleting, because repeated rows can sometimes be valid records.")
    if measures:
        summary = df[measures].apply(pd.to_numeric, errors="coerce").describe().T
        usable = summary[(summary["mean"].abs() > 0) & summary["std"].notna()]
        if not usable.empty:
            spread = (usable["std"] / usable["mean"].abs()).idxmax()
            findings.append(f"**Numeric variation:** `{spread}` has the largest relative standard deviation among "
                            "numeric measures. This indicates comparatively high spread, not necessarily a problem.")
    if categories:
        col = categories[0]
        counts = df[col].dropna().astype(str).value_counts()
        if not counts.empty:
            share = float(counts.iloc[0] / max(1, df[col].notna().sum()) * 100)
            findings.append(f"**Most common value:** `{counts.index[0]}` is the most frequent value in `{col}` "
                            f"({int(counts.iloc[0]):,} records; {share:.1f}% of non-missing values).")
    if len(measures) >= 2:
        answer = _correlation(df, {})
        if answer.table is not None:
            corr = answer.table
            best = None
            for i, left in enumerate(measures):
                for right in measures[i + 1:]:
                    value = corr.loc[left, right]
                    if pd.notna(value) and (best is None or abs(value) > abs(best[0])):
                        best = (float(value), left, right)
            if best:
                findings.append(f"**Strongest numeric correlation:** `{best[1]}` and `{best[2]}` have Pearson "
                                f"r = {best[0]:.3f}. Correlation describes a linear association and does not prove causation.")
    return findings
