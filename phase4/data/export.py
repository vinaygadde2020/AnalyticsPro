"""
data/export.py
==============
Helpers for building downloadable files (CSV / Excel) and safe download names.

No Streamlit imports. The byte builders are meant to be passed to
``st.download_button(data=<callable>)`` so a file is only generated when the
user actually clicks Download, not on every page rerun.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import UTC, datetime
from importlib.util import find_spec

import pandas as pd

_DATA_EXTENSIONS = (".csv", ".xlsx", ".xls")


def download_stem(dataset_name: str | None) -> str:
    """
    A safe base name for download files: the dataset name without its data-file
    extension (so we never produce 'sales.csv_cleaned.csv'), without any
    directory part ('../../etc/x.csv' -> 'x') and without control characters.
    Falls back to 'dataset'.
    """
    name = re.split(r"[\\/]", str(dataset_name or ""))[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    for ext in _DATA_EXTENSIONS:
        if name.lower().endswith(ext):
            name = name[: -len(ext)]
            break
    name = name.strip().strip(".")
    return name or "dataset"


def dataframe_to_csv_bytes(frame: pd.DataFrame) -> bytes:
    """UTF-8 CSV bytes (no index column)."""
    return frame.to_csv(index=False).encode("utf-8")


def excel_export_available() -> bool:
    """True when the optional 'openpyxl' package is installed."""
    return find_spec("openpyxl") is not None


def dataframe_to_excel_bytes(frame: pd.DataFrame, sheet_name: str = 'Cleaned Data') -> bytes:
    """XLSX bytes with a single sheet (no index column)."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name=sheet_name)
    return buffer.getvalue()


def dataframe_to_powerbi_workbook_bytes(
    frame: pd.DataFrame,
    column_profile: pd.DataFrame | None = None,
) -> bytes:
    """Build a Power BI-friendly Excel workbook with data, profile, KPI and guide sheets."""
    buffer = io.BytesIO()
    profile = column_profile if column_profile is not None else pd.DataFrame({
        "Column": [str(c) for c in frame.columns],
        "Data Type": [str(frame[c].dtype) for c in frame.columns],
        "Missing": [int(frame[c].isna().sum()) for c in frame.columns],
        "Unique": [int(frame[c].nunique(dropna=True)) for c in frame.columns],
    })
    numeric = frame.select_dtypes(include="number")
    kpis = pd.DataFrame([
        {"Metric": "Rows", "Value": int(len(frame)), "Description": "Number of records in the exported dataset"},
        {"Metric": "Columns", "Value": int(len(frame.columns)), "Description": "Number of fields"},
        {"Metric": "Missing Cells", "Value": int(frame.isna().sum().sum()), "Description": "Total blank / null cells"},
        {"Metric": "Duplicate Rows", "Value": int(frame.duplicated().sum()), "Description": "Rows duplicated across all columns"},
        {"Metric": "Numeric Columns", "Value": int(len(numeric.columns)), "Description": "Fields detected as numeric"},
    ])
    guide = pd.DataFrame([
        {"Page": "Executive Overview", "Visual / Element": "KPI cards", "Suggested fields / measure": "Rows, Columns, Missing Cells, Duplicate Rows", "Purpose": "High-level dataset status"},
        {"Page": "Category Analysis", "Visual / Element": "Clustered bar chart", "Suggested fields / measure": "Choose a categorical field + a numeric field", "Purpose": "Compare values across categories"},
        {"Page": "Trend Analysis", "Visual / Element": "Line chart", "Suggested fields / measure": "Choose a date field + numeric field", "Purpose": "Show changes over time"},
        {"Page": "Data Quality", "Visual / Element": "Table / bar chart", "Suggested fields / measure": "Column, Missing, Missing %, Unique", "Purpose": "Find incomplete or high-cardinality fields"},
        {"Page": "Slicers", "Visual / Element": "Date, category, region slicers", "Suggested fields / measure": "Use available date and categorical columns", "Purpose": "Filter visuals across report pages"},
        {"Page": "Model setup", "Visual / Element": "Power Query", "Suggested fields / measure": "Check data types and blanks after import", "Purpose": "Validate the imported data"},
    ])
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="Data")
        profile.to_excel(writer, index=False, sheet_name="Column Profile")
        kpis.to_excel(writer, index=False, sheet_name="KPI Summary")
        guide.to_excel(writer, index=False, sheet_name="Power BI Guide")
    return buffer.getvalue()

def powerbi_starter_pack_bytes(
    frame: pd.DataFrame,
    dataset_name: str = 'dataset',
    column_profile: pd.DataFrame | None = None,
) -> bytes:
    """Create a ZIP starter pack for building a Power BI report (not a .pbix file)."""
    buffer = io.BytesIO()
    stem = download_stem(dataset_name)
    profile = column_profile if column_profile is not None else pd.DataFrame({
        "Column": [str(c) for c in frame.columns],
        "Data Type": [str(frame[c].dtype) for c in frame.columns],
        "Missing": [int(frame[c].isna().sum()) for c in frame.columns],
        "Unique": [int(frame[c].nunique(dropna=True)) for c in frame.columns],
    })
    numeric_cols = [str(c) for c in frame.select_dtypes(include="number").columns]
    date_cols = [str(c) for c in frame.columns if pd.api.types.is_datetime64_any_dtype(frame[c])]
    categorical_cols = [str(c) for c in frame.columns if c not in numeric_cols and c not in date_cols]
    readme = f"""AnalyticsPro Power BI Starter Pack
Dataset: {stem}
Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}

FILES
- {stem}_data.csv: processed data to import into Power BI Desktop
- column_profile.csv: data types, missing counts and unique counts
- kpi_summary.csv: dataset-level KPI values
- dashboard_build_guide.md: suggested pages, visuals, KPIs and slicers
- suggested_fields.json: detected numeric, date and categorical columns

IMPORTANT
This is a Power BI-ready starter pack, not a native .pbix dashboard file. Open Power BI Desktop, use Get Data > Text/CSV to import the data, then build visuals using the guide.
"""
    kpis = pd.DataFrame([
        {"KPI": "Total Rows", "Value": int(len(frame))},
        {"KPI": "Total Columns", "Value": int(len(frame.columns))},
        {"KPI": "Missing Cells", "Value": int(frame.isna().sum().sum())},
        {"KPI": "Duplicate Rows", "Value": int(frame.duplicated().sum())},
    ])
    guide = f"""# Power BI Dashboard Build Guide\n\n## Suggested report pages\n1. **Executive Overview** — KPI cards for Total Rows, Total Columns, Missing Cells and Duplicate Rows.\n2. **Category Analysis** — clustered bar chart using a categorical field and a numeric field.\n3. **Trend Analysis** — line chart using a date field and numeric measure, if a date field exists.\n4. **Data Quality** — column profile table and missing-value bar chart.\n\n## Suggested slicers\n- Date slicer: {', '.join(date_cols) if date_cols else 'No date columns detected; add a slicer for a suitable categorical field.'}\n- Category slicers: {', '.join(categorical_cols[:8]) if categorical_cols else 'No categorical fields detected.'}\n\n## Numeric fields\n{', '.join(numeric_cols) if numeric_cols else 'No numeric fields detected.'}\n\n## Suggested DAX measures\n```DAX\nTotal Rows = COUNTROWS('Data')\nMissing Cells = SUM('Column Profile'[Missing])\nDuplicate Rows = COUNTROWS('Data') - COUNTROWS(DISTINCT('Data'))\n```\nReview table names and DAX definitions after importing; these are starting templates and may need adjustment for your data model.\n"""
    fields = {"numeric_columns": numeric_cols, "date_columns": date_cols, "categorical_columns": categorical_cols}
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{stem}_data.csv", dataframe_to_csv_bytes(frame))
        zf.writestr("column_profile.csv", dataframe_to_csv_bytes(profile))
        zf.writestr("kpi_summary.csv", dataframe_to_csv_bytes(kpis))
        zf.writestr("dashboard_build_guide.md", guide)
        zf.writestr("suggested_fields.json", json.dumps(fields, indent=2))
        zf.writestr("README.txt", readme)
    return buffer.getvalue()
