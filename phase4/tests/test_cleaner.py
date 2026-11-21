"""Unit tests for data/cleaner.py. Expected values are computed independently."""
import numpy as np
import pandas as pd
import pytest

from data import cleaner as cl


@pytest.fixture()
def messy():
    return pd.DataFrame({
        "a": [1.0, 2.0, 2.0, None, 100.0],
        "b": ["x", "y", "y", None, "z"],
    })


def _unchanged(fn, df):
    snapshot = df.copy(deep=True)
    fn(df)
    assert df.equals(snapshot) and list(df.columns) == list(snapshot.columns), "input was mutated"


# ----------------------------------------------------------- missing values
def test_analyze_missing_values_counts_and_sorting(messy):
    messy.loc[0, "b"] = None
    out = cl.analyze_missing_values(messy)
    assert out["Column"].tolist() == ["b", "a"]                 # 2 missing before 1
    assert out["Missing Count"].tolist() == [2, 1]
    assert out["Missing %"].tolist() == [40.0, 20.0]


def test_analyze_missing_values_when_nothing_missing_or_empty():
    assert cl.analyze_missing_values(pd.DataFrame({"a": [1, 2]})).empty
    assert cl.analyze_missing_values(pd.DataFrame()).empty
    assert cl.analyze_missing_values(None).empty


@pytest.mark.parametrize("strategy,expected", [
    ("Mean", np.mean([1, 2, 2, 100])), ("Median", 2.0), ("Zero", 0.0),
])
def test_fill_numeric_strategies(messy, strategy, expected):
    out, rep = cl.fill_missing_values(messy, ["a"], strategy, None, "Mode", None)
    assert out["a"].iloc[3] == pytest.approx(expected)
    assert rep["filled_numeric"] == 1 and rep["warnings"] == []


def test_fill_custom_numeric_and_categorical_strategies(messy):
    out, _ = cl.fill_missing_values(messy, ["a", "b"], "Custom value", "7.5", "Custom value", "N/A")
    assert out["a"].iloc[3] == 7.5 and out["b"].iloc[3] == "N/A"


@pytest.mark.parametrize("strategy,custom,expected", [
    ("Mode", None, "y"), ("Unknown", None, "Unknown"),
    ("Custom value", "", "Unknown"), ("Custom value", "Missing", "Missing"),
])
def test_fill_categorical_strategies(messy, strategy, custom, expected):
    out, rep = cl.fill_missing_values(messy, ["b"], "Mean", None, strategy, custom)
    assert out["b"].iloc[3] == expected and rep["filled_categorical"] == 1


def test_fill_drop_rows_removes_only_rows_missing_in_selected_columns(messy):
    messy.loc[1, "a"] = None   # missing in a only
    out, rep = cl.fill_missing_values(messy, ["a"], "Drop rows", None, "Mode", None)
    assert len(out) == 3 and rep["dropped_rows"] == 2
    assert out["b"].tolist() == ["x", "y", "z"]   # surviving rows 0, 2, 4 keep their b values


def test_fill_leaves_unselected_and_unknown_columns_alone(messy):
    out, rep = cl.fill_missing_values(messy, ["a", "nope"], "Zero", None, "Mode", None)
    assert out["b"].isna().sum() == 1 and rep["filled_numeric"] == 1


def test_fill_all_missing_numeric_column_is_not_filled_with_nan_statistic():
    df = pd.DataFrame({"a": [None, None, None]}, dtype=float)
    out, rep = cl.fill_missing_values(df, ["a"], "Mean", None, "Mode", None)
    assert out["a"].isna().all() and rep["filled_numeric"] == 0


def test_fill_does_not_mutate_input(messy):
    _unchanged(lambda d: cl.fill_missing_values(d, ["a", "b"], "Median", None, "Mode", None), messy)


# --------------------------------------------------------------- duplicates
def test_detect_duplicates_counts_and_percent():
    df = pd.DataFrame({"k": [1, 1, 2, 2, 2]})
    assert cl.detect_duplicates(df) == (3, 60.0)
    assert cl.detect_duplicates(pd.DataFrame()) == (0, 0.0)


def test_remove_duplicates_first_last_and_noop():
    df = pd.DataFrame({"k": [1, 2, 1], "v": ["a", "b", "a"]})
    first, n1 = cl.remove_duplicates(df, "Keep first occurrence")
    last, n2 = cl.remove_duplicates(df, "Keep last occurrence")
    none, n3 = cl.remove_duplicates(df, "Do nothing")
    assert first["k"].tolist() == [1, 2] and n1 == 1
    assert last["k"].tolist() == [2, 1] and n2 == 1
    assert len(none) == 3 and n3 == 0
    assert first.index.tolist() == [0, 1], "index must be reset"


# -------------------------------------------------------- column management
def test_drop_rename_reorder_columns():
    df = pd.DataFrame({"a": [1], "b": [2], "c": [3]})
    assert list(cl.drop_columns(df, ["b", "ghost"]).columns) == ["a", "c"]
    assert list(cl.rename_column(df, "a", "z").columns) == ["z", "b", "c"]
    assert list(cl.reorder_columns(df, ["c", "a"]).columns) == ["c", "a", "b"]
    _unchanged(lambda d: cl.drop_columns(d, ["a"]), df)
    _unchanged(lambda d: cl.rename_column(d, "a", "z"), df)
    _unchanged(lambda d: cl.reorder_columns(d, ["c"]), df)


# ------------------------------------------------------------ type conversion
def test_convert_valid_types():
    df = pd.DataFrame({"i": ["1", "2"], "f": ["1.5", "2"], "d": ["2024-01-01", "2024-02-01"],
                       "b": ["yes", "no"], "s": [1, 2], "c": ["x", "y"]})
    assert cl.convert_column_type(df, "i", "Integer")[0]["i"].tolist() == [1, 2]
    assert cl.convert_column_type(df, "f", "Float")[0]["f"].tolist() == [1.5, 2.0]
    assert pd.api.types.is_datetime64_any_dtype(cl.convert_column_type(df, "d", "DateTime")[0]["d"])
    assert cl.convert_column_type(df, "b", "Boolean")[0]["b"].tolist() == [True, False]
    assert cl.convert_column_type(df, "s", "String")[0]["s"].tolist() == ["1", "2"]
    assert str(cl.convert_column_type(df, "c", "Category")[0]["c"].dtype) == "category"


def test_convert_to_string_and_category_preserve_missing_values():
    df = pd.DataFrame({"v": [1.5, None, 3.0], "o": ["a", None, "c"]})
    assert cl.convert_column_type(df, "v", "String")[0]["v"].isna().sum() == 1
    assert cl.convert_column_type(df, "o", "Category")[0]["o"].isna().sum() == 1


@pytest.mark.parametrize("target,values", [
    ("DateTime", ["2024-01-01", "not a date"]),
    ("Boolean", ["yes", "maybe"]),
    ("Float", ["1.5", "abc"]),
])
def test_lossy_conversions_are_refused_by_default(target, values):
    df = pd.DataFrame({"v": values})
    out, err = cl.convert_column_type(df, "v", target)
    assert err and out["v"].tolist() == values
    out, err = cl.convert_column_type(df, "v", target, allow_data_loss=True)
    assert err is None and out["v"].isna().sum() == 1


def test_conversion_unknown_target_and_float_to_int_with_fraction():
    df = pd.DataFrame({"v": [1.5, 2.0]})
    assert cl.convert_column_type(df, "v", "Hex")[1]
    out, err = cl.convert_column_type(df, "v", "Integer")   # 1.5 cannot be an integer
    assert err and out["v"].tolist() == [1.5, 2.0]


def test_conversion_does_not_mutate_input():
    df = pd.DataFrame({"v": ["1", "x"]})
    _unchanged(lambda d: cl.convert_column_type(d, "v", "Integer", allow_data_loss=True), df)


# ------------------------------------------------------------ text cleaning
def test_text_cleaning_operations():
    df = pd.DataFrame({"s": ["  Hello   World ", "", None, "ABC"]})
    out = cl.clean_text_columns(df, ["s"], ["strip", "dedupe_spaces", "lower", "empty_to_nan"])
    assert out["s"].iloc[0] == "hello world" and pd.isna(out["s"].iloc[1]) and pd.isna(out["s"].iloc[2])
    assert cl.clean_text_columns(df, ["s"], ["upper"])["s"].iloc[3] == "ABC"
    assert cl.clean_text_columns(df, ["s"], [])["s"].iloc[0] == "  Hello   World "
    assert cl.clean_text_columns(df, ["ghost"], ["lower"]).equals(df)
    _unchanged(lambda d: cl.clean_text_columns(d, ["s"], ["lower"]), df)


# ----------------------------------------------------------- numeric cleaning
def test_numeric_quality_scan_counts():
    rng = np.random.default_rng(0)
    values = list(rng.normal(0, 1, 200)) + [1000.0, -5.0, np.inf]
    df = pd.DataFrame({"x": values})
    row = cl.numeric_quality_scan(df, ["x"]).iloc[0]
    finite = np.array([v for v in values if np.isfinite(v)])
    z = (finite - finite.mean()) / finite.std(ddof=0)
    assert row["Infinite Values"] == 1
    assert row["Negative Values"] == int((np.array(values) < 0).sum())
    assert row["Extreme Values (|z|>4)"] == int((np.abs(z) > 4).sum())


def test_numeric_quality_scan_constant_column_has_no_extremes():
    row = cl.numeric_quality_scan(pd.DataFrame({"x": [5, 5, 5]}), ["x"]).iloc[0]
    assert row["Extreme Values (|z|>4)"] == 0 and row["Negative Values"] == 0


def test_fix_infinite_values():
    df = pd.DataFrame({"x": [1.0, np.inf, -np.inf], "y": [np.inf, 1.0, 1.0]})
    out = cl.fix_infinite_values(df, ["x", "ghost"])
    assert out["x"].isna().sum() == 2 and np.isinf(out["y"]).sum() == 1
    _unchanged(lambda d: cl.fix_infinite_values(d, ["x"]), df)


# ------------------------------------------------------- composite / reporting
def test_clean_dataframe_default_removes_duplicates_then_fills():
    df = pd.DataFrame({"a": [1.0, 1.0, None, 4.0], "b": ["x", "x", None, "y"]})
    out, rep = cl.clean_dataframe(df)
    assert rep["before_rows"] == 4 and rep["removed_duplicates"] == 1 and rep["after_rows"] == 3
    assert rep["after_missing"] == 0 and rep["filled_numeric"] == 1 and rep["filled_categorical"] == 1
    assert rep["after_duplicates"] == 0
    assert out["a"].tolist() == [1.0, 2.5, 4.0] or out["a"].iloc[1] == pytest.approx(np.median([1, 4]))


def test_clean_dataframe_drop_strategy_and_noop():
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    out, rep = cl.clean_dataframe(df, missing_strategy="Drop rows with missing values")
    assert len(out) == 2 and rep["dropped_rows"] == 1
    out, rep = cl.clean_dataframe(df, missing_strategy="Leave as is", duplicate_action="Keep all")
    assert out.equals(df) and rep["after_missing"] == 1


def test_generate_cleaning_report_deltas():
    before = {"rows": 10, "columns": 4, "missing": 7, "duplicates": 3}
    after = {"rows": 8, "columns": 3, "missing": 0, "duplicates": 0}
    assert cl.generate_cleaning_report(before, after) == {
        "rows_removed": 2, "columns_removed": 1, "missing_repaired": 7, "duplicates_removed": 3}
