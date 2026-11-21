"""Export & Reporting page."""

from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from data.export import (
    dataframe_to_csv_bytes,
    dataframe_to_powerbi_workbook_bytes,
    download_stem,
    excel_export_available,
    powerbi_starter_pack_bytes,
)
from data.profiler import get_column_profile
from data.report import generate_html_report
from data.script_export import build_cleaning_script, exportable_steps, unexportable_actions
from views.common import (
    badge_html,
    card_container,
    notice_html,
    render_html,
    render_page_intro,
    render_section_heading,
)


def _card_head(title: str, format_label: str, description: str, includes: str | None = None) -> None:
    """Card heading: title, file-format badge, one-sentence description and (optionally) what the file contains."""
    render_html(
        f'<div class="ap-share-title">{escape(title)}{badge_html(format_label, "info")}</div>'
        + (f'<p class="ap-section-caption">{escape(description)}</p>' if description else "")
        + (f'<p class="ap-small"><strong>Includes:</strong> {escape(includes)}</p>' if includes else "")
    )


def _render_executive_report(df: pd.DataFrame, dataset_name: str) -> None:
    render_section_heading("📄 Automated Executive Report", "The main deliverable: one file you can open or share without this app.")
    with card_container("export_report"):
        _card_head(
            "Executive report", "HTML",
            "Generate and download a self-contained HTML executive summary report featuring dataset metrics, health scores, "
            "and key statistical insights.",
            "a single file with its styles built in; it needs no internet connection to open.",
        )
        st.download_button(
            "📄 Download Executive Report (HTML)",
            data=lambda: generate_html_report(df, dataset_name),
            file_name=f"{download_stem(dataset_name)}_Executive_Report.html",
            mime="text/html",
            type="primary",
            width="stretch", on_click="ignore")


def _render_dataset_downloads(df: pd.DataFrame, dataset_name: str) -> None:
    render_section_heading("📥 Dataset & Profile Downloads", "Plain CSV files (UTF-8, no index column).")
    left, right = st.columns(2)
    with left, card_container("export_csv"):
        _card_head("Processed dataset", "CSV", f"The active dataset as it is now, after any cleaning: {len(df):,} rows × {len(df.columns):,} columns.")
        st.download_button(
            "⬇️ Download Current Processed Dataset (CSV)",
            data=lambda: dataframe_to_csv_bytes(df),
            file_name=f"{download_stem(dataset_name)}_cleaned.csv",
            mime="text/csv",
            width="stretch", on_click="ignore")
    with right, card_container("export_profile"):
        _card_head("Column data profile", "CSV", f"One row per column ({len(df.columns):,}): type, role, missing and unique counts.")
        st.download_button(
            "📋 Download Full Column Data Profile (CSV)",
            data=lambda: dataframe_to_csv_bytes(get_column_profile(df)),
            file_name=f"{download_stem(dataset_name)}_column_profile.csv",
            mime="text/csv",
            width="stretch", on_click="ignore")


def _render_excel_and_powerbi(df: pd.DataFrame, dataset_name: str) -> None:
    render_section_heading("📊 Excel & Power BI Export", "Export the processed data to Excel or download a Power BI starter pack.")
    export_col1, export_col2 = st.columns(2)
    with export_col1, card_container("export_excel"):
        _card_head("Excel workbook", "XLSX", "The processed data in an Excel workbook.",
                   "Data, Column Profile, KPI Summary and Power BI Guide sheets.")
        if excel_export_available():
            st.download_button(
                "📗 Download Excel Workbook",
                data=lambda: dataframe_to_powerbi_workbook_bytes(df, get_column_profile(df)),
                file_name=f"{download_stem(dataset_name)}_AnalyticsPro.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch", on_click="ignore",
                help="Includes Data, Column Profile, KPI Summary and Power BI Guide sheets.")
        else:
            st.warning("Excel export requires openpyxl. Install it with: pip install openpyxl")
    with export_col2, card_container("export_powerbi"):
        _card_head("Power BI starter pack", "ZIP", "A zip of files to import into Power BI Desktop. It is not a Power BI (.pbix) file.",
                   "data CSV, KPI summary, column profile, detected fields and a dashboard/slicer build guide.")
        st.download_button(
            "📊 Download Power BI Starter Pack",
            data=lambda: powerbi_starter_pack_bytes(df, dataset_name, get_column_profile(df)),
            file_name=f"{download_stem(dataset_name)}_PowerBI_Starter_Pack.zip",
            mime="application/zip",
            width="stretch", on_click="ignore",
            help="Includes CSV data, KPI summary, column profile, detected fields and a dashboard/slicer guide.")
    render_html(notice_html(
        "Power BI export is a starter pack, not a native .pbix file. Import the included CSV into Power BI Desktop and follow "
        "the build guide to create visuals, KPI cards and slicers.", "info"))


def _render_cleaning_script_section() -> None:
    """Download (and preview) a standalone pandas script that repeats the import and cleaning steps."""
    history = st.session_state.get("cleaning_history", [])
    source_name = st.session_state.get("uploaded_file_name") or "dataset.csv"
    render_section_heading("🐍 Reproducible Cleaning Script", "Repeat your import and cleaning steps outside this app.")
    script = build_cleaning_script(history, st.session_state.get("import_steps", {}), source_name=source_name)
    stem = download_stem(source_name.rsplit(".", 1)[0])
    steps = len(exportable_steps(history))
    with card_container("export_script"):
        _card_head("Standalone pandas script", "PY", "")
        st.write(
            "Download a standalone Python (pandas) script that repeats how the file was imported and every "
            "cleaning step you applied on the Data Preparation page, in order. Run it on your original file "
            "to get the same cleaned dataset without this app."
        )
        st.download_button(
            "🐍 Download cleaning script (.py)", data=script.encode("utf-8"), file_name=f"{stem}_cleaning_script.py",
            mime="text/x-python", key="export_cleaning_script", on_click="ignore",
        )
        st.caption(f"{steps} cleaning step(s) included. Cleaning done outside the Data Preparation page is not recorded.")
        skipped = unexportable_actions(history)
        if skipped:
            st.warning("These steps could not be exported and appear as comments only: " + "; ".join(skipped))
        with st.expander("Preview the script"):
            st.code(script, language="python")


def render_export_reporting_page(df: pd.DataFrame) -> None:
    render_page_intro("Download your results as an HTML report, CSV or Excel files, a Power BI starter pack, "
                      "or a Python script that repeats your cleaning.")

    if df is None or df.empty:
        st.info("Upload a dataset first.")
        return

    dataset_name = st.session_state.get("dataset_name", "Active_Dataset")
    render_html(badge_html(f"{dataset_name} · {len(df):,} rows × {len(df.columns):,} columns", "info"))

    _render_executive_report(df, dataset_name)
    _render_dataset_downloads(df, dataset_name)
    _render_excel_and_powerbi(df, dataset_name)
    _render_cleaning_script_section()
