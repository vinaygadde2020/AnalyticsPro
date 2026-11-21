"""Unit tests for data/validator.py."""
import numpy as np
import pandas as pd
import pytest

from data import validator as va


def test_validate_dataframe_empty_and_none():
    for bad in (None, pd.DataFrame(), pd.DataFrame({"a": []})):
        r = va.validate_dataframe(bad)
        assert r["is_valid"] is False and r["is_empty"] is True and r["warnings"]


def test_validate_dataframe_clean_data_is_valid():
    r = va.validate_dataframe(pd.DataFrame({"a": [1, 2], "b": ["x", "y"]}))
    assert r["is_valid"] and not r["warnings"] and not r["null_only_columns"]


def test_validate_dataframe_flags_duplicate_column_names():
    df = pd.DataFrame([[1, 2]], columns=["a", "a"])
    r = va.validate_dataframe(df)
    assert r["is_valid"] is False and r["duplicate_column_names"] == ["a"]


def test_validate_dataframe_warns_about_null_only_and_blank_columns():
    df = pd.DataFrame({"n": [None, None], "e": ["", " "], "ok": [1, 2]})
    r = va.validate_dataframe(df)
    assert r["is_valid"] is True                      # warnings are non-blocking
    assert r["null_only_columns"] == ["n"] and r["empty_columns"] == ["e"]
    assert len(r["warnings"]) == 2


def test_detect_problematic_columns():
    df = pd.DataFrame({"mixed": pd.Series([1, "a", 2.5], dtype=object),
                       "inf": [1.0, np.inf, 2.0], "fine": [1, 2, 3], "txt": ["a", "b", "c"]})
    found = {(p["column"], p["issue"]) for p in va.detect_problematic_columns(df)}
    assert found == {("mixed", "mixed_types"), ("inf", "infinite_values")}
    assert va.detect_problematic_columns(pd.DataFrame()) == []
    assert va.detect_problematic_columns(None) == []


@pytest.mark.parametrize("col,target,safe", [
    ("nums", "Integer", True), ("text", "Integer", False), ("nums", "Float", True),
    ("dates", "DateTime", True), ("text", "DateTime", False),
    ("yn", "Boolean", True), ("text", "Boolean", False), ("text", "String", True),
])
def test_validate_column_conversion(col, target, safe):
    df = pd.DataFrame({"nums": ["1", "2", None], "text": ["a", "b", "c"],
                       "dates": ["2024-01-01", "2024-02-01", None], "yn": ["yes", "no", None]})
    is_safe, message = va.validate_column_conversion(df, col, target)
    assert is_safe is safe and message


def test_validate_column_conversion_missing_column_and_counts_losses():
    df = pd.DataFrame({"v": ["1", "x", "y"]})
    assert va.validate_column_conversion(df, "ghost", "Integer")[0] is False
    ok, msg = va.validate_column_conversion(df, "v", "Integer")
    assert not ok and "2 value(s)" in msg          # 'x' and 'y'; existing gaps are not counted
