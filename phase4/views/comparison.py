"""Dataset Comparison page: primary dataset vs one secondary upload, by size, missing cells, health and column names."""

from __future__ import annotations

import logging
from html import escape

import pandas as pd
import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile

from data.loader import load_dataset
from data.profiler import calculate_dataset_health, dataset_metrics
from views.common import (
    badge_html,
    card_container,
    render_html,
    render_page_intro,
    render_section_heading,
)

logger = logging.getLogger("analyticspro.comparison")


def _difference_badge(label: str, diff: int, *, lower_is_better: bool = False, higher_is_better: bool = False) -> str:
    """A pill such as 'Rows -118'. Colour: green = better, red = worse, grey = no judgement (size, column count)."""
    if diff == 0:
        tone = "neutral"
    elif lower_is_better:
        tone = "success" if diff < 0 else "danger"
    elif higher_is_better:
        tone = "success" if diff > 0 else "danger"
    else:
        tone = "info"
    return badge_html(f"{label} {diff:+,}" if diff else f"{label} no change", tone)


def _dataset_heading(role: str, name: str, tone: str) -> str:
    return f'{badge_html(role, tone)} <code>{escape(str(name))}</code>'


def _render_upload_section() -> UploadedFile | None:
    render_section_heading("Secondary dataset", "Upload a second CSV or Excel file to compare against your active dataset.")
    with card_container("compare_upload"):
        second_file = st.file_uploader("Choose a second CSV or Excel file", type=["csv", "xlsx", "xls"], key="second_dataset_file")
        st.caption("The secondary file is read for this comparison only. It does not replace your active dataset.")
    return second_file


def _render_overview(df: pd.DataFrame, df_2: pd.DataFrame, second_name: str) -> None:
    m1, m2 = dataset_metrics(df), dataset_metrics(df_2)
    h1, h2 = calculate_dataset_health(df), calculate_dataset_health(df_2)

    render_section_heading("Side-by-side overview", "Secondary values show the difference from the primary dataset beneath each number.")
    c1, c2 = st.columns(2)
    with c1, card_container("compare_primary"):
        render_html(_dataset_heading("Primary", st.session_state.get("dataset_name", "Dataset 1"), "info"))
        st.metric("Rows", f"{m1['rows']:,}")
        st.metric("Columns", f"{m1['columns']:,}")
        st.metric("Missing Cells", f"{m1['missing']:,}")
        st.metric("Health Score", f"{h1['overall']}/100")

    with c2, card_container("compare_secondary"):
        render_html(_dataset_heading("Secondary", second_name, "success"))
        st.metric("Rows", f"{m2['rows']:,}", delta=f"{m2['rows'] - m1['rows']:,}")
        st.metric("Columns", f"{m2['columns']:,}", delta=f"{m2['columns'] - m1['columns']:,}")
        st.metric("Missing Cells", f"{m2['missing']:,}", delta=f"{m2['missing'] - m1['missing']:,}", delta_color="inverse")
        st.metric("Health Score", f"{h2['overall']}/100", delta=f"{h2['overall'] - h1['overall']}")

    render_html(
        '<div class="ap-topbar-aside" role="group" aria-label="Differences, secondary minus primary">'
        + _difference_badge("Rows", m2["rows"] - m1["rows"])
        + _difference_badge("Columns", m2["columns"] - m1["columns"])
        + _difference_badge("Missing cells", m2["missing"] - m1["missing"], lower_is_better=True)
        + _difference_badge("Health", h2["overall"] - h1["overall"], higher_is_better=True)
        + "</div>"
    )
    st.caption("Differences are secondary minus primary. Green is better (fewer missing cells, higher health); size changes are not judged.")


def _render_common_columns(df: pd.DataFrame, df_2: pd.DataFrame) -> None:
    common_cols = sorted(set(df.columns).intersection(df_2.columns), key=str)
    render_section_heading(f"Common Columns ({len(common_cols)})", "Columns whose names match exactly in both datasets.")
    with card_container("compare_common"):
        if common_cols:
            st.write(", ".join([f"`{c}`" for c in common_cols]))
            st.caption(f"{len(common_cols):,} of {len(df.columns):,} primary and {len(df_2.columns):,} secondary column names match. "
                       "Names are compared exactly; columns are not matched or merged any other way.")
        else:
            st.warning("No overlapping column names were found between the two datasets.")


def render_dataset_comparison_page(df: pd.DataFrame) -> None:
    render_page_intro("Compare your active dataset with a second file by size, missing cells, health score and shared column names.")

    if df is None or df.empty:
        st.info("Upload a primary dataset first to enable comparison.")
        return

    second_file = _render_upload_section()

    if second_file is not None:
        try:
            df_2 = load_dataset(second_file)
            _render_overview(df, df_2, second_file.name)
            _render_common_columns(df, df_2)
        except ValueError as exc:
            st.error(f"Could not read the second dataset. {exc}")
        except Exception:
            logger.exception("Unexpected error comparing datasets")
            st.error("Could not compare these datasets. Check that the second file is a valid CSV or Excel file.")
    else:
        st.info("Upload a second dataset above to view side-by-side metric comparison.")
