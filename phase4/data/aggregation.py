"""
data/aggregation.py
===================
The single place where AnalyticsPro turns "Sum / Average / Median / ..." choices
into numbers. Dashboard KPIs, chart builders and recommendation previews all use
these helpers so a label means the same thing everywhere.

Pure pandas; no Streamlit or plotting imports.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

#: Canonical labels, in the order they are offered to users.
AGGREGATION_LABELS: tuple[str, ...] = ("Sum", "Average", "Median", "Count", "Min", "Max")

_SYNONYMS = {
    "sum": "Sum", "total": "Sum",
    "average": "Average", "mean": "Average", "avg": "Average",
    "median": "Median",
    "count": "Count",
    "min": "Min", "minimum": "Min",
    "max": "Max", "maximum": "Max",
}


def normalize_aggregation(label: str) -> str:
    """Map a user-facing label ("Mean", "Minimum", ...) to a canonical one.

    Raises ValueError for an unknown label so callers never silently fall back
    to a different statistic.
    """
    key = str(label).strip().lower()
    if key not in _SYNONYMS:
        raise ValueError(f"Unknown aggregation '{label}'. Choose one of: {', '.join(AGGREGATION_LABELS)}.")
    return _SYNONYMS[key]


def to_numeric_clean(values: pd.Series) -> pd.Series:
    """Coerce to numbers; text becomes NaN and +/-infinity becomes NaN."""
    return pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)


def aggregate_grouped(grouped: Any, label: str) -> Any:
    """Apply an aggregation to a pandas GroupBy/Resampler of one column.

    Sum uses ``min_count=1`` so a group whose values are all missing stays
    missing instead of showing a misleading 0.
    """
    canonical = normalize_aggregation(label)
    if canonical == "Sum":
        return grouped.sum(min_count=1)
    if canonical == "Average":
        return grouped.mean()
    if canonical == "Median":
        return grouped.median()
    if canonical == "Count":
        return grouped.count()
    if canonical == "Min":
        return grouped.min()
    return grouped.max()


def aggregate_values(values: pd.Series, label: str) -> float | None:
    """Aggregate a whole column to one number (for KPI cards).

    Non-numeric and infinite values are ignored. Returns ``None`` when nothing
    numeric is left, except Count which returns 0.
    """
    canonical = normalize_aggregation(label)
    clean = to_numeric_clean(values).dropna()
    if canonical == "Count":
        return float(clean.count())
    if clean.empty:
        return None
    if canonical == "Sum":
        return float(clean.sum())
    if canonical == "Average":
        return float(clean.mean())
    if canonical == "Median":
        return float(clean.median())
    if canonical == "Min":
        return float(clean.min())
    return float(clean.max())


def group_aggregate(df: pd.DataFrame, keys: list[str], value_col: str, label: str) -> tuple[pd.DataFrame, str]:
    """Group ``df`` by ``keys`` and aggregate ``value_col``.

    Returns ``(frame, value_name)``. ``value_name`` equals ``value_col`` unless
    that column is also a grouping key, in which case it is renamed (for
    example ``"sales (sum)"``) so the two columns do not collide. Values are
    coerced to numbers first, except for Count, which counts any non-missing
    value.
    """
    canonical = normalize_aggregation(label)
    value_name = value_col if value_col not in keys else f"{value_col} ({canonical.lower()})"
    working = df[list(dict.fromkeys(keys))].copy()
    series = df[value_col] if canonical == "Count" else to_numeric_clean(df[value_col])
    working["__value__"] = series.values
    result = aggregate_grouped(working.groupby(keys, dropna=False)["__value__"], canonical)
    return result.rename(value_name).reset_index(), value_name
