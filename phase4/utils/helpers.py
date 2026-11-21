"""
utils/helpers.py
==================
General-purpose reusable helpers used throughout AnalyticsPro:
number/byte formatting and generic column-type classification.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


def format_number(value: Any, decimals: int = 2) -> str:
    """Format a number with thousands separators, e.g. 1234.5 -> '1,234.50'."""
    try:
        return f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)


def format_bytes(num_bytes: Any) -> str:
    """Format a byte count as a human-readable size string (B/KB/MB/GB/TB)."""
    try:
        size = float(num_bytes)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


# Words that mark a column as an identifier rather than a measurement.
_ID_NAME_TOKENS = frozenset({"id", "ids", "idx", "index", "code", "codes", "uuid", "guid", "key"})


def looks_like_id_name(name: Any) -> bool:
    """
    True when a column NAME marks it as an identifier ("customer_id",
    "customerId", "Row Index", "zip-code"). Matching is by whole word, so
    ordinary measures that merely contain the letters "id" (humidity,
    width, video_views, paid_amount) are NOT treated as identifiers.
    """
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(name))      # split camelCase
    text = re.sub(r"(?<=[A-Za-z])(?=[0-9])|(?<=[0-9])(?=[A-Za-z])", " ", text)  # letters|digits
    tokens = {t for t in re.split(r"[^A-Za-z0-9]+", text.lower()) if t}
    return bool(tokens & _ID_NAME_TOKENS)


def numeric_columns(df: pd.DataFrame, exclude_id: bool = True) -> list:
    """
    List of numeric column names. When exclude_id is True, columns
    whose name marks them as an identifier (the word "id", "index",
    "code", "key"... see looks_like_id_name) are excluded, since they're
    rarely meaningful for statistical analysis.
    """
    if df is None or df.empty:
        return []
    cols = df.select_dtypes(include=["number"]).columns.tolist()
    if exclude_id:
        cols = [c for c in cols if not looks_like_id_name(c)]
    return cols


def categorical_columns(df: pd.DataFrame) -> list:
    """List of object/category/string column names."""
    if df is None or df.empty:
        return []
    return df.select_dtypes(include=["object", "category", "string"]).columns.tolist()


def get_column_types(df: pd.DataFrame) -> dict:
    """
    Classify every column into one of "numeric", "categorical",
    "datetime", or "boolean". Returns a dict {column_name: kind}.
    """
    if df is None or df.empty:
        return {}
    types = {}
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_bool_dtype(s):
            types[str(col)] = "boolean"
        elif pd.api.types.is_numeric_dtype(s):
            types[str(col)] = "numeric"
        elif pd.api.types.is_datetime64_any_dtype(s):
            types[str(col)] = "datetime"
        else:
            types[str(col)] = "categorical"
    return types


_MARKDOWN_SPECIALS = re.compile(r"([\\`*_{}\[\]()#+\-!|<>~])")


def escape_markdown(text: Any) -> str:
    """Backslash-escape Markdown syntax so user-controlled text (column names, cell
    values) is shown literally instead of becoming links, bold text or HTML."""
    return _MARKDOWN_SPECIALS.sub(r"\\\1", str(text))
