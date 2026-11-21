"""
data/cleaner.py
=================
Data-cleaning logic for AnalyticsPro: missing values, duplicates,
text/numeric cleaning, datatype conversion, column management and
cleaning reports.

No Streamlit widgets live in this module — every function takes a
DataFrame (and plain parameters) and returns a DataFrame (and/or a
plain dict report), so the Data Preparation page in app.py only has
to wire these functions to widgets and session state.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger("analyticspro.cleaner")


# ---------------------------------------------------------------------
# Missing values
# ---------------------------------------------------------------------

def analyze_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-column missing-value breakdown as a DataFrame with
    Column / Missing Count / Missing % / Data Type.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    n = len(df)
    rows = []
    for col in df.columns:
        missing = int(df[col].isna().sum())
        if missing == 0:
            continue
        rows.append({
            "Column": str(col),
            "Data Type": str(df[col].dtype),
            "Missing Count": missing,
            "Missing %": round(missing / max(n, 1) * 100, 2)
        })
    if not rows:
        return pd.DataFrame(columns=["Column", "Data Type", "Missing Count", "Missing %"])
    return pd.DataFrame(rows).sort_values("Missing Count", ascending=False).reset_index(drop=True)

def _numeric_fill_value(s: pd.Series, strategy: str, custom: Any, col: str) -> tuple[Any, str | None]:
    """Value used to fill a numeric column, or ``(None, warning)`` when it cannot be chosen.

    An invalid custom value never invents a number: the column is left untouched and a
    warning says why.
    """
    if strategy == "Mean":
        return s.mean(), None
    if strategy == "Zero":
        return 0, None
    if strategy == "Custom value":
        try:
            return float(custom), None
        except (TypeError, ValueError):
            return None, f"'{custom}' is not a valid number, so column '{col}' was not filled."
    return s.median(), None          # "Median" and any unknown strategy


def _categorical_fill_value(s: pd.Series, strategy: str, custom: Any) -> Any:
    """Value used to fill a text/category column ("Mode", "Unknown" or a custom value)."""
    if strategy == "Mode":
        mode = s.mode(dropna=True)
        return mode.iloc[0] if not mode.empty else "Unknown"
    if strategy == "Custom value":
        return custom if custom else "Unknown"
    return "Unknown"


def fill_missing_values(
    df: pd.DataFrame,
    selected_columns: Sequence[str],
    numeric_strategy: str,
    numeric_custom: Any,
    categorical_strategy: str,
    categorical_custom: Any,
) -> tuple[pd.DataFrame, dict]:
    """
    Apply a missing-value treatment strategy to selected_columns.

    Numeric columns use numeric_strategy ("Mean" / "Median" / "Zero" /
    "Custom value" / "Drop rows"); non-numeric columns use
    categorical_strategy ("Mode" / "Unknown" / "Custom value" /
    "Drop rows"). Returns (cleaned_df, report_dict). The report's
    "warnings" list describes anything that could not be applied (for
    example a non-numeric custom value for a numeric column).
    """
    cleaned = df.copy()
    filled_numeric = 0
    filled_categorical = 0
    dropped_rows = 0
    before_rows = len(cleaned)
    drop_cols = []
    warnings = []

    for col in selected_columns:
        if col not in cleaned.columns:
            continue
        s = cleaned[col]
        missing_count = int(s.isna().sum())
        if missing_count == 0:
            continue

        is_num = pd.api.types.is_numeric_dtype(s)
        strategy = numeric_strategy if is_num else categorical_strategy
        if strategy == "Drop rows":
            drop_cols.append(col)
            continue

        if is_num:
            value, warning = _numeric_fill_value(s, strategy, numeric_custom, col)
            if warning:
                warnings.append(warning)
            elif pd.notna(value):
                cleaned[col] = s.fillna(value)
                filled_numeric += missing_count
        else:
            cleaned[col] = s.fillna(_categorical_fill_value(s, strategy, categorical_custom))
            filled_categorical += missing_count

    if drop_cols:
        cleaned = cleaned.dropna(subset=drop_cols).reset_index(drop=True)
        dropped_rows = before_rows - len(cleaned)

    report = {
        "filled_numeric": filled_numeric,
        "filled_categorical": filled_categorical,
        "dropped_rows": dropped_rows,
        "warnings": warnings,
    }
    return cleaned, report


# ---------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------

def detect_duplicates(df: pd.DataFrame) -> tuple[int, float]:
    """Return (duplicate_count, duplicate_percentage) for df."""
    if df is None or df.empty:
        return 0, 0.0
    count = int(df.duplicated().sum())
    pct = round(count / max(len(df), 1) * 100, 2)
    return count, pct


def remove_duplicates(df: pd.DataFrame, action: str) -> tuple[pd.DataFrame, int]:
    """
    Remove duplicate rows according to `action`:
    "Keep first occurrence" or "Keep last occurrence".
    Returns (cleaned_df, removed_count). Any other action is a no-op.
    """
    cleaned = df.copy()
    removed = 0
    if action == "Keep first occurrence":
        before = len(cleaned)
        cleaned = cleaned.drop_duplicates(keep="first").reset_index(drop=True)
        removed = before - len(cleaned)
    elif action == "Keep last occurrence":
        before = len(cleaned)
        cleaned = cleaned.drop_duplicates(keep="last").reset_index(drop=True)
        removed = before - len(cleaned)
    return cleaned, removed


# ---------------------------------------------------------------------
# Column management
# ---------------------------------------------------------------------

def drop_columns(df: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    """Drop the given columns (missing names are silently ignored)."""
    return df.drop(columns=columns, errors="ignore")


def rename_column(df: pd.DataFrame, old_name: str, new_name: str) -> pd.DataFrame:
    """Rename a single column. Returns the updated DataFrame."""
    return df.rename(columns={old_name: new_name})


def reorder_columns(df: pd.DataFrame, new_order: Sequence[str]) -> pd.DataFrame:
    """
    Reorder columns, placing `new_order` first and any remaining
    columns (in their original order) after it.
    """
    remaining = [c for c in df.columns if c not in new_order]
    return df[list(new_order) + remaining]


def convert_column_type(
    df: pd.DataFrame,
    col: str,
    target_type: str,
    allow_data_loss: bool = False,
) -> tuple[pd.DataFrame, str | None]:
    """
    Convert a single column to target_type ("Integer" / "Float" /
    "String" / "Category" / "DateTime" / "Boolean").

    Returns (updated_df, error_message). error_message is None on
    success. On failure the column is left unchanged and the message
    explains why.

    Conversions to Integer / Float / DateTime / Boolean are refused when
    they would turn existing values into missing values, unless
    `allow_data_loss=True` is passed explicitly. (Values that were already
    missing do not count as loss.)
    """
    cleaned = df.copy()
    original = cleaned[col].copy()
    try:
        if target_type == "Integer":
            converted = pd.to_numeric(original, errors="coerce").astype("Int64")
        elif target_type == "Float":
            converted = pd.to_numeric(original, errors="coerce").astype(float)
        elif target_type == "String":
            converted = original.astype(str)
        elif target_type == "Category":
            converted = original.astype("category")
        elif target_type == "DateTime":
            converted = pd.to_datetime(original, errors="coerce")
        elif target_type == "Boolean":
            converted = original.map(
                lambda x: True if str(x).strip().lower() in ["true", "1", "yes", "y"]
                else (False if str(x).strip().lower() in ["false", "0", "no", "n"] else None)
            )
        else:
            return cleaned, f"Unknown target type '{target_type}'."

        if target_type in ("Integer", "Float", "DateTime", "Boolean") and not allow_data_loss:
            lost = int(converted.isna().sum() - original.isna().sum())
            if lost > 0:
                return cleaned, (
                    f"{lost} value(s) in '{col}' cannot be converted to {target_type} and "
                    "would become missing"
                )
        cleaned[col] = converted
        return cleaned, None
    except (ValueError, TypeError, OverflowError) as exc:
        logger.warning("Column conversion failed (%s) target=%s", type(exc).__name__, target_type)
        cleaned[col] = original
        return cleaned, f"the values do not fit the {target_type} type"


# ---------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------

def clean_text_columns(
    df: pd.DataFrame,
    columns: Sequence[str],
    operations: Sequence[str],
) -> pd.DataFrame:
    """
    Apply a set of text-cleaning operations to the given columns.
    Supported operations: "strip", "lower", "upper", "dedupe_spaces",
    "empty_to_nan".
    """
    cleaned = df.copy()
    for col in columns:
        if col not in cleaned.columns:
            continue
        s = cleaned[col].astype("string")
        if "strip" in operations:
            s = s.str.strip()
        if "lower" in operations:
            s = s.str.lower()
        if "upper" in operations:
            s = s.str.upper()
        if "dedupe_spaces" in operations:
            s = s.str.replace(r"\s+", " ", regex=True)
        if "empty_to_nan" in operations:
            s = s.replace("", pd.NA)
        cleaned[col] = s.astype(object).where(s.notna(), None)
    return cleaned


# ---------------------------------------------------------------------
# Numeric cleaning
# ---------------------------------------------------------------------

def numeric_quality_scan(df: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    """
    Scan numeric columns for negative values, infinite values, and
    statistical outliers (|z-score| > 4). Returns a summary DataFrame.
    """
    rows = []
    for col in columns:
        s = df[col]
        try:
            s_float = s.astype(float)
        except Exception:
            s_float = pd.to_numeric(s, errors="coerce")
        negatives = int((s < 0).sum()) if pd.api.types.is_numeric_dtype(s) else 0
        infinite = int(np.isinf(s_float).sum())
        valid = s_float.replace([np.inf, -np.inf], np.nan).dropna()
        extreme = 0
        if not valid.empty and valid.std(ddof=0) > 0:
            z = (valid - valid.mean()) / valid.std(ddof=0)
            extreme = int((z.abs() > 4).sum())
        rows.append({
            "Column": str(col),
            "Negative Values": negatives,
            "Infinite Values": infinite,
            "Extreme Values (|z|>4)": extreme
        })
    return pd.DataFrame(rows)


def fix_infinite_values(df: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    """Replace +/- infinity with NaN in the given numeric columns."""
    cleaned = df.copy()
    for col in columns:
        if col in cleaned.columns:
            cleaned[col] = cleaned[col].replace([np.inf, -np.inf], np.nan)
    return cleaned


# ---------------------------------------------------------------------
# Composite cleaning / reporting
# ---------------------------------------------------------------------

def clean_dataframe(
    df: pd.DataFrame,
    missing_strategy: str = 'Fill missing values',
    numeric_strategy: str = 'Median',
    categorical_strategy: str = 'Mode',
    duplicate_action: str = 'Remove duplicate rows',
    selected_columns: Sequence[str] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """
    One-shot "quick clean" that applies a sensible default treatment
    in a single call: remove duplicate rows, then fill (or drop)
    missing values across selected_columns (defaults to all columns).

    Returns (cleaned_df, report_dict) where report_dict summarizes
    what changed, for use in cleaning-history / before-after displays.
    """
    cleaned = df.copy()
    report = {
        "before_rows": len(cleaned),
        "before_missing": int(cleaned.isna().sum().sum()),
        "before_duplicates": int(cleaned.duplicated().sum()),
        "filled_numeric": 0,
        "filled_categorical": 0,
        "removed_duplicates": 0,
        "dropped_rows": 0
    }

    cols = selected_columns if selected_columns else list(cleaned.columns)

    if duplicate_action == "Remove duplicate rows":
        cleaned, removed = remove_duplicates(cleaned, "Keep first occurrence")
        report["removed_duplicates"] = removed

    if missing_strategy == "Drop rows with missing values":
        before = len(cleaned)
        cleaned = cleaned.dropna(subset=cols).reset_index(drop=True)
        report["dropped_rows"] = before - len(cleaned)
    elif missing_strategy == "Fill missing values":
        cleaned, fill_report = fill_missing_values(
            cleaned, cols, numeric_strategy, None, categorical_strategy, None
        )
        report["filled_numeric"] = fill_report["filled_numeric"]
        report["filled_categorical"] = fill_report["filled_categorical"]
        report["dropped_rows"] += fill_report["dropped_rows"]

    report["after_rows"] = len(cleaned)
    report["after_missing"] = int(cleaned.isna().sum().sum())
    report["after_duplicates"] = int(cleaned.duplicated().sum())
    return cleaned, report


def generate_cleaning_report(before_metrics: dict, after_metrics: dict) -> dict:
    """
    Compare two "overview metrics" dicts (as produced by
    data.profiler.profile_dataset) and summarize the delta.
    """
    return {
        "rows_removed": before_metrics["rows"] - after_metrics["rows"],
        "columns_removed": before_metrics["columns"] - after_metrics["columns"],
        "missing_repaired": before_metrics["missing"] - after_metrics["missing"],
        "duplicates_removed": before_metrics["duplicates"] - after_metrics["duplicates"]
    }
