"""
data/recommender.py
=====================
Smart Visual Recommendations engine for AnalyticsPro.

Pure pandas/data-analysis logic only:
    * No Streamlit imports.
    * No UI code.
    * No hard-coded, dataset-specific values.

Given an arbitrary dataframe, `generate_visual_recommendations()`
inspects its actual column types, cardinality, missingness, variance
and correlations, and returns a prioritized, de-duplicated list of
chart recommendations. Each recommendation is a plain dict so it can
be rendered by any UI layer (Streamlit, tests, notebooks, etc.).

This module intentionally reuses the project's existing column-
classification helpers (utils.helpers) and dataset-analysis helpers
(data.profiler, data.loader) instead of re-implementing that logic.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from data.aggregation import group_aggregate
from data.loader import detect_datetime_columns
from data.profiler import outlier_summary
from utils.helpers import categorical_columns, looks_like_id_name, numeric_columns

_KNOWN_AGGS = ("Sum", "Mean", "Count", "Median", "Min", "Max")

# ---------------------------------------------------------------------
# Column-suitability heuristics
# ---------------------------------------------------------------------

def _looks_like_id(df: pd.DataFrame, col: str) -> bool:
    """
    Heuristic for identifying ID-like columns that shouldn't be used
    as ordinary chart dimensions: either the column name hints at an
    identifier, or nearly every value in the column is unique.
    """
    if looks_like_id_name(col):
        return True
    n = len(df)
    if n == 0:
        return False
    unique_count = df[col].nunique(dropna=True)
    return unique_count > 20 and (unique_count / n) > 0.9


def usable_categorical_columns(
    df: pd.DataFrame,
    max_cardinality: int = 50,
    max_unique_ratio: float = 0.5,
) -> list:
    """
    Categorical columns with cardinality low enough to produce a
    meaningful category chart. Excludes ID-like / near-unique columns
    and columns with fewer than 2 distinct values.
    """
    if df is None or df.empty:
        return []
    n = max(len(df), 1)
    usable = []
    for col in categorical_columns(df):
        if _looks_like_id(df, col):
            continue
        unique = df[col].nunique(dropna=True)
        if unique < 2 or unique > max_cardinality:
            continue
        if (unique / n) > max_unique_ratio:
            continue
        usable.append(col)
    return usable


def usable_numeric_columns(df: pd.DataFrame) -> list:
    """
    Numeric columns (ID-like numeric columns excluded) that have at
    least two distinct non-null values, i.e. columns with meaningful
    variance to plot.
    """
    if df is None or df.empty:
        return []
    usable = []
    for col in numeric_columns(df, exclude_id=True):
        s = df[col].dropna()
        if s.empty or s.nunique() < 2:
            continue
        usable.append(col)
    return usable


def usable_datetime_columns(df: pd.DataFrame) -> list:
    """Datetime-capable columns (real dtype or reliably parseable) with at least one valid value."""
    if df is None or df.empty:
        return []
    cols = []
    for col in detect_datetime_columns(df):
        try:
            parsed = df[col] if pd.api.types.is_datetime64_any_dtype(df[col]) else pd.to_datetime(df[col], errors="coerce")
            if parsed.notna().any():
                cols.append(col)
        except Exception:
            continue
    return cols


def _rank_by_variance(df: pd.DataFrame, cols: Sequence[str]) -> list:
    """Sort numeric column names by variance, descending (0 variance sorts last)."""
    scored = []
    for col in cols:
        try:
            var = float(df[col].var(skipna=True) or 0.0)
        except Exception:
            var = 0.0
        scored.append((col, var))
    scored.sort(key=lambda item: item[1], reverse=True)
    return [c for c, _ in scored]


# ---------------------------------------------------------------------
# Recommendation dict factory + de-duplication
# ---------------------------------------------------------------------

def _rec(
    title: str, description: str, chart_type: str, reason: str, priority: int,
    x_column: str | None = None, y_column: str | None = None, aggregation: str | None = None,
    columns: Sequence[str] | None = None, interactive: bool = True,
) -> dict:
    """
    Build one recommendation dict.

    `interactive` marks whether this recommendation maps onto the
    existing manual visualization controls (chart type / X / Y /
    aggregation) and can be "applied" to them, versus a summary-style
    recommendation (KPI overview, correlation heatmap, ranked/ time
    views) that's best shown as its own preview.

    `columns` is an optional list used only by multi-column
    recommendation types (KPI Summary, Correlation Heatmap) that
    don't fit the single x/y shape.
    """
    return {
        "title": title,
        "description": description,
        "chart_type": chart_type,
        "x_column": x_column,
        "y_column": y_column,
        "aggregation": aggregation,
        "columns": columns,
        "reason": reason,
        "priority": priority,
        "interactive": interactive,
    }


def _dedupe(recommendations: list[dict]) -> list[dict]:
    """Drop recommendations that repeat the same chart/columns/aggregation."""
    seen = set()
    unique = []
    for rec in recommendations:
        key = (
            rec["chart_type"],
            rec.get("x_column"),
            rec.get("y_column"),
            rec.get("aggregation"),
            tuple(rec.get("columns") or []),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(rec)
    return unique


# ---------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------

def _kpi_overview_recs(nums: list, ranked: list, n_rows: int) -> list[dict]:
    """One KPI summary card over the highest-variance numeric columns."""
    if not nums:
        return []
    top_metrics = ranked[:4]
    return [_rec(
        title="KPI Summary Overview",
        description=f"A quick-glance summary of {len(top_metrics)} key numeric metric(s): {', '.join(top_metrics)}.",
        chart_type="KPI Summary",
        reason=f"Dataset has {len(nums)} usable numeric column(s) across {n_rows:,} rows.",
        priority=85, columns=top_metrics, interactive=False,
    )]


def _category_count_recs(df: pd.DataFrame, cats: list) -> list[dict]:
    """Record counts for the first two usable categorical columns."""
    recs = []
    for col in cats[:2]:
        unique = df[col].nunique(dropna=True)
        recs.append(_rec(
            title=f"Distribution of {col}",
            description=f"See how records are spread across the {unique} categories of {col}.",
            chart_type="Bar Chart", x_column=col, y_column=None, aggregation="Count",
            reason=f"{col} has {unique} distinct categories, suitable for a category breakdown.",
            priority=60,
        ))
    return recs


def _category_metric_recs(nums: list, cats: list, ranked: list) -> list[dict]:
    """Average / total / count / bottom-N views pairing a category with a numeric metric."""
    if not (cats and nums):
        return []
    top_cat, top_metric = cats[0], ranked[0]
    recs = [
        _rec(title=f"Average {top_metric} by {top_cat}",
             description=f"Compare the average {top_metric} across each {top_cat} group.",
             chart_type="Bar Chart", x_column=top_cat, y_column=top_metric, aggregation="Mean",
             reason=f"{top_cat} is categorical and {top_metric} is numeric with meaningful variance.", priority=80),
        _rec(title=f"Top {top_cat} by Total {top_metric}",
             description=f"Rank {top_cat} categories by their total (summed) {top_metric}.",
             chart_type="Bar Chart", x_column=top_cat, y_column=top_metric, aggregation="Sum",
             reason=f"Ranking categories by summed {top_metric} highlights the biggest contributors.", priority=78),
    ]
    if len(cats) > 1 or len(nums) > 1:
        second_cat = cats[1] if len(cats) > 1 else top_cat
        second_metric = ranked[1] if len(nums) > 1 else top_metric
        if (second_cat, second_metric) != (top_cat, top_metric):
            recs.append(_rec(
                title=f"Count of Records by {second_cat}",
                description=f"See record counts of {second_metric} broken down by {second_cat}.",
                chart_type="Bar Chart", x_column=second_cat, y_column=second_metric, aggregation="Count",
                reason=f"A second categorical/numeric pairing worth exploring: {second_cat} and {second_metric}.",
                priority=55))
    # Bottom categories (ascending) are preview-only: the manual controls only support a descending "Top N".
    recs.append(_rec(
        title=f"Bottom {top_cat} by Total {top_metric}",
        description=f"Identify the lowest-performing {top_cat} categories by total {top_metric}.",
        chart_type="Bottom Categories", x_column=top_cat, y_column=top_metric, aggregation="Sum",
        reason="Understanding the weakest categories is as useful as understanding the strongest.",
        priority=45, interactive=False))
    return recs


def _time_trend_recs(nums: list, dates: list, ranked: list) -> list[dict]:
    """A trend line of the highest-variance metric over the first date column."""
    if not (dates and nums):
        return []
    date_col, metric_col = dates[0], ranked[0]
    return [_rec(
        title=f"{metric_col} Trend Over Time",
        description=f"Track how {metric_col} evolves over {date_col}.",
        chart_type="Time Trend", x_column=date_col, y_column=metric_col, aggregation="Mean",
        reason=f"{date_col} is a date/time column, well suited to a trend line for {metric_col}.",
        priority=90, interactive=False,
    )]


def _histogram_recs(ranked: list, n_rows: int) -> list[dict]:
    """Histograms of the two highest-variance numeric columns."""
    return [_rec(
        title=f"Distribution of {col}",
        description=f"Visualize the spread and shape of {col} values.",
        chart_type="Histogram", x_column=col, y_column=None, aggregation=None,
        reason=f"{col} is numeric with meaningful variance across {n_rows:,} rows.", priority=50,
    ) for col in ranked[:2]]


def _outlier_box_recs(df: pd.DataFrame, nums: list, ranked: list) -> list[dict]:
    """Box plot of the column with the highest outlier rate (or of the top-variance column if none)."""
    try:
        outliers_df = outlier_summary(df)
    except (ValueError, TypeError, KeyError):
        outliers_df = pd.DataFrame()

    if not outliers_df.empty:
        top = outliers_df.iloc[0]
        column, pct = top["Column"], float(top["Outlier %"])
        if column not in nums:
            return []
        return [_rec(
            title=f"Outlier Check: {column}",
            description=f"{column} has {pct:.1f}% of values flagged as statistical outliers (IQR method).",
            chart_type="Box Plot", x_column=None, y_column=column, aggregation=None,
            reason=f"{column} shows the highest outlier rate ({pct:.1f}%) among numeric columns.",
            priority=65 if pct > 5 else 40,
        )]
    if ranked:
        return [_rec(
            title=f"Box Plot of {ranked[0]}", description=f"Review the quartile spread of {ranked[0]}.",
            chart_type="Box Plot", x_column=None, y_column=ranked[0], aggregation=None,
            reason=f"{ranked[0]} is numeric with meaningful variance.", priority=35,
        )]
    return []


def _strongest_pair(df: pd.DataFrame, nums: list) -> tuple | None:
    """The most strongly correlated pair of numeric columns as ``(col_a, col_b, |r|)``, or None."""
    corr_matrix = df[nums].corr(numeric_only=True).abs()
    best = None
    for i, col_a in enumerate(nums):
        for col_b in nums[i + 1:]:
            score = corr_matrix.loc[col_a, col_b]
            if pd.notna(score) and score > (best[2] if best else 0.0):
                best = (col_a, col_b, float(score))
    return best


def _relationship_recs(df: pd.DataFrame, nums: list) -> list[dict]:
    """Scatter plot of the most strongly correlated numeric pair."""
    if len(nums) < 2:
        return []
    try:
        best = _strongest_pair(df, nums)
    except (ValueError, TypeError, KeyError):
        return []
    if best is None:
        return []
    col_a, col_b, score = best
    return [_rec(
        title=f"{col_a} vs {col_b} Relationship",
        description=f"Explore how {col_a} and {col_b} relate to each other.",
        chart_type="Scatter Plot", x_column=col_a, y_column=col_b, aggregation=None,
        reason=f"These two numeric columns have a correlation of {score:.2f}.",
        priority=int(60 + score * 30),
    )]


def _heatmap_recs(nums: list, ranked: list) -> list[dict]:
    """Correlation heatmap when three or more numeric columns exist."""
    if len(nums) < 3:
        return []
    cols = ranked[:10]
    return [_rec(
        title="Correlation Heatmap",
        description=f"See how {len(cols)} numeric columns correlate with one another.",
        chart_type="Correlation Heatmap",
        reason=f"{len(nums)} usable numeric columns are available for a multi-variable correlation view.",
        priority=75, columns=cols, interactive=False,
    )]


def generate_visual_recommendations(df: pd.DataFrame, max_recommendations: int = 8) -> list[dict]:
    """
    Inspect `df` and return a prioritized, de-duplicated list of
    visualization recommendations (see `_rec()` for the shape of
    each entry). Each kind of recommendation is built by its own helper.

    Returns an empty list for a missing/empty dataframe, or one with
    no usable columns.
    """
    if df is None or df.empty or len(df.columns) == 0:
        return []

    n_rows = len(df)
    nums = usable_numeric_columns(df)
    cats = usable_categorical_columns(df)
    dates = usable_datetime_columns(df)
    ranked = _rank_by_variance(df, nums)

    recs = (
        _kpi_overview_recs(nums, ranked, n_rows)
        + _category_count_recs(df, cats)
        + _category_metric_recs(nums, cats, ranked)
        + _time_trend_recs(nums, dates, ranked)
        + _histogram_recs(ranked, n_rows)
        + _outlier_box_recs(df, nums, ranked)
        + _relationship_recs(df, nums)
        + _heatmap_recs(nums, ranked)
    )
    recs = _dedupe(recs)
    recs.sort(key=lambda r: r["priority"], reverse=True)
    return recs[:max_recommendations]


# ---------------------------------------------------------------------
# Preview-data builders for non-interactive (summary-style) recommendations
# ---------------------------------------------------------------------

def compute_kpi_summary(df: pd.DataFrame, columns: Sequence[str]) -> list[dict]:
    """
    Return a list of {column, mean, sum, count, missing} dicts for
    the given numeric columns, used to render KPI summary cards.
    """
    if df is None or df.empty or not columns:
        return []
    summary = []
    for col in columns:
        if col not in df.columns:
            continue
        s = df[col]
        valid = s.dropna()
        summary.append({
            "column": col,
            "mean": float(valid.mean()) if not valid.empty else None,
            "sum": float(valid.sum()) if not valid.empty else None,
            "count": int(valid.count()),
            "missing": int(s.isna().sum()),
        })
    return summary


def compute_category_aggregation(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    aggregation: str = 'Sum',
    ascending: bool = False,
    top_n: int = 10,
) -> pd.DataFrame:
    """
    Group df by x_col and aggregate y_col, returning a DataFrame with
    columns [x_col, y_col] sorted by y_col according to `ascending`,
    limited to top_n rows. Mirrors the aggregation options already
    used by the manual visualization controls (Sum/Mean/Count/
    Median/Min/Max) so recommendation previews stay consistent with
    the rest of the app.
    """
    if df is None or df.empty or x_col not in df.columns or y_col not in df.columns:
        return pd.DataFrame()

    result, value_name = group_aggregate(df, [x_col], y_col, aggregation if aggregation in _KNOWN_AGGS else "Sum")
    result = result.sort_values(value_name, ascending=ascending).head(top_n)
    return result


def compute_time_trend(
    df: pd.DataFrame,
    date_col: str,
    value_col: str,
    aggregation: str = 'Mean',
) -> pd.DataFrame:
    """
    Return a DataFrame with [date_col, value_col] aggregated per
    calendar day/period, ready for a time-series line chart.
    """
    if df is None or df.empty or date_col not in df.columns or value_col not in df.columns:
        return pd.DataFrame()

    working = df[[date_col, value_col]].copy()
    if not pd.api.types.is_datetime64_any_dtype(working[date_col]):
        working[date_col] = pd.to_datetime(working[date_col], errors="coerce")
    working = working.dropna(subset=[date_col])
    if working.empty:
        return pd.DataFrame()

    grouped = working.groupby(working[date_col].dt.date)[value_col]
    if aggregation == "Sum":
        result = grouped.sum()
    elif aggregation == "Count":
        result = grouped.count()
    else:
        result = grouped.mean()
    result = result.reset_index()
    result.columns = [date_col, value_col]
    return result.sort_values(date_col)


def compute_correlation_matrix(df: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    """Correlation matrix (pandas DataFrame) for the given numeric columns."""
    if df is None or df.empty or not columns:
        return pd.DataFrame()
    valid_cols = [c for c in columns if c in df.columns]
    if len(valid_cols) < 2:
        return pd.DataFrame()
    return df[valid_cols].corr(numeric_only=True)
