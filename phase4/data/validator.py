"""
data/validator.py
===================
Safe validation for datasets loaded into AnalyticsPro. These checks
make sure the application never crashes because of a bad dataset —
every function here inspects the DataFrame and reports problems
instead of raising.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _duplicate_column_names(df: pd.DataFrame) -> list[str]:
    """Column names that appear more than once (compared as text)."""
    names = pd.Series(df.columns.astype(str))
    return names[names.duplicated()].unique().tolist()


def _null_only_columns(df: pd.DataFrame) -> list[str]:
    """Columns whose every value is missing. Iterates by position because with duplicate
    column names ``df[name]`` would return a DataFrame."""
    return [str(c) for i, c in enumerate(df.columns) if df.iloc[:, i].isna().all()]


def _empty_string_columns(df: pd.DataFrame) -> list[str]:
    """Text columns in which every non-missing value is an empty/blank string."""
    found = []
    for i, col in enumerate(df.columns):
        series = df.iloc[:, i]
        if not (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
            continue
        non_null = series.dropna()
        if not non_null.empty and (non_null.astype(str).str.strip() == "").all():
            found.append(str(col))
    return found


def validate_dataframe(df: pd.DataFrame) -> dict:
    """
    Run a full battery of structural checks on a DataFrame and return
    a dict describing what (if anything) is wrong with it:

        {
            "is_valid": bool,
            "is_empty": bool,
            "empty_columns": [...],
            "null_only_columns": [...],
            "duplicate_column_names": [...],
            "warnings": ["human readable message", ...]
        }

    `is_valid` is False only for structural problems that could break
    the rest of the app (an empty dataframe, or duplicate column
    names); everything else is surfaced as a non-blocking warning.
    """
    result: dict[str, Any] = {
        "is_valid": True,
        "is_empty": False,
        "empty_columns": [],
        "null_only_columns": [],
        "duplicate_column_names": [],
        "warnings": []
    }

    if df is None or df.empty:
        result["is_valid"] = False
        result["is_empty"] = True
        result["warnings"].append("The dataset has no rows.")
        return result

    if len(df.columns) == 0:
        result["is_valid"] = False
        result["warnings"].append("The dataset has no columns.")
        return result

    dupes = _duplicate_column_names(df)
    if dupes:
        result["is_valid"] = False
        result["duplicate_column_names"] = dupes
        result["warnings"].append(
            f"Duplicate column name(s) detected: {', '.join(dupes)}. "
            "Rename or remove them before continuing."
        )

    null_only = _null_only_columns(df)
    if null_only:
        result["null_only_columns"] = null_only
        result["warnings"].append(
            f"{len(null_only)} column(s) contain only missing values: {', '.join(null_only)}."
        )

    empty_cols = _empty_string_columns(df)
    if empty_cols:
        result["empty_columns"] = empty_cols
        result["warnings"].append(
            f"{len(empty_cols)} column(s) contain only empty strings: {', '.join(empty_cols)}."
        )

    return result


def detect_problematic_columns(df: pd.DataFrame) -> list:
    """
    Detect columns likely to cause downstream problems: mixed
    Python object types, infinite numeric values, or dtypes pandas
    can't cleanly summarize. Returns a list of dicts:

        [{"column": "...", "issue": "mixed_types" | "infinite_values" | "unsupported_dtype"}]
    """
    if df is None or df.empty:
        return []

    problems = []
    for i, col in enumerate(df.columns):
        s = df.iloc[:, i]

        if pd.api.types.is_object_dtype(s):
            non_null = s.dropna()
            if not non_null.empty:
                type_names = non_null.map(lambda v: type(v).__name__).unique()
                if len(type_names) > 1:
                    problems.append({"column": str(col), "issue": "mixed_types"})
                    continue

        if pd.api.types.is_numeric_dtype(s):
            try:
                if np.isinf(s.astype(float)).any():
                    problems.append({"column": str(col), "issue": "infinite_values"})
                    continue
            except Exception:
                pass

        if s.dtype == object:
            try:
                s.astype(str)
            except Exception:
                problems.append({"column": str(col), "issue": "unsupported_dtype"})

    return problems


def validate_column_conversion(df: pd.DataFrame, col: str, target_type: str) -> tuple[bool, str]:
    """
    Pre-check whether converting `col` to `target_type` is likely to
    succeed, without mutating anything. Returns (is_safe, message).
    `is_safe=False` doesn't block the conversion (the caller still
    handles failures gracefully) — it's meant to warn the user ahead
    of time.
    """
    if col not in df.columns:
        return False, f"Column '{col}' does not exist."

    s = df[col]

    if target_type in ("Integer", "Float"):
        coerced = pd.to_numeric(s, errors="coerce")
        failures = int(coerced.isna().sum() - s.isna().sum())
        if failures > 0:
            return False, (
                f"{failures} value(s) in '{col}' are not numeric and will "
                "become missing after conversion."
            )

    elif target_type == "DateTime":
        coerced = pd.to_datetime(s, errors="coerce")
        failures = int(coerced.isna().sum() - s.isna().sum())
        if failures > 0:
            return False, (
                f"{failures} value(s) in '{col}' don't look like dates and "
                "will become missing after conversion."
            )

    elif target_type == "Boolean":
        allowed = {"true", "1", "yes", "y", "false", "0", "no", "n"}
        non_null = s.dropna().astype(str).str.strip().str.lower()
        unrecognized = int((~non_null.isin(allowed)).sum())
        if unrecognized > 0:
            return False, (
                f"{unrecognized} value(s) in '{col}' aren't recognizable "
                "booleans and will become missing after conversion."
            )

    return True, "This conversion looks safe."
