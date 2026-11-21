"""Tests for data/export.py."""
import io

import pandas as pd
import pytest

from data import export


@pytest.mark.parametrize("name,expected", [
    ("sales.csv", "sales"), ("Report.XLSX", "Report"), ("legacy.xls", "legacy"),
    ("no_extension", "no_extension"), ("name with spaces.csv", "name with spaces"),
    ("data.backup.csv", "data.backup"), ("archive.tar.csv", "archive.tar"),
    ("../../etc/passwd.csv", "passwd"), ("C:\\Users\\me\\q3 sales.xlsx", "q3 sales"),
    ("a/b/c.csv", "c"), ("bell\x07name.csv", "bellname"),
    ("", "dataset"), (None, "dataset"), (".csv", "dataset"), ("...", "dataset"), ("  .xlsx ", "dataset"),
])
def test_download_stem(name, expected):
    assert export.download_stem(name) == expected


def test_download_stem_never_contains_path_separators():
    for nasty in ("../x.csv", "..\\x.csv", "/abs/x.csv", "a/../../b.csv"):
        stem = export.download_stem(nasty)
        assert "/" not in stem and "\\" not in stem and stem


def test_csv_bytes_roundtrip_without_index():
    df = pd.DataFrame({"a": [1, 2], "b": ["x,y", "é"]})
    out = pd.read_csv(io.BytesIO(export.dataframe_to_csv_bytes(df)))
    assert out.equals(df) and "Unnamed" not in "".join(out.columns)


def test_excel_bytes_roundtrip_and_sheet_name():
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    assert export.excel_export_available()
    data = export.dataframe_to_excel_bytes(df)
    assert pd.read_excel(io.BytesIO(data), sheet_name="Cleaned Data").equals(df)
    custom = export.dataframe_to_excel_bytes(df, sheet_name="Mine")
    assert list(pd.read_excel(io.BytesIO(custom), sheet_name=None)) == ["Mine"]


def test_powerbi_workbook_contains_expected_sheets():
    df = pd.DataFrame({"Region": ["East", "West"], "Sales": [10, 20]})
    data = export.dataframe_to_powerbi_workbook_bytes(df)
    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)
    assert set(sheets) == {"Data", "Column Profile", "KPI Summary", "Power BI Guide"}
    assert sheets["Data"].equals(df)
    assert "Total Rows" not in sheets["KPI Summary"].columns
    assert "Metric" in sheets["KPI Summary"].columns


def test_powerbi_starter_pack_contains_data_and_guidance():
    import zipfile
    df = pd.DataFrame({"Region": ["East", "West"], "Sales": [10, 20]})
    data = export.powerbi_starter_pack_bytes(df, "sales.csv")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
        assert "sales_data.csv" in names
        assert "column_profile.csv" in names
        assert "kpi_summary.csv" in names
        assert "dashboard_build_guide.md" in names
        assert "suggested_fields.json" in names
        guide = archive.read("dashboard_build_guide.md").decode("utf-8")
        assert "slicers" in guide.lower()
        assert "KPI" in guide
