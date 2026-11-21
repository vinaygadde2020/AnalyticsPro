"""Unit tests for data/loader.py (file reading and load-time preparation)."""
import io

import pandas as pd
import pytest

from data import loader
from data.loader import load_dataset
from tests.conftest import csv_bytes, named_buffer


def ld(text_or_bytes, name="t.csv"):
    data = text_or_bytes if isinstance(text_or_bytes, bytes) else csv_bytes(text_or_bytes)
    return load_dataset(named_buffer(data, name))


# ----------------------------------------------------------------- delimiters
@pytest.mark.parametrize("delim", [";", "\t", "|"])
def test_non_comma_delimiters_are_detected(delim):
    text = delim.join(["id", "name", "score"]) + "\n" + "\n".join(
        delim.join([str(i), f"n{i}", str(i * 2)]) for i in range(10))
    df = ld(text)
    assert list(df.columns) == ["id", "name", "score"] and len(df) == 10


def test_comma_csv_is_unchanged_and_quoted_commas_survive():
    df = ld('id,note\n1,"a, b"\n2,"c, d"\n')
    assert list(df.columns) == ["id", "note"] and df["note"].tolist() == ["a, b", "c, d"]


def test_single_column_csv_stays_single_column():
    df = ld("only\n1\n2\n3\n")
    assert list(df.columns) == ["only"] and len(df) == 3


def test_semicolon_inside_quoted_comma_field_does_not_confuse_detection():
    df = ld('a,b\n"x;y",1\n"p;q",2\n')
    assert list(df.columns) == ["a", "b"]


# ------------------------------------------------------------------ encodings
def test_utf8_bom_is_stripped_from_first_header():
    df = ld("id,val\n1,2\n".encode("utf-8-sig"))
    assert list(df.columns) == ["id", "val"]


def test_windows_1252_smart_quotes_decode_correctly():
    raw = "name\n\u201cquoted\u201d caf\u00e9\n".encode("cp1252")
    assert ld(raw).iloc[0, 0] == "\u201cquoted\u201d caf\u00e9"


def test_latin1_only_bytes_still_load():
    df = ld(b"name\nfoo\x81bar\n")  # 0x81 is undefined in cp1252, valid in latin-1
    assert len(df) == 1


# ------------------------------------------------------------- bad / odd input
def test_empty_file_raises_readable_error():
    with pytest.raises(ValueError, match="Could not read CSV"):
        ld(b"")


def test_header_only_csv_gives_zero_rows():
    df = ld("a,b\n")
    assert list(df.columns) == ["a", "b"] and len(df) == 0


def test_unsupported_extension_is_rejected():
    with pytest.raises(ValueError, match="Unsupported file type"):
        load_dataset(named_buffer(b"x", "notes.txt"))


def test_corrupt_excel_raises_value_error_not_a_crash():
    with pytest.raises(ValueError):
        load_dataset(named_buffer(b"not,an,excel", "bad.xlsx"))


def test_duplicate_and_blank_headers_are_made_unique_or_named():
    df = ld("a,a,\n1,2,3\n")
    assert len(set(df.columns)) == 3 and all(str(c).strip() for c in df.columns)


def test_column_name_whitespace_is_stripped():
    assert list(ld(" a , b \n1,2\n").columns) == ["a", "b"]


# ---------------------------------------------------------------------- Excel
def _xlsx(sheets: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for name, frame in sheets.items():
            frame.to_excel(w, sheet_name=name, index=False)
    return buf.getvalue()


def test_xlsx_roundtrip():
    src = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    df = ld(_xlsx({"Data": src}), "t.xlsx")
    assert df["a"].tolist() == [1, 2, 3] and df["b"].tolist() == ["x", "y", "z"]


def test_legacy_xls_loads():
    xlwt = pytest.importorskip("xlwt")
    wb = xlwt.Workbook()
    ws = wb.add_sheet("s")
    for j, h in enumerate(["a", "b"]):
        ws.write(0, j, h)
    for i, (x, y) in enumerate([(1, "p"), (2, "q")], start=1):
        ws.write(i, 0, x)
        ws.write(i, 1, y)
    buf = io.BytesIO()
    wb.save(buf)
    df = ld(buf.getvalue(), "legacy.xls")
    assert list(df.columns) == ["a", "b"] and len(df) == 2


def test_multi_sheet_workbook_loads_first_sheet_and_lists_all_sheets():
    data = _xlsx({"First": pd.DataFrame({"a": [1, 2]}), "Second": pd.DataFrame({"b": [9, 9, 9]})})
    assert list(ld(data, "t.xlsx").columns) == ["a"]
    assert loader.excel_sheet_names(named_buffer(data, "t.xlsx")) == ["First", "Second"]


def test_excel_sheet_names_returns_empty_list_for_garbage():
    assert loader.excel_sheet_names(named_buffer(b"garbage", "t.xlsx")) == []


# ------------------------------------------------------------ datetime logic
def test_real_dates_are_converted():
    df = ld("d,v\n" + "\n".join(f"2024-01-{i % 28 + 1:02d},{i}" for i in range(30)))
    assert pd.api.types.is_datetime64_any_dtype(df["d"])


def test_text_ids_with_digits_are_not_turned_into_dates():
    # 4-digit ids plus one non-numeric id -> object column. Must stay text.
    ids = [str(1001 + i) for i in range(25)] + ["x1"]
    df = ld("pid,v\n" + "\n".join(f"{p},{i}" for i, p in enumerate(ids)))
    assert not pd.api.types.is_datetime64_any_dtype(df["pid"])
    assert df["pid"].tolist() == ids, "id values must be preserved exactly"


def test_month_year_labels_are_still_detected_as_dates():
    df = ld("m,v\n" + "\n".join(f"Jan 2024,{i}" for i in range(30)))
    assert pd.api.types.is_datetime64_any_dtype(df["m"])


def test_detect_datetime_columns_ignores_numeric_and_empty():
    assert loader.detect_datetime_columns(pd.DataFrame()) == []
    assert loader.detect_datetime_columns(pd.DataFrame({"n": [1, 2, 3]})) == []
    assert loader.detect_datetime_columns(None) == []


def test_prepare_loaded_dataframe_does_not_mutate_input():
    raw = pd.DataFrame({" a ": [1, 2], "d": ["2024-01-01", "2024-01-02"]})
    snapshot = raw.copy(deep=True)
    loader.prepare_loaded_dataframe(raw)
    assert raw.equals(snapshot) and list(raw.columns) == list(snapshot.columns)
