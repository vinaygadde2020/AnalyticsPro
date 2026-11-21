"""
utils/dataframe_utils.py
==========================
Safe DataFrame-display utilities.

This module exists to solve `pyarrow.lib.ArrowInvalid` errors that
occur when Streamlit's `st.dataframe()` tries to convert a column
containing mixed Python object types (e.g. a mix of str and int in
the same object column) to Arrow.

IMPORTANT: this module does NOT convert every column to strings.
Integers, floats, booleans and datetime columns are always left
untouched. Only object/mixed-type columns that would actually break
Arrow conversion are sanitized.
"""

from __future__ import annotations

import pandas as pd


def safe_numeric_conversion(series: pd.Series) -> pd.Series:
    """
    Attempt to coerce a Series to numeric. Values that can't be
    parsed become NaN. Never raises.
    """
    return pd.to_numeric(series, errors="coerce")


def detect_mixed_object_columns(df: pd.DataFrame) -> list:
    """
    Identify object-dtype columns that are likely to break PyArrow's
    dataframe conversion: columns whose non-null values are made up
    of more than one underlying Python type, or of a type Arrow can't
    represent (e.g. dict, list, set).

    Returns a list of column names. Pure-string object columns,
    numeric, boolean, category, and datetime columns are never
    flagged.
    """
    if df is None or df.empty:
        return []

    arrow_unfriendly_types = {"dict", "list", "set", "tuple", "bytearray"}
    flagged = []

    for col in df.columns:
        s = df[col]
        if not pd.api.types.is_object_dtype(s):
            continue

        non_null = s.dropna()
        if non_null.empty:
            continue

        type_names = set(non_null.map(lambda v: type(v).__name__).unique())

        if len(type_names) > 1 or type_names & arrow_unfriendly_types:
            flagged.append(col)

    return flagged


def convert_problematic_objects(series: pd.Series) -> pd.Series:
    """
    Safely convert a single problematic object Series into something
    PyArrow/Streamlit can render.

    Strategy:
        1. If every non-null value can be coerced to numeric without
           losing any originally-valid value, return the numeric
           series (this keeps e.g. an accidentally-object int/float
           column numeric instead of turning it into strings).
        2. Otherwise, stringify every non-null value individually
           (so mixed str/int/dict cells all become plain strings)
           while preserving actual missing values as None.
    """
    non_null_mask = series.notna()

    if non_null_mask.any():
        numeric_attempt = safe_numeric_conversion(series)
        # Safe only if coercion didn't turn any originally-present
        # value into a new NaN.
        newly_missing = numeric_attempt.isna() & non_null_mask
        if not newly_missing.any():
            return numeric_attempt

    return series.map(lambda x: None if pd.isna(x) else str(x)).astype(object)


def sanitize_for_streamlit(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a copy of df where only the columns flagged by
    detect_mixed_object_columns() have been sanitized. Every other
    column (including clean string columns, numeric, boolean,
    category, and datetime columns) is returned unchanged.
    """
    if df is None:
        return df

    result = df.copy()
    for col in detect_mixed_object_columns(result):
        result[col] = convert_problematic_objects(result[col])
    return result


def safe_dataframe(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """
    Public entry point used by app.py right before every
    st.dataframe() call. Thin, null-safe wrapper around
    sanitize_for_streamlit() so callers don't need to guard against
    df being None.
    """
    if df is None:
        return None
    return sanitize_for_streamlit(df)
