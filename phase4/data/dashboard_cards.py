"""
data/dashboard_cards.py
=======================
The numbers behind the dashboard's cards: KPI cards, a category composition (donut),
data-quality checks, a completeness ring and a "latest records" table.

Everything here is plain pandas and returns plain Python values, so it is unit-tested
without Streamlit; ``views/dashboard_ui.py`` turns the results into HTML.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from data.aggregation import aggregate_values, group_aggregate, normalize_aggregation
from data.loader import detect_datetime_columns

#: A card value is "good" at or above this share of complete cells / valid dates.
GOOD_SHARE = 0.98
REVIEW_SHARE = 0.90


def compact_number(value: float | None) -> str:
    """Short human-readable number: 1,234 -> "1.23K", 4.38e7 -> "43.8M". None -> an em dash."""
    if value is None or pd.isna(value) or np.isinf(value):
        return "—"
    magnitude = abs(float(value))
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if magnitude >= limit:
            return f"{value / limit:,.2f}{suffix}"
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"


def delta_percent(current: float | None, baseline: float | None) -> float | None:
    """Percentage change from ``baseline`` to ``current``; None if either is missing or baseline is 0."""
    if current is None or baseline is None or pd.isna(current) or pd.isna(baseline) or baseline == 0:
        return None
    return (float(current) - float(baseline)) / abs(float(baseline)) * 100


def _direction(change: float | None) -> str:
    if change is None or abs(change) < 1e-9:
        return "flat"
    return "up" if change > 0 else "down"


def completeness_summary(df: pd.DataFrame) -> dict:
    """Cell and row completeness plus duplicate rows.

    Keys: total_rows, total_cells, missing_cells, complete_pct (share of non-missing cells, 0-100),
    complete_rows, rows_with_gaps, duplicate_rows, complete_rows_pct.
    """
    rows, cols = df.shape
    cells = rows * cols
    missing = int(df.isna().sum().sum()) if cells else 0
    complete_rows = int((~df.isna().any(axis=1)).sum()) if rows else 0
    return {
        "total_rows": rows,
        "total_cells": cells,
        "missing_cells": missing,
        "complete_pct": (1 - missing / cells) * 100 if cells else 100.0,
        "complete_rows": complete_rows,
        "rows_with_gaps": rows - complete_rows,
        "duplicate_rows": int(df.duplicated().sum()) if rows else 0,
        "complete_rows_pct": complete_rows / rows * 100 if rows else 0.0,
    }


def _card(key: str, label: str, value: str, caption: str, delta: float | None, delta_text: str, note: str,
          tone: str = "neutral") -> dict:
    """One KPI card. ``direction`` is the arrow (up/down/flat); ``tone`` is the colour (good/bad/neutral).

    Only completeness is judged good or bad; a filtered view having fewer rows than the full dataset is
    not bad news, so the other cards stay neutral.
    """
    return {"key": key, "label": label, "value": value, "caption": caption, "delta_text": delta_text,
            "delta_note": note, "direction": _direction(delta), "tone": tone}


def kpi_cards(full: pd.DataFrame, filtered: pd.DataFrame, metric: str | None, aggregation: str,
              category: str | None) -> list[dict]:
    """The four headline cards: records, the chosen metric, completeness and distinct segments.

    Each card compares the filtered view with the full dataset (``delta_text`` / ``direction``).
    """
    cards: list[dict] = []
    diff_rows = len(filtered) - len(full)
    cards.append(_card("records", "Total Records", f"{len(filtered):,}", "Rows in the current view", diff_rows,
                       f"{diff_rows:+,}", "vs full dataset"))

    if metric and metric in filtered.columns:
        label = normalize_aggregation(aggregation)
        now = aggregate_values(filtered[metric], aggregation)
        base = aggregate_values(full[metric], aggregation)
        change = delta_percent(now, base)
        cards.append(_card("metric", f"{label} {metric}", compact_number(now), f"{metric}, current view", change,
                           "—" if change is None else f"{change:+.1f}%", "vs full dataset"))
    else:
        numeric = sum(pd.api.types.is_numeric_dtype(filtered[c]) for c in filtered.columns)
        cards.append(_card("metric", "Numeric Columns", f"{numeric:,}", "Available to analyse", 0, "—", ""))

    now_c, base_c = completeness_summary(filtered), completeness_summary(full)
    pp = now_c["complete_pct"] - base_c["complete_pct"]
    cards.append(_card("completeness", "Data Completeness", f"{now_c['complete_pct']:.1f}%",
                       f"{now_c['missing_cells']:,} missing cells", pp, f"{pp:+.1f} pp", "vs full dataset",
                       tone="neutral" if abs(pp) < 1e-9 else "good" if pp > 0 else "bad"))

    if category and category in filtered.columns:
        now_n, base_n = int(filtered[category].nunique()), int(full[category].nunique())
        cards.append(_card("segments", f"Distinct {category}", f"{now_n:,}", "Segments in the current view",
                           now_n - base_n, f"{now_n - base_n:+,}", "vs full dataset"))
    else:
        cards.append(_card("segments", "Columns", f"{filtered.shape[1]:,}", "In the active dataset", 0, "—", ""))
    return cards


def composition(df: pd.DataFrame, category: str | None, metric: str | None, aggregation: str,
                top_n: int = 5) -> dict:
    """Share of a total by category, for the donut.

    Shares must add up, so this is always a *sum* (or a row count when ``aggregation`` is Count or no metric
    is chosen), whatever aggregation the dashboard uses elsewhere. The largest ``top_n`` categories are kept
    and the rest are grouped as "Other". Returns ``{"items": [{label, value, share}], "total", "basis", "note"}``;
    ``items`` is empty (with a ``note``) when a composition cannot be drawn.
    """
    empty = {"items": [], "total": 0.0, "basis": "", "note": None}
    if not category or category not in df.columns or df.empty:
        return {**empty, "note": "Choose a category in “Segment by” to see a composition."}
    if not metric or normalize_aggregation(aggregation) == "Count":
        grouped, name = group_aggregate(df, [category], category, "Count")
        basis = "Records"
    else:
        grouped, name = group_aggregate(df, [category], metric, "Sum")
        basis = f"Total {metric}"
    grouped = grouped.dropna(subset=[name])
    grouped[category] = grouped[category].astype(object).where(grouped[category].notna(), "(missing)").astype(str)
    if grouped.empty:
        return {**empty, "note": "There are no values to compare."}
    if (grouped[name] < 0).any():
        return {**empty, "note": "A composition needs non-negative totals; this metric has negative sums."}
    grouped = grouped[grouped[name] > 0].sort_values(name, ascending=False)
    if grouped.empty:
        return {**empty, "note": "All totals are zero."}
    total = float(grouped[name].sum())
    head, tail = grouped.head(top_n), grouped.iloc[top_n:]
    items = [{"label": str(row[category]), "value": float(row[name]), "share": float(row[name]) / total}
             for _, row in head.iterrows()]
    if not tail.empty:
        other = float(tail[name].sum())
        items.append({"label": "Other", "value": other, "share": other / total})
    return {"items": items, "total": total, "basis": basis, "note": None}


def _status(share: float) -> str:
    return "ok" if share >= GOOD_SHARE else "warn" if share >= REVIEW_SHARE else "bad"


def quality_checks(df: pd.DataFrame, max_checks: int = 5) -> list[dict]:
    """Data-quality checks for the status list: ``{name, detail, status}`` with status ok / warn / bad."""
    if df.empty:
        return []
    summary = completeness_summary(df)
    checks = [{"name": "Completeness", "detail": f"{summary['complete_pct']:.1f}% of cells filled",
               "status": _status(summary["complete_pct"] / 100)}]
    dup = summary["duplicate_rows"]
    checks.append({"name": "Duplicate rows", "detail": "None found" if not dup else f"{dup:,} repeated rows",
                   "status": "ok" if not dup else "warn"})
    gaps = [c for c in df.columns if df[c].isna().mean() > 0.2]
    checks.append({"name": "Missing-value hotspots",
                   "detail": "No column over 20% missing" if not gaps else f"{len(gaps)} column(s) over 20% missing",
                   "status": "ok" if not gaps else "warn"})
    dates = detect_datetime_columns(df)
    if dates:
        valid = float(np.mean([pd.to_datetime(df[c], errors="coerce").notna().mean() for c in dates]))
        checks.append({"name": "Date validity", "detail": f"{valid * 100:.1f}% valid dates", "status": _status(valid)})
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
    bad_numbers = int(sum(np.isinf(pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float, na_value=np.nan)).sum()
                          for c in numeric))
    checks.append({"name": "Numeric validity", "detail": "No infinite values" if not bad_numbers else f"{bad_numbers:,} infinite values",
                   "status": "ok" if not bad_numbers else "bad"})
    constant = [c for c in df.columns if df[c].nunique(dropna=True) <= 1]
    checks.append({"name": "Useful columns", "detail": "Every column varies" if not constant else f"{len(constant)} constant/empty column(s)",
                   "status": "ok" if not constant else "warn"})
    return checks[:max_checks]


def latest_records(df: pd.DataFrame, date_col: str | None = None, n: int = 5, max_columns: int = 7) -> pd.DataFrame:
    """The ``n`` newest rows by ``date_col`` (or the first rows when there is no usable date column).

    Only the first ``max_columns`` columns are returned so the table stays readable.
    """
    view = df.iloc[:, :max_columns]
    if date_col and date_col in df.columns:
        parsed = pd.to_datetime(df[date_col], errors="coerce")
        if parsed.notna().any():
            order = parsed.sort_values(ascending=False, na_position="last").index
            return view.loc[order].head(n)
    return view.head(n)
