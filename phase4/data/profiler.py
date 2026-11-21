"""
data/profiler.py
==================
Dataset profiling functions for AnalyticsPro: row/column counts,
missing/duplicate summaries, column classification, numeric and
categorical statistics, outlier detection and automatic insights.

These functions work independently of Streamlit and can be reused
anywhere a description of a DataFrame's shape or quality is needed.
"""

from __future__ import annotations

from typing import Any, NamedTuple

import numpy as np
import pandas as pd

from utils.helpers import (
    categorical_columns,
    format_bytes,
    get_column_types,
    numeric_columns,
)

# ---------------------------------------------------------------------
# Column classification helpers
# ---------------------------------------------------------------------

def infer_column_role(series: pd.Series) -> str:
    """Classify a single column as Numeric / Date-Time / Categorical.
    Booleans are two-valued labels, so they are Categorical (consistent with the
    column counts in dataset_metrics / profile_dataset)."""
    if pd.api.types.is_bool_dtype(series):
        return "Categorical"
    if pd.api.types.is_numeric_dtype(series):
        return "Numeric"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "Date/Time"
    return "Categorical"


# ---------------------------------------------------------------------
# High-level summaries
# ---------------------------------------------------------------------

def profile_dataset(df: pd.DataFrame) -> dict:
    """
    High-level overview metrics used across the app: rows, columns,
    missing cells, duplicate rows, and column-type counts, plus a
    human-readable memory-usage string.
    """
    if df is None or df.empty:
        return {
            "rows": 0, "columns": 0, "missing": 0, "duplicates": 0,
            "numeric": 0, "categorical": 0, "datetime": 0, "memory": "0 B"
        }
    numeric_cnt = len(df.select_dtypes(include=["number"]).columns)
    datetime_cnt = len(df.select_dtypes(include=["datetime", "datetimetz"]).columns)
    categorical_cnt = max(len(df.columns) - numeric_cnt - datetime_cnt, 0)
    try:
        mem_bytes = int(df.memory_usage(deep=True).sum())
    except Exception:
        mem_bytes = int(df.memory_usage(deep=False).sum())
    return {
        "rows": len(df),
        "columns": len(df.columns),
        "missing": int(df.isna().sum().sum()),
        "duplicates": int(df.duplicated().sum()),
        "numeric": numeric_cnt,
        "categorical": categorical_cnt,
        "datetime": datetime_cnt,
        "memory": format_bytes(mem_bytes)
    }


def dataset_metrics(df: pd.DataFrame) -> dict:
    """
    Compact metrics dict (rows/columns/numeric/categorical/missing/
    duplicates) used by pages that don't need the full profile_dataset
    breakdown (e.g. top-level KPI strip, EDA header).
    """
    if df is None or df.empty:
        return {
            "rows": 0, "columns": 0, "numeric": 0,
            "categorical": 0, "missing": 0, "duplicates": 0
        }
    col_types = get_column_types(df)
    # Booleans are two-valued labels, so they count as categorical (matches profile_dataset).
    categorical = sum(1 for kind in col_types.values() if kind in ("categorical", "boolean"))
    return {
        "rows": len(df),
        "columns": len(df.columns),
        "numeric": len(df.select_dtypes(include=["number"]).columns),
        "categorical": categorical,
        "missing": int(df.isna().sum().sum()),
        "duplicates": int(df.duplicated().sum())
    }


def calculate_dataset_health(df: pd.DataFrame) -> dict:
    """
    Composite health score (0-100) blending completeness (60%) and
    row-uniqueness (40%), plus a status label.
    """
    if df is None or df.empty:
        return {"overall": 0, "status": "Empty", "completeness": 0, "uniqueness": 0}
    total = df.size
    missing = int(df.isna().sum().sum())
    completeness = round((total - missing) / max(total, 1) * 100, 1)
    duplicates = int(df.duplicated().sum())
    uniqueness = round((len(df) - duplicates) / max(len(df), 1) * 100, 1)
    overall = int(completeness * 0.6 + uniqueness * 0.4)
    return {
        "overall": overall,
        "status": (
            "Excellent" if overall > 85
            else "Good" if overall > 70
            else "Needs Attention"
        ),
        "completeness": completeness,
        "uniqueness": uniqueness
    }


# ---------------------------------------------------------------------
# Column-level profile / quality report
# ---------------------------------------------------------------------

def get_column_profile(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-column profile: name, dtype, inferred role, missing count/%,
    and unique-value count. Used for the Column Summary table.
    """
    rows = []
    for col in df.columns:
        s = df[col]
        missing = int(s.isna().sum())
        rows.append({
            "Column": str(col),
            "Data Type": str(s.dtype),
            "Role": infer_column_role(s),
            "Missing": missing,
            "Missing %": round(missing / max(len(df), 1) * 100, 2),
            "Unique": int(s.nunique(dropna=True))
        })
    return pd.DataFrame(rows)


def get_data_quality_report(df: pd.DataFrame) -> pd.DataFrame:
    """
    Column-level data-quality report including min/max for numeric
    columns. Used by the Data Preparation "Data Quality" tab.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    rows = []
    n = len(df)
    for col in df.columns:
        s = df[col]
        missing = int(s.isna().sum())
        is_num = pd.api.types.is_numeric_dtype(s)
        min_val: Any = "—"
        max_val: Any = "—"
        if is_num:
            valid = s.dropna()
            if not valid.empty:
                try:
                    min_val = round(float(valid.min()), 4)
                    max_val = round(float(valid.max()), 4)
                except Exception:
                    min_val, max_val = "—", "—"
        rows.append({
            "Column": str(col),
            "Data Type": str(s.dtype),
            "Missing Count": missing,
            "Missing %": round(missing / max(n, 1) * 100, 2),
            "Unique Values": int(s.nunique(dropna=True)),
            "Min": min_val,
            "Max": max_val
        })
    return pd.DataFrame(rows)


def get_column_statistics(df: pd.DataFrame, col: str) -> dict:
    """
    Detailed statistics for a single column, shaped differently
    depending on whether it's numeric, datetime, or categorical.
    The returned dict always includes a "type" key.
    """
    s = df[col]
    if pd.api.types.is_numeric_dtype(s):
        count = int(s.count())
        if count == 0:
            return {
                "type": "numeric", "Count": 0, "Mean": "—", "Median": "—",
                "Std Dev": "—", "Min": "—", "Max": "—",
                "25%": "—", "75%": "—",
                "Missing": int(s.isna().sum()), "Unique": 0
            }
        desc = s.describe()
        return {
            "type": "numeric",
            "Count": count,
            "Mean": round(float(desc.get("mean", 0)), 4),
            "Median": round(float(s.median()), 4),
            "Std Dev": round(float(desc.get("std", 0)), 4),
            "Min": round(float(desc.get("min", 0)), 4),
            "Max": round(float(desc.get("max", 0)), 4),
            "25%": round(float(desc.get("25%", 0)), 4),
            "75%": round(float(desc.get("75%", 0)), 4),
            "Missing": int(s.isna().sum()),
            "Unique": int(s.nunique(dropna=True))
        }
    elif pd.api.types.is_datetime64_any_dtype(s):
        valid = s.dropna()
        return {
            "type": "datetime",
            "Min Date": str(valid.min()) if not valid.empty else "—",
            "Max Date": str(valid.max()) if not valid.empty else "—",
            "Missing": int(s.isna().sum()),
            "Unique Dates": int(valid.nunique())
        }
    else:
        mode = s.mode(dropna=True)
        return {
            "type": "categorical",
            "Count": int(s.count()),
            "Unique": int(s.nunique(dropna=True)),
            "Missing": int(s.isna().sum()),
            "Most Frequent": str(mode.iloc[0]) if not mode.empty else "—",
            "Frequency": int((s == mode.iloc[0]).sum()) if not mode.empty else 0
        }


# ---------------------------------------------------------------------
# Numeric / categorical statistics tables
# ---------------------------------------------------------------------

def numeric_statistics(df: pd.DataFrame) -> pd.DataFrame:
    """Summary statistics table for every (non-id) numeric column in df."""
    numeric_cols = numeric_columns(df, exclude_id=False)
    if not numeric_cols:
        return pd.DataFrame()
    result = df[numeric_cols].describe().T
    result["median"] = df[numeric_cols].median(numeric_only=True)
    result["skewness"] = df[numeric_cols].skew(numeric_only=True)
    result["missing"] = df[numeric_cols].isna().sum()
    result["missing %"] = df[numeric_cols].isna().mean() * 100
    result = result.reset_index().rename(columns={"index": "Column"})
    preferred = [
        "Column", "count", "mean", "median", "std",
        "min", "25%", "50%", "75%", "max",
        "skewness", "missing", "missing %"
    ]
    return result[[c for c in preferred if c in result.columns]]


def categorical_statistics(df: pd.DataFrame) -> pd.DataFrame:
    """Summary statistics table for every categorical column in df."""
    categorical_cols = categorical_columns(df)
    if not categorical_cols:
        return pd.DataFrame()
    rows = []
    for col in categorical_cols:
        s = df[col]
        mode = s.mode(dropna=True)
        rows.append({
            "Column": str(col),
            "Unique": int(s.nunique(dropna=True)),
            "Missing": int(s.isna().sum()),
            "Missing %": round(s.isna().mean() * 100, 2),
            "Most Common": str(mode.iloc[0]) if not mode.empty else "—",
            "Frequency": int((s == mode.iloc[0]).sum()) if not mode.empty else 0
        })
    return pd.DataFrame(rows)


class OutlierResult(NamedTuple):
    """Result of detect_outliers: a boolean mask aligned to the input index plus the
    bounds used. q1/q3 are only set for the IQR method."""
    mask: pd.Series
    lower: float
    upper: float
    q1: float | None = None
    q3: float | None = None


def detect_outliers(
    series: pd.Series,
    method: str = 'iqr',
    threshold: float | None = None,
) -> OutlierResult:
    """
    Flag outliers in a numeric Series. This is the single implementation used by
    the EDA summary and the Outlier Detection page.

    method="iqr":    outside [Q1 - k*IQR, Q3 + k*IQR]; threshold is k (default 1.5).
    method="zscore": more than `threshold` sample standard deviations from the mean
                     (default 3.0). A constant column has no outliers.

    Missing values are never outliers. The mask keeps the input's index.
    """
    if method not in ("iqr", "zscore"):
        raise ValueError(f"Unknown outlier method '{method}' (use 'iqr' or 'zscore').")
    clean = series.dropna()
    none_flagged = pd.Series(False, index=series.index)
    if clean.empty:
        return OutlierResult(none_flagged, np.nan, np.nan)

    if method == "iqr":
        k = 1.5 if threshold is None else float(threshold)
        q1, q3 = clean.quantile(0.25), clean.quantile(0.75)
        iqr = q3 - q1
        lower, upper = q1 - k * iqr, q3 + k * iqr
        return OutlierResult((series < lower) | (series > upper), lower, upper, q1, q3)

    limit = 3.0 if threshold is None else float(threshold)
    mean, std = clean.mean(), clean.std()
    if not std or np.isnan(std):
        return OutlierResult(none_flagged, mean, mean)
    z = (series - mean) / std
    return OutlierResult(z.abs() > limit, mean - limit * std, mean + limit * std)


def outlier_summary(df: pd.DataFrame) -> pd.DataFrame:
    """IQR-based outlier summary for every (non-id) numeric column in df."""
    numeric_cols = numeric_columns(df, exclude_id=False)
    rows = []
    for col in numeric_cols:
        if df[col].dropna().empty:
            continue
        result = detect_outliers(df[col], "iqr", 1.5)
        count = int(result.mask.sum())
        rows.append({
            "Column": str(col),
            "Q1": result.q1,
            "Q3": result.q3,
            "IQR": None if result.q1 is None or result.q3 is None else result.q3 - result.q1,
            "Lower Bound": result.lower,
            "Upper Bound": result.upper,
            "Outliers": count,
            "Outlier %": round(count / max(len(df), 1) * 100, 2)
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("Outliers", ascending=False)


def generate_eda_insights(df: pd.DataFrame) -> list[str]:
    """
    Generate a short list of plain-language insights about the
    dataset (missing values, duplicates, variance, category spread,
    overall health) for the Automatic EDA page.
    """
    insights: list[str] = []
    if df is None or df.empty:
        return insights

    numeric_cols = numeric_columns(df, exclude_id=False)
    categorical_cols = categorical_columns(df)
    metrics = dataset_metrics(df)
    health = calculate_dataset_health(df)

    if metrics["missing"] > 0:
        missing = df.isna().sum().sort_values(ascending=False)
        top = missing[missing > 0].head(3)
        for col, count in top.items():
            pct = count / max(len(df), 1) * 100
            insights.append(f"**{col}** has {int(count):,} missing values ({pct:.1f}%).")
    else:
        insights.append("The dataset has no missing cells.")

    if metrics["duplicates"] > 0:
        insights.append(f"The dataset contains {metrics['duplicates']:,} duplicate rows.")
    else:
        insights.append("No duplicate rows were detected.")

    if numeric_cols:
        variances = df[numeric_cols].var(numeric_only=True).sort_values(ascending=False)
        if not variances.empty:
            col = variances.index[0]
            insights.append(f"**{col}** has the highest variance among the numeric columns.")

        ranges = {}
        for col in numeric_cols:
            s = df[col].dropna()
            if not s.empty:
                ranges[col] = float(s.max() - s.min())
        if ranges:
            col = max(ranges, key=lambda name: ranges[name])
            insights.append(f"**{col}** has the widest observed numeric range ({ranges[col]:,.2f}).")

    if categorical_cols:
        col = max(categorical_cols, key=lambda c: df[c].nunique(dropna=True))
        unique = int(df[col].nunique(dropna=True))
        insights.append(f"**{col}** has the largest number of distinct categorical values ({unique:,}).")

        mode = df[col].mode(dropna=True)
        if not mode.empty:
            count = int((df[col] == mode.iloc[0]).sum())
            pct = count / max(len(df), 1) * 100
            insights.append(
                f"The most common value in **{col}** is **{str(mode.iloc[0])}** ({pct:.1f}% of rows)."
            )

    insights.append(
        f"Overall dataset health is **{health['overall']}/100** and classified as **{health['status']}**."
    )
    return insights[:8]


def correlation_strength(value: float) -> str:
    """Label a correlation coefficient, e.g. 0.82 -> "Strong Positive", -0.2 -> "Weak Negative".

    Bands: |r| > 0.7 strong, > 0.3 moderate, otherwise weak; the sign gives Positive/Negative.
    """
    magnitude = abs(value)
    band = "Strong" if magnitude > 0.7 else "Moderate" if magnitude > 0.3 else "Weak"
    return f"{band} {'Positive' if value >= 0 else 'Negative'}"


def correlated_pairs(corr: pd.DataFrame, threshold: float) -> list[dict]:
    """Column pairs whose absolute correlation is at least ``threshold``.

    ``corr`` is a square correlation matrix; each pair appears once (upper triangle).
    Missing coefficients are skipped. Returns dicts with Feature A/B, Correlation, Strength.
    """
    pairs: list[dict] = []
    columns = list(corr.columns)
    for i in range(len(columns)):
        for j in range(i + 1, len(columns)):
            value = corr.iloc[i, j]
            if pd.notna(value) and abs(value) >= threshold:
                pairs.append({
                    "Feature A": columns[i],
                    "Feature B": columns[j],
                    "Correlation": round(float(value), 3),
                    "Strength": correlation_strength(float(value)),
                })
    return pairs
