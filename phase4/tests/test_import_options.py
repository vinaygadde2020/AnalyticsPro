"""Import improvements: leading zeros, decimal commas, Excel worksheets, CSV validation."""
import io

import numpy as np
import pandas as pd
import pytest

from data.loader import (
    DECIMAL_COMMA,
    DECIMAL_POINT,
    convert_decimal_text_columns,
    excel_sheet_names,
    import_notes,
    load_csv,
    load_dataset,
    load_excel,
)
from tests.conftest import named_buffer


def csv(text, name="t.csv", encoding="utf-8"):
    return named_buffer(text.encode(encoding), name)


def xlsx(sheets: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return buf.getvalue()


# ------------------------------------------------------------------ leading zeros
def test_leading_zero_codes_stay_text_and_are_noted():
    df = load_dataset(csv("zip,city,amount\n00123,A,1.5\n01234,B,2.5\n90210,C,3.5\n"))
    assert df["zip"].tolist() == ["00123", "01234", "90210"]
    assert df["amount"].dtype.kind == "f"
    assert any("'zip'" in n and "leading zeros" in n for n in import_notes(df))


def test_ordinary_integers_and_decimals_remain_numeric():
    df = load_dataset(csv("units,price,score\n1,0.5,007.5\n20,1.5,3.5\n"))
    assert pd.api.types.is_numeric_dtype(df["units"]) and pd.api.types.is_numeric_dtype(df["price"])
    assert import_notes(df) == []


def test_zero_value_measure_is_not_mistaken_for_a_code():
    df = load_dataset(csv("n\n0\n5\n10\n"))
    assert pd.api.types.is_numeric_dtype(df["n"])


def test_leading_zero_column_with_missing_values_keeps_missing():
    df = load_dataset(csv("code,v\n007,1\n,2\n042,3\n"))
    assert df["code"].tolist()[0] == "007" and pd.isna(df["code"].iloc[1])


def test_leading_zero_preservation_can_be_switched_off():
    df = load_dataset(csv("zip\n00123\n01234\n"), keep_leading_zeros=False)
    assert df["zip"].tolist() == [123, 1234]


def test_leading_zero_column_is_not_averaged_as_a_measure():
    from data.columns import classify_columns
    df = load_dataset(csv("zip,v\n" + "\n".join(f"{i % 3:05d},{i}" for i in range(40))))
    assert classify_columns(df)["zip"] != "measure"


# ------------------------------------------------------------------ decimal commas
@pytest.mark.parametrize("values,expected", [
    (["12,50", "3,5", "7"], [12.5, 3.5, 7.0]),
    (["1.234,56", "12,5"], [1234.56, 12.5]),
    (["1,234.56", "7.5"], [1234.56, 7.5]),
    (["0,123", "1,5"], [0.123, 1.5]),
    (["1,234,567", "2.5"], [1234567.0, 2.5]),
    (["-3,5", "+2,25"], [-3.5, 2.25]),
])
def test_unambiguous_formats_are_converted_in_auto_mode(values, expected):
    out = convert_decimal_text_columns(pd.DataFrame({"v": values}))
    assert out["v"].tolist() == expected and import_notes(out)


@pytest.mark.parametrize("values", [["1,234", "2,500"], ["1.234", "2.500"]])
def test_ambiguous_formats_are_left_alone_with_a_note(values):
    out = convert_decimal_text_columns(pd.DataFrame({"v": values}))
    assert out["v"].tolist() == values
    if "," in values[0]:
        assert any("could use a decimal comma" in n for n in import_notes(out))


@pytest.mark.parametrize("values", [["12,50", "3.5"], ["abc", "1,5"], ["a,b", "c,d"], ["3.14", "2.71"], ["1.10", "2.5"]])
def test_mixed_or_non_numeric_or_plain_text_is_never_modified(values):
    assert convert_decimal_text_columns(pd.DataFrame({"v": values}))["v"].tolist() == values


def test_user_can_force_a_locale_for_ambiguous_values():
    frame = pd.DataFrame({"v": ["1,234", "2,500"]})
    assert convert_decimal_text_columns(frame, DECIMAL_COMMA)["v"].tolist() == [1.234, 2.5]
    assert convert_decimal_text_columns(frame, DECIMAL_POINT)["v"].tolist() == [1234.0, 2500.0]


def test_forced_locale_still_refuses_columns_that_do_not_fit():
    assert convert_decimal_text_columns(pd.DataFrame({"v": ["1,5", "x"]}), DECIMAL_COMMA)["v"].tolist() == ["1,5", "x"]


def test_invalid_decimal_setting_is_rejected():
    with pytest.raises(ValueError):
        convert_decimal_text_columns(pd.DataFrame({"v": ["1"]}), "semicolon")


def test_missing_values_survive_conversion():
    out = convert_decimal_text_columns(pd.DataFrame({"v": ["1,5", None, "2,5"]}))
    assert out["v"].iloc[0] == 1.5 and pd.isna(out["v"].iloc[1]) and out["v"].iloc[2] == 2.5


def test_semicolon_csv_with_decimal_commas_loads_as_numbers_end_to_end():
    df = load_dataset(csv("product;price;qty\nA;12,50;3\nB;7,25;4\nC;1.234,50;5\n"))
    assert df["price"].tolist() == [12.5, 7.25, 1234.5] and df["qty"].tolist() == [3, 4, 5]


def test_comma_csv_with_quoted_decimal_commas():
    df = load_dataset(csv('product,price\nA,"12,50"\nB,"7,25"\n'))
    assert df["price"].tolist() == [12.5, 7.25]


def test_existing_decimal_point_values_are_not_corrupted():
    df = load_dataset(csv("a,b\n1.5,2.25\n3.75,4.5\n"))
    assert df["a"].tolist() == [1.5, 3.75] and import_notes(df) == []


# ------------------------------------------------------------------ Excel worksheets
@pytest.fixture
def workbook():
    return xlsx({"Sales": pd.DataFrame({"a": [1, 2]}), "Costs": pd.DataFrame({"b": [9, 9, 9]}),
                 "Codes": pd.DataFrame({"zip": ["00123", "01234"]})})


def test_default_is_still_the_first_sheet(workbook):
    assert list(load_dataset(named_buffer(workbook, "w.xlsx")).columns) == ["a"]


@pytest.mark.parametrize("sheet,columns", [("Costs", ["b"]), (2, ["zip"]), ("Sales", ["a"])])
def test_any_sheet_can_be_chosen_by_name_or_position(workbook, sheet, columns):
    assert list(load_dataset(named_buffer(workbook, "w.xlsx"), sheet_name=sheet).columns) == columns


def test_excel_text_cells_keep_leading_zeros(workbook):
    assert load_dataset(named_buffer(workbook, "w.xlsx"), sheet_name="Codes")["zip"].tolist() == ["00123", "01234"]


def test_invalid_sheet_name_and_number_give_helpful_messages(workbook):
    with pytest.raises(ValueError, match="Available sheets: Sales, Costs, Codes"):
        load_excel(named_buffer(workbook, "w.xlsx"), "Nope")
    with pytest.raises(ValueError, match="does not exist"):
        load_excel(named_buffer(workbook, "w.xlsx"), 9)


def test_empty_sheet_is_reported(workbook):
    empty = xlsx({"Data": pd.DataFrame({"a": [1]}), "Empty": pd.DataFrame()})
    with pytest.raises(ValueError, match="has no data"):
        load_excel(named_buffer(empty, "w.xlsx"), "Empty")


def test_blank_rows_and_empty_unnamed_columns_are_removed_and_reported():
    buf = io.BytesIO()
    frame = pd.DataFrame({"a": [1, np.nan, 3], "Unnamed: 1": [np.nan] * 3, "b": ["x", None, "z"]})
    frame.to_excel(buf, index=False)
    df = load_excel(named_buffer(buf.getvalue(), "t.xlsx"))
    assert len(df) == 2 and "Unnamed: 1" not in df.columns
    assert len(import_notes(df)) == 2


def test_only_the_requested_sheet_is_parsed(workbook, monkeypatch):
    calls = []
    original = pd.ExcelFile.parse

    def spy(self, sheet_name=0, *a, **k):
        calls.append(sheet_name)
        return original(self, sheet_name, *a, **k)
    monkeypatch.setattr(pd.ExcelFile, "parse", spy)
    load_excel(named_buffer(workbook, "w.xlsx"), "Costs")
    assert calls == ["Costs"]


def test_sheet_names_and_garbage(workbook):
    assert excel_sheet_names(named_buffer(workbook, "w.xlsx")) == ["Sales", "Costs", "Codes"]
    with pytest.raises(ValueError, match="corrupt"):
        load_excel(named_buffer(b"not a workbook", "w.xlsx"))


@pytest.mark.parametrize("name", ["data.ods", "data.json", "data.xlsb", "noext"])
def test_unsupported_formats_are_rejected_politely(name):
    with pytest.raises(ValueError, match="Unsupported file type"):
        load_dataset(named_buffer(b"x", name))


# ------------------------------------------------------------------ general CSV validation
@pytest.mark.parametrize("sep", [",", ";", "\t"])
def test_three_delimiters_load_identically(sep):
    text = "\n".join(sep.join(r) for r in [["a", "b"], ["1", "x"], ["2", "y"]]) + "\n"
    df = load_dataset(csv(text))
    assert list(df.columns) == ["a", "b"] and df["a"].tolist() == [1, 2]


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp1252", "latin-1"])
def test_common_encodings(encoding):
    df = load_dataset(csv("name,v\ncafé,1\nnaïve,2\n", encoding=encoding))
    assert df["name"].tolist() == ["café", "naïve"]


def test_blank_lines_are_skipped_silently_because_nothing_is_lost():
    assert len(load_dataset(csv("a,b\n1,2\n\n\n3,4\n"))) == 2


def test_duplicate_column_names_are_made_unique_and_reported():
    df = load_dataset(csv("a,a,b\n1,2,3\n"))
    assert list(df.columns) == ["a", "a.1", "b"]
    assert any("'a' appears more than once" in n for n in import_notes(df))


def test_empty_file_message_is_friendly():
    with pytest.raises(ValueError, match="the file is empty"):
        load_csv(csv(""))


def test_malformed_rows_name_the_line_without_leaking_data():
    with pytest.raises(ValueError) as err:
        load_csv(csv("a,b\n1,2\n3,4,5,6\n"))
    text = str(err.value)
    assert "Line 3" in text and "delimiter" in text and "Traceback" not in text and "C error" not in text


def test_binary_garbage_does_not_crash_with_an_internal_error():
    try:
        load_csv(named_buffer(bytes(range(256)) * 20, "x.csv"))
    except ValueError as exc:
        assert "Traceback" not in str(exc) and "/home" not in str(exc)


def test_mixed_type_column_stays_text_and_keeps_every_value():
    df = load_dataset(csv("v\n1\ntwo\n3.5\n"))
    assert df["v"].tolist() == ["1", "two", "3.5"]


def test_header_only_file_loads_with_zero_rows():
    assert len(load_dataset(csv("a,b\n"))) == 0


def test_no_value_is_silently_discarded_in_a_realistic_file():
    rows = [f"{i:04d},{i % 5},{i * 1.5:.2f}" for i in range(200)]
    df = load_dataset(csv("code,grp,amount\n" + "\n".join(rows) + "\n"))
    assert len(df) == 200 and df["code"].iloc[0] == "0000" and df["amount"].sum() == pytest.approx(sum(i * 1.5 for i in range(200)))


def test_uploaded_buffer_is_left_rewound_and_unchanged():
    buf = csv("zip,v\n00123,1\n")
    before = buf.getvalue()
    load_dataset(buf)
    assert buf.tell() == 0 and buf.getvalue() == before


def test_import_notes_survive_the_loading_pipeline_and_copies():
    df = load_dataset(csv("zip,v\n00123,1\n01234,2\n"))
    assert import_notes(df.copy())


def test_excel_keeps_native_types_and_converts_numbers_stored_as_text():
    frame = pd.DataFrame({
        "n": [1, 2, 3], "f": [1.5, 2.5, 3.5], "d": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"]),
        "b": [True, False, True], "s": ["x", "y", "z"], "text_numbers": ["10", "20", "30"],
        "mixed": ["1", "two", "3"],
    })
    df = load_dataset(named_buffer(xlsx({"S": frame}), "t.xlsx"))
    assert pd.api.types.is_integer_dtype(df["n"]) and pd.api.types.is_float_dtype(df["f"])
    assert pd.api.types.is_datetime64_any_dtype(df["d"]) and pd.api.types.is_bool_dtype(df["b"])
    assert df["s"].tolist() == ["x", "y", "z"]
    assert df["text_numbers"].tolist() == [10, 20, 30]
    assert df["mixed"].tolist() == ["1", "two", "3"]


def test_excel_leading_zero_switch():
    data = xlsx({"S": pd.DataFrame({"zip": ["00123", "01234"]})})
    assert load_dataset(named_buffer(data, "t.xlsx"), keep_leading_zeros=False)["zip"].tolist() == [123, 1234]


@pytest.mark.parametrize("values", [["1,234", "2,500", "3,100"], ["12,50", "3,25", "7,75"], ["1.234", "2.500", "3.100"]])
def test_separated_numbers_are_not_mistaken_for_dates(values):
    from data.loader import detect_datetime_columns
    assert detect_datetime_columns(pd.DataFrame({"v": values})) == []


@pytest.mark.parametrize("values", [["2024.01.15", "2024.02.15", "2024.03.15"], ["15.01.2024", "15.02.2024", "15.03.2024"],
                                    ["2024-01-15", "2024-02-15", "2024-03-15"]])
def test_real_dates_with_separators_are_still_dates(values):
    from data.loader import detect_datetime_columns
    assert detect_datetime_columns(pd.DataFrame({"v": values})) == ["v"]


def test_excel_whole_number_text_column_stays_integer_when_blank_rows_are_removed():
    """Regression: numbers stored as text were converted before blank rows were dropped, giving floats."""
    buf = io.BytesIO()
    pd.DataFrame({"n": ["10", "20", None, "30"], "k": [1, 2, None, 4]}).to_excel(buf, index=False)
    df = load_dataset(named_buffer(buf.getvalue(), "t.xlsx"))
    assert len(df) == 3 and pd.api.types.is_integer_dtype(df["n"])
