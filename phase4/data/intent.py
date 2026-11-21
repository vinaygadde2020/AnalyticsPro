"""
data/intent.py
==============
Rule-based interpretation of plain-English chart requests ("show top 5 region
by sales"). This is keyword matching, NOT a language model: it understands four
chart types (bar, line, histogram, scatter) and returns None for anything else.

No Streamlit or plotting imports; the page turns the returned intent into a chart.
"""

from __future__ import annotations

import re

import pandas as pd

from data.columns import columns_by_role, rank_measures
from data.loader import detect_datetime_columns
from data.recommender import compute_category_aggregation
from utils.helpers import categorical_columns, numeric_columns

_AGGREGATIONS = {"sum": "Sum", "mean": "Mean", "count": "Count"}


def _words(question: str) -> set[str]:
    """Lower-case words of a question as a set."""
    return set(re.findall(r"[a-z0-9]+", question))


def _mentions(question: str, words: set[str], terms: list[str]) -> bool:
    """True if any term appears as a whole word (or, for phrases, as a substring)."""
    return any((t in question) if " " in t else (t in words) for t in terms)


def _column_in_question(columns: list, question: str) -> str | None:
    """First column whose whole name appears in the question (case-insensitive)."""
    for col in columns:
        if re.search(rf"(?<![a-z0-9]){re.escape(str(col).lower())}(?![a-z0-9])", question):
            return col
    return None


def parse_chart_intent(question: str, df: pd.DataFrame) -> dict | None:
    """
    Turn a question into a chart description, or None when it is not understood.

    Returned dict keys: chart_type ("Bar Chart" / "Line Chart" / "Histogram" /
    "Scatter Plot"), x, y, title and, where relevant, agg ("sum"/"mean"/"count"),
    ascending and limit (1..50, default 10).

    Column names and keywords are matched as whole words, so a column called "a"
    is not triggered by the letter "a" inside other words.
    """
    if df is None or df.empty:
        return None
    q = str(question).lower().strip()
    words = _words(q)
    nums = numeric_columns(df, exclude_id=False)
    cats = categorical_columns(df)
    dts = detect_datetime_columns(df)

    # A column named in the question is always honoured (even an ID column). When the
    # question names none, default to a real measure / category rather than an
    # identifier or free-text column that merely happens to come first.
    by_role = columns_by_role(df)
    default_num = next((c for c in rank_measures(by_role["measure"]) if c in nums), nums[0] if nums else None)
    default_cat = next((c for c in by_role["category"] if c in cats), cats[0] if cats else None)
    target_num = _column_in_question(nums, q) or default_num
    target_cat = _column_in_question(cats, q) or default_cat
    target_dt = _column_in_question(dts, q) or (dts[0] if dts else None)

    match = re.search(r"\b(\d+)\b", q)
    limit = min(max(int(match.group(1)), 1), 50) if match else 10

    agg_method = "sum"
    if _mentions(q, words, ["average", "avg", "mean"]):
        agg_method = "mean"
    elif _mentions(q, words, ["count", "number of", "frequency"]):
        agg_method = "count"

    if target_dt and target_num and _mentions(q, words, ["trend", "time", "over", "date", "monthly"]):
        return {
            "chart_type": "Line Chart", "x": target_dt, "y": target_num, "agg": agg_method,
            "title": f"{target_num} Trend over {target_dt}",
        }

    if target_cat and target_num and _mentions(
            q, words, ["top", "highest", "best", "compare", "by", "category", "bottom"]):
        ascending = _mentions(q, words, ["bottom", "lowest"])
        order_label = "Bottom" if ascending else "Top"
        return {
            "chart_type": "Bar Chart", "x": target_cat, "y": target_num, "agg": agg_method,
            "ascending": ascending, "limit": limit,
            "title": f"{order_label} {limit} {target_cat} by {target_num} ({agg_method.title()})",
        }

    if target_num and _mentions(q, words, ["distribution", "histogram", "spread", "range"]):
        return {"chart_type": "Histogram", "x": target_num, "y": None,
                "title": f"Distribution of {target_num}"}

    if len(nums) >= 2 and _mentions(q, words, ["scatter", "relationship", "versus", "vs", "correlation"]):
        second = _column_in_question([c for c in nums if c != target_num], q) or (
            nums[1] if nums[0] == target_num else nums[0])
        return {"chart_type": "Scatter Plot", "x": target_num, "y": second,
                "title": f"{second} vs {target_num}"}

    return None


def build_chart_data(df: pd.DataFrame, intent: dict) -> tuple[pd.DataFrame, str]:
    """
    Aggregate the data for a Bar or Line intent.

    Returns (DataFrame, value_column). value_column is the column holding the
    aggregated numbers; it equals intent["y"] unless x and y are the same column,
    in which case it is renamed so the two do not collide.
    """
    agg = intent.get("agg", "sum")
    if agg not in _AGGREGATIONS:
        agg = "sum"
    x, y = intent["x"], intent["y"]

    if intent["chart_type"] == "Bar Chart":
        data = compute_category_aggregation(
            df, x, y, _AGGREGATIONS[agg],
            ascending=intent.get("ascending", False), top_n=intent.get("limit", 10),
        )
        value_col = y if y != x else f"{y} ({agg})"
        return data, value_col

    if intent["chart_type"] == "Line Chart":
        value_col = y if y != x else f"{y} ({agg})"
        values = getattr(df.groupby(x, dropna=False)[y], agg)().rename(value_col)
        return values.reset_index().sort_values(x), value_col

    raise ValueError(f"No aggregated data is needed for a {intent['chart_type']}.")
