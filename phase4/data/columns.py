"""
data/columns.py
===============
Decide what each column is *for*: a measure you can average, a category you can
group by, an identifier you should not average, a date, and so on.

Several pages (Ask Your Data, chart defaults, suggestions) share this so an
``order_id`` column is never offered as "the metric to analyse" just because it
is the first numeric column.

Pure pandas; no Streamlit imports.
"""
from __future__ import annotations

import re

import pandas as pd

from data.loader import detect_datetime_columns
from utils.helpers import looks_like_id_name

#: Every role ``classify_columns`` can return.
ROLES: tuple[str, ...] = (
    "measure", "category", "date", "identifier", "high_cardinality",
    "text", "boolean", "constant", "empty",
)

#: A column with more distinct values than this is too crowded to group by.
MAX_CATEGORY_VALUES = 50
#: Columns whose values are almost all different look like identifiers / free text.
_UNIQUE_RATIO = 0.9
_MIN_ROWS_FOR_RATIO = 20


def _is_whole_numbers(values: pd.Series) -> bool:
    """True when every non-missing number is a whole number (1, 2, 3.0, ...)."""
    clean = values.dropna()
    if clean.empty:
        return False
    if pd.api.types.is_integer_dtype(clean):
        return True
    try:
        return bool(((clean % 1) == 0).all())
    except (TypeError, ValueError):
        return False


def _looks_like_sequence(values: pd.Series) -> bool:
    """True for row-number style columns: sorted, or whole numbers packed densely.

    Distinguishes ``1..1000`` (an ID) from ``salary`` values such as 41000, 52500,
    ... which are also unique whole numbers but spread over a wide range.
    """
    clean = values.dropna()
    if clean.empty:
        return False
    if clean.is_monotonic_increasing or clean.is_monotonic_decreasing:
        return True
    span = float(clean.max() - clean.min()) + 1
    return span <= 1.5 * len(clean)


def _mostly_unique(values: pd.Series, unique: int) -> bool:
    """True when nearly every non-missing value is different."""
    count = int(values.notna().sum())
    return count >= _MIN_ROWS_FOR_RATIO and unique / count > _UNIQUE_RATIO


def _classify_text_column(name: str, values: pd.Series, unique: int) -> str:
    """Role of a text column: identifier, text, high_cardinality or category."""
    if looks_like_id_name(name):
        return "identifier"
    if _mostly_unique(values, unique):
        sample = values.dropna().astype(str).head(200)
        if sample.str.contains(r"\s").mean() > 0.5 or sample.str.len().mean() > 30:
            return "text"
        return "identifier"
    n = int(values.notna().sum())
    if unique > MAX_CATEGORY_VALUES or (n >= _MIN_ROWS_FOR_RATIO and unique / n > 0.5):
        return "high_cardinality"
    return "category"


def classify_columns(df: pd.DataFrame) -> dict[str, str]:
    """Return ``{column_name: role}`` for every column (see ``ROLES``).

    Rules, in order: all-missing -> ``empty``; real or parseable dates ->
    ``date``; booleans -> ``boolean``; a single distinct value -> ``constant``;
    numeric columns are an ``identifier`` when their name says so (id, code,
    key, index...) or they are whole numbers that are almost all different and
    run in sequence (row numbers),
    otherwise a ``measure``; text columns are an ``identifier``, ``text``,
    ``high_cardinality`` or ``category`` depending on name and uniqueness.
    """
    if df is None or len(df.columns) == 0:
        return {}
    dates = set(detect_datetime_columns(df)) if len(df) else set()
    roles: dict[str, str] = {}
    for col in df.columns:
        series = df[col]
        name = str(col)
        if series.notna().sum() == 0:
            roles[col] = "empty"
        elif col in dates:
            roles[col] = "date"
        elif pd.api.types.is_bool_dtype(series):
            roles[col] = "boolean"
        elif series.nunique(dropna=True) <= 1:
            roles[col] = "constant"
        elif pd.api.types.is_numeric_dtype(series):
            unique = int(series.nunique(dropna=True))
            if looks_like_id_name(name) or (
                _is_whole_numbers(series) and _mostly_unique(series, unique)
                and _looks_like_sequence(series)
            ):
                roles[col] = "identifier"
            else:
                roles[col] = "measure"
        else:
            roles[col] = _classify_text_column(name, series, int(series.nunique(dropna=True)))
    return roles


def columns_by_role(df: pd.DataFrame) -> dict[str, list]:
    """Group column names by role, e.g. ``{"measure": ["sales"], "category": ["region"], ...}``.

    Every role in ``ROLES`` is present (possibly with an empty list); columns
    keep their original left-to-right order.
    """
    grouped: dict[str, list] = {role: [] for role in ROLES}
    for col, role in classify_columns(df).items():
        grouped[role].append(col)
    return grouped


_PREFERRED_MEASURE_WORDS = (
    "revenue", "sales", "amount", "total", "profit", "salary", "income", "spend",
    "cost", "score", "mark", "marks", "value", "quantity", "price",
)


def rank_measures(measures: list) -> list:
    """Put business-like measures (revenue, sales, salary...) before the rest.

    Earlier words in ``_PREFERRED_MEASURE_WORDS`` rank higher; columns that match
    nothing keep their original order after them (the sort is stable).
    """
    def rank(name) -> int:
        tokens = set(re.split(r"[^a-z0-9]+", str(name).lower()))
        hits = [i for i, word in enumerate(_PREFERRED_MEASURE_WORDS) if word in tokens]
        return min(hits) if hits else len(_PREFERRED_MEASURE_WORDS)
    return sorted(measures, key=rank)


def measure_first(df: pd.DataFrame, numeric: list) -> list:
    """Order numeric columns so real measures come first, identifiers last.

    Nothing is removed (a user can still pick an ID column on purpose); this only
    changes which column a page selects *by default*. Within the measure group,
    business-like names (revenue, sales, salary...) come first.
    """
    roles = classify_columns(df[list(numeric)]) if len(numeric) else {}
    measures = rank_measures([c for c in numeric if roles.get(c) == "measure"])
    return measures + [c for c in numeric if c not in measures]
