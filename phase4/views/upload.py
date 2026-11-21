"""Data Upload & Preview page."""

from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd
import streamlit as st

from data.profiler import calculate_dataset_health, dataset_metrics, get_column_profile
from utils.dataframe_utils import safe_dataframe
from utils.helpers import escape_markdown
from views.common import (
    badge_html,
    card_container,
    card_html,
    goto_page_button,
    hero_html,
    kv_rows_html,
    progress_html,
    render_html,
    render_page_intro,
    render_section_heading,
)


def _upload_fingerprint(uploaded: Any) -> str:
    """Identify an uploaded file by what it contains, not just its name, so a
    changed file that happens to keep the same name is still detected."""
    file_id = getattr(uploaded, "file_id", None)
    if file_id:
        return f"id:{file_id}"
    data = uploaded.getvalue()
    return f"hash:{uploaded.name}:{len(data)}:{hashlib.blake2b(data, digest_size=16).hexdigest()}"


_DELIMITER_NAMES = {",": "Comma (,)", ";": "Semicolon (;)", "\t": "Tab", "|": "Pipe (|)", " ": "Space"}
PREVIEW_ROWS = 15


def _parser_state() -> list[tuple[str, str]]:
    """What the importer actually did for the active file, from the structured record kept at load time."""
    source = (st.session_state.get("import_steps") or {}).get("source") or {}
    pairs: list[tuple[str, str]] = []
    if source.get("format") == "excel":
        pairs.append(("Worksheet", str(source.get("sheet", "—"))))
    elif source.get("format") == "csv":
        delimiter = source.get("delimiter")
        pairs.append(("Delimiter", _DELIMITER_NAMES.get(delimiter, repr(delimiter)) if delimiter is not None else "—"))
        pairs.append(("Character encoding", str(source.get("encoding", "—"))))
    else:
        pairs.append(("Source details", "Not recorded"))
    pairs.append(("Decimal separator", str(st.session_state.get("import_decimal", "Auto-detect")).split("  ")[0]))
    pairs.append(("Leading zeros in codes", "Preserved" if st.session_state.get("import_keep_zeros", True) else "Not preserved"))
    return pairs


def _render_empty_state() -> None:
    render_html(hero_html(
        "☁️", "Upload a dataset to begin",
        "Use the Upload File control in the left sidebar (open the sidebar with the arrow at the top-left on small screens). "
        "Delimiter, encoding and worksheet are detected for you.",
        ["CSV", "XLSX", "XLS", "Up to 200 MB"],
    ))
    a, b, c = st.columns(3)
    a.markdown(card_html("<p>Rows, columns, types, missing values and duplicates.</p>", title="📋 Profile"), unsafe_allow_html=True)
    b.markdown(card_html("<p>EDA, KPIs, distributions, correlations and outliers.</p>", title="📊 Analyze"), unsafe_allow_html=True)
    c.markdown(card_html("<p>Ask plain-English questions (rule-based, runs locally) and export reports.</p>", title="💬 Ask & export"),
               unsafe_allow_html=True)


def _render_file_header(m: dict, h: dict) -> None:
    name = str(st.session_state.get("dataset_name", "Uploaded dataset"))
    badges = badge_html("Uploaded file", "info")
    if st.session_state.get("cleaning_applied"):
        badges += " " + badge_html("Cleaned in session", "warning")
    badges += " " + badge_html(f"Health {h['overall']}/100 · {h['status']}", "success" if h["overall"] > 85 else "warning", dot=True)
    with card_container("upload_file"):
        st.markdown(f"**Active dataset:** `{name}`")
        render_html(badges)
        if st.session_state.get("sheet_notice"):
            st.caption(st.session_state["sheet_notice"])


def _render_metrics(m: dict, h: dict, df: pd.DataFrame) -> None:
    dates = int(sum(pd.api.types.is_datetime64_any_dtype(df[c]) for c in df.columns))
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Rows", f"{m['rows']:,}")
    c2.metric("Columns", f"{m['columns']:,}")
    c3.metric("Numeric", f"{m['numeric']:,}")
    c4.metric("Categorical", f"{m['categorical']:,}")
    c5.metric("Missing", f"{m['missing']:,}")
    c6.metric("Health", f"{h['overall']}/100")
    if dates:
        st.caption(f"{dates} date/time column(s) in the dataset.")


def _render_quality_status(m: dict) -> None:
    if m["missing"] > 0 or m["duplicates"] > 0:
        st.warning(
            f"{m['missing']:,} missing cells and {m['duplicates']:,} duplicate rows detected. "
            "Use Data Preparation before final analysis."
        )
        goto_page_button("Open Data Preparation", "Data Preparation", "upload_goto_prep", primary=True)
    else:
        st.success("Dataset is ready for analysis.")


def _render_import_config() -> None:
    render_section_heading("Import configuration", "How this file was read. Change options in the sidebar under Import options.")
    left, right = st.columns([1, 1])
    with left, card_container("upload_import_how"):
        st.markdown("**Changing import options**")
        st.caption("The worksheet, decimal separator and leading-zero options live in the sidebar. "
                   "Changing one re-reads the original file and discards cleaning steps made so far.")
    with right, card_container("upload_import_state"):
        render_html(kv_rows_html(_parser_state()))


def _render_import_notes() -> None:
    notes = st.session_state.get("import_notes") or []
    if notes:
        with st.expander(f"Import notes ({len(notes)})", expanded=True):
            st.caption("Things the importer changed or could not decide. Your original file is untouched.")
            for note in notes:
                st.markdown(f"- {escape_markdown(note)}")


def _render_preview_and_schema(df: pd.DataFrame, h: dict) -> None:
    left, right = st.columns([1.35, 1])
    with left:
        render_section_heading("Raw data preview", f"First {min(PREVIEW_ROWS, len(df))} of {len(df):,} rows, as parsed.")
        st.dataframe(safe_dataframe(df.head(PREVIEW_ROWS)), width="stretch", height=390)
    with right:
        render_section_heading("Column schema & profile", f"{len(df.columns):,} columns with inferred type and role.")
        st.dataframe(safe_dataframe(get_column_profile(df)), width="stretch", height=390, hide_index=True)
        render_html(progress_html(h["completeness"], "Dataset completeness", f"{h['completeness']}% populated",
                                  "success" if h["completeness"] >= 95 else "warning"))


def render_upload_preview_page(df: pd.DataFrame) -> None:
    render_page_intro("Import a CSV or Excel file, check how it was parsed, and inspect the raw records and column schema "
                      "before any cleaning.")
    if df is None or df.empty:
        _render_empty_state()
        return

    m = dataset_metrics(df)
    h = calculate_dataset_health(df)
    _render_file_header(m, h)
    _render_metrics(m, h, df)
    _render_quality_status(m)
    _render_import_config()
    _render_import_notes()
    _render_preview_and_schema(df, h)
