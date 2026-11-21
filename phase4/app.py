"""AnalyticsPro entry point: page config, styling, navigation and routing.

Each page lives in its own module under views/."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import streamlit as st

from data.loader import (
    DECIMAL_AUTO,
    DECIMAL_COMMA,
    DECIMAL_POINT,
    excel_sheet_names,
    import_notes,
    import_steps,
    load_dataset,
)
from utils.session_state import (
    clear_dataset_dependent_state,
    initialize_session_state,
    reset_dataset_state,
)
from views.analyst import render_ask_your_data_page
from views.common import (
    badge_html,
    footer_html,
    inject_global_css,
    page_header_html,
    render_html,
    sidebar_brand_html,
)
from views.comparison import render_dataset_comparison_page
from views.correlation import render_correlation_page
from views.data_prep import render_data_prep_page
from views.eda import render_automatic_eda_page
from views.export import render_export_reporting_page
from views.interactive_dashboard import render_interactive_dashboard_page
from views.kpi import render_kpi_dashboard_page
from views.outliers import render_outlier_page
from views.upload import _upload_fingerprint, render_upload_preview_page
from views.visualizations import render_visualizations_page

st.set_page_config(
    page_title="AnalyticsPro — Executive Reporting & Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Shared look and feel (tokens + one stylesheet) lives in views/common.py.
inject_global_css()

logger = logging.getLogger("analyticspro.app")

# Page names that were renamed. Old session values (and bookmarks/tests) keep working.
LEGACY_ROUTES = {"AI Data Analyst": "Ask Your Data"}

# Labels for the "Decimal separator" import option -> loader setting.
DECIMAL_CHOICES = {
    "Auto-detect": DECIMAL_AUTO,
    "Decimal point  (1,234.50)": DECIMAL_POINT,
    "Decimal comma  (1.234,50)": DECIMAL_COMMA,
}


def _import_options(uploaded: Any) -> tuple[Any, str, bool, list]:
    """Sidebar import options for the uploaded file: decimal style, leading zeros, worksheet.

    Returns ``(sheet_name, decimal_mode, keep_leading_zeros, sheet_names)``.
    """
    is_excel = str(uploaded.name).lower().endswith((".xlsx", ".xls"))
    base = _upload_fingerprint(uploaded)
    sheet_names = []
    if is_excel:
        cached = st.session_state.get("_sheet_names_cache")
        if cached and cached[0] == base:
            sheet_names = cached[1]
        else:
            sheet_names = excel_sheet_names(uploaded)
            st.session_state["_sheet_names_cache"] = (base, sheet_names)
    sheet: Any = 0
    with st.sidebar.expander("Import options"):
        if len(sheet_names) > 1:
            sheet = st.selectbox("Worksheet", sheet_names, key=f"import_sheet_{base}",
                                 help="Only the chosen worksheet is loaded.")
        label = st.selectbox("Decimal separator", list(DECIMAL_CHOICES), key="import_decimal",
                             help="Auto-detect converts text like 12,50 only when the format is unambiguous.")
        keep_zeros = st.checkbox("Keep leading zeros (codes, ZIPs)", value=True, key="import_keep_zeros",
                                 help="Numeric-looking codes such as 00123 stay text instead of becoming 123.")
    return sheet, DECIMAL_CHOICES[label], keep_zeros, sheet_names


NAV_ITEMS = [
    ("☁️", "Data Upload & Preview", "Data Upload & Preview"),
    ("🛠️", "Data Preparation", "Data Preparation"),
    ("🔍", "Automatic EDA", "Automatic EDA"),
    ("📌", "KPI Dashboard", "KPI Dashboard"),
    ("🧭", "Interactive Dashboard", "Interactive Dashboard"),
    ("📊", "Visualizations", "Visualizations"),
    ("📈", "Correlation", "Correlation & Relationships"),
    ("⚠️", "Outlier Detection", "Outlier Detection"),
    ("💬", "Ask Your Data", "Ask Your Data"),
    ("🔄", "Dataset Comparison", "Dataset Comparison"),
    ("📁", "Export & Reporting", "Export & Reporting"),
]

PAGE_RENDERERS = {
    "Data Upload & Preview": render_upload_preview_page,
    "Data Preparation": render_data_prep_page,
    "Automatic EDA": render_automatic_eda_page,
    "KPI Dashboard": render_kpi_dashboard_page,
    "Interactive Dashboard": render_interactive_dashboard_page,
    "Visualizations": render_visualizations_page,
    "Correlation & Relationships": render_correlation_page,
    "Outlier Detection": render_outlier_page,
    "Ask Your Data": render_ask_your_data_page,
    "Dataset Comparison": render_dataset_comparison_page,
    "Export & Reporting": render_export_reporting_page,
}


def _render_navigation() -> None:
    """Sidebar brand + one button per page."""
    st.sidebar.markdown(sidebar_brand_html(), unsafe_allow_html=True)
    for icon, label, route in NAV_ITEMS:
        is_current = st.session_state.get("current_page") == route
        if st.sidebar.button(f"{icon}  {label}", key=f"nav_{route}", type="primary" if is_current else "secondary"):
            st.session_state["current_page"] = route
            st.rerun()
    st.sidebar.markdown("<hr>", unsafe_allow_html=True)


def _load_uploaded_file(uploaded: Any) -> None:
    """Load the sidebar upload (honouring the import options) into session state."""
    sheet, decimal_mode, keep_zeros, sheet_names = _import_options(uploaded)
    fingerprint = f"{_upload_fingerprint(uploaded)}|sheet={sheet}|dec={decimal_mode}|zeros={keep_zeros}"
    if st.session_state.get("uploaded_file_fingerprint") == fingerprint:
        return
    try:
        loaded = load_dataset(uploaded, sheet_name=sheet, decimal=decimal_mode, keep_leading_zeros=keep_zeros)
        if len(loaded) == 0:
            raise ValueError("The file has column headers but no data rows.")
        clear_dataset_dependent_state()
        st.session_state.update({
            "df": loaded, "original_df": loaded.copy(),
            "dataset_name": uploaded.name, "uploaded_file_name": uploaded.name,
            "uploaded_file_fingerprint": fingerprint,
            "sheet_notice": f"Workbook has {len(sheet_names)} sheets; loaded '{sheet}'." if len(sheet_names) > 1 else None,
            "import_notes": import_notes(loaded),
            "import_steps": import_steps(loaded),
            "cleaning_applied": False, "cleaning_report": {},
            "current_page": "Data Upload & Preview",
        })
        st.rerun()
    except ValueError as exc:
        # Loader messages are written for users (no paths or stack traces).
        st.sidebar.error(f"Could not load this file. {exc}")
    except Exception:
        logger.exception("Unexpected error while loading an upload")
        st.sidebar.error("Could not load this file. Check that it is a valid CSV or Excel file and try again.")


def _render_dataset_status(df: pd.DataFrame) -> None:
    """Active-dataset caption and the reload button."""
    if df is None:
        return
    st.sidebar.markdown(f"🟢 **Active:** `{len(df):,} rows`")
    if st.session_state.get("sheet_notice"):
        st.sidebar.caption(st.session_state["sheet_notice"])
    if st.sidebar.button("↺ Reload Original Dataset", key="reset_dataset_btn",
                         help="Discard current cleaning changes and reload the original uploaded dataset."):
        reset_dataset_state()
        st.session_state["current_page"] = "Data Upload & Preview"
        st.rerun()


def main() -> None:
    initialize_session_state()
    if st.session_state.get("current_page") in LEGACY_ROUTES:
        st.session_state["current_page"] = LEGACY_ROUTES[st.session_state["current_page"]]

    _render_navigation()
    uploaded = st.sidebar.file_uploader("Upload File", type=["csv", "xlsx", "xls"], key="sidebar_file_uploader")
    if uploaded is not None:
        _load_uploaded_file(uploaded)

    df = st.session_state.get("df")
    _render_dataset_status(df)

    page = st.session_state["current_page"]
    display_names = {route: label for _, label, route in NAV_ITEMS}
    badges = badge_html(f"{len(df):,} rows active", "success", dot=True) if df is not None else badge_html("No dataset loaded", "neutral")
    render_html(page_header_html(display_names.get(page, page), badges_html=badges))

    if df is None and page != "Data Upload & Preview":
        st.info("👋 Upload a CSV or Excel file in the sidebar to begin.")
    else:
        PAGE_RENDERERS.get(page, render_upload_preview_page)(df)

    render_html(footer_html())


if __name__ == "__main__":
    main()
