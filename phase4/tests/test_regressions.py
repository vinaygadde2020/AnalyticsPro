"""Regression tests for confirmed early (P0) bugs.

Each test encodes a bug that was reproduced against the baseline code, so it
must FAIL before the fix and PASS after it.
"""
import numpy as np
import pandas as pd
import pytest

from data import cleaner
from tests.conftest import csv_bytes, edge_datasets, make_app, upload

EDGE = edge_datasets()


# --- B1: Visualizations crashed when no text column existed -----------------
@pytest.mark.parametrize("name", [
    "single_numeric_col", "all_numeric", "all_nan_col", "inf_values", "numeric_header_names",
])
def test_visualizations_render_without_text_columns(name):
    at = make_app(EDGE[name], f"{name}.csv", page="Visualizations")
    assert not at.exception, f"{name}: {at.exception[0].value if at.exception else ''}"


# --- B2: same file name, different content, was silently ignored -------------
def test_same_name_upload_replaces_dataset():
    at = make_app()
    upload(at, csv_bytes("a,b\n1,2\n3,4\n"), "data.csv")
    assert len(at.session_state["df"]) == 2
    upload(at, csv_bytes("a,b\n9,9\n8,8\n7,7\n6,6\n5,5\n"), "data.csv")
    df = at.session_state["df"]
    assert len(df) == 5, "changed file with the same name must replace the dataset"
    assert int(df.iloc[0, 0]) == 9


# --- B6: converting text to a number silently blanked the whole column -------
def test_type_conversion_refuses_silent_data_loss():
    df = pd.DataFrame({"z": ["1", "2", "x", "4"]})
    out, error = cleaner.convert_column_type(df, "z", "Integer")
    assert error, "an error message is required when values would be lost"
    assert out["z"].tolist() == ["1", "2", "x", "4"], "column must be left unchanged"


def test_type_conversion_allows_loss_only_when_explicit():
    df = pd.DataFrame({"z": ["1", "2", "x", "4"]})
    out, error = cleaner.convert_column_type(df, "z", "Integer", allow_data_loss=True)
    assert error is None
    assert out["z"].isna().sum() == 1 and out["z"].dropna().tolist() == [1, 2, 4]


def test_clean_conversions_still_work():
    df = pd.DataFrame({"n": ["1", "2", "3"], "f": ["1.5", "2.5", None]})
    assert cleaner.convert_column_type(df, "n", "Integer")[0]["n"].tolist() == [1, 2, 3]
    out, err = cleaner.convert_column_type(df, "f", "Float")  # existing NaN is not "new" loss
    assert err is None and out["f"].isna().sum() == 1


# --- B7: invalid custom fill value silently became 0 -------------------------
def test_invalid_custom_numeric_fill_is_not_applied_silently():
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    out, report = cleaner.fill_missing_values(df, ["a"], "Custom value", "abc", "Mode", None)
    assert out["a"].isna().sum() == 1, "must not fill with a made-up 0"
    assert report.get("warnings"), "the problem must be reported to the caller"


def test_valid_custom_numeric_fill_works():
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    out, report = cleaner.fill_missing_values(df, ["a"], "Custom value", "7.5", "Mode", None)
    assert out["a"].tolist() == [1.0, 7.5, 3.0] and not report.get("warnings")


# --- B9/B10: data must never reach raw HTML; no literal ** markers ------------
def _markdown_values(at):
    return [m.value for m in at.markdown]


def test_eda_insights_escape_cell_values_and_have_no_literal_asterisks():
    df = pd.DataFrame({"cat": ["<b>BOLD</b>"] * 40 + ["ok"] * 5, "v": np.arange(45.0)})
    at = make_app(df, "x.csv", page="Automatic EDA")
    assert not at.exception
    insights = [v for v in _markdown_values(at) if "ap-insight" in v]
    assert insights, "insight cards should be rendered"
    joined = "\n".join(insights)
    assert "<b>BOLD</b>" not in joined, "cell value reached raw HTML unescaped"
    assert "&lt;b&gt;BOLD&lt;/b&gt;" in joined
    assert "**" not in joined, "markdown bold markers must be converted"


def test_cleaning_history_escapes_user_text():
    df = pd.DataFrame({"cat": ["a", "b", "a"], "v": [1, 2, 3]})
    at = make_app(df, "x.csv", page="Data Preparation")
    at.selectbox(key="cm_rename_col").set_value("cat")
    at.text_input(key="cm_new_name").set_value("<i>NEW</i>")
    at.run()
    [b for b in at.button if b.key == "apply_rename_btn"][0].click().run()
    assert not at.exception
    joined = "\n".join(v for v in _markdown_values(at) if "ap-insight" in v)
    assert "<i>NEW</i>" not in joined


# --- UI-level: the Data Preparation buttons honour the data-loss protections ---
def _btn(at, key):
    return [b for b in at.button if b.key == key][0]


def _prep_app(df):
    return make_app(df, "x.csv", page="Data Preparation")


def test_ui_type_conversion_blocked_then_allowed_with_explicit_opt_in():
    df = pd.DataFrame({"z": ["1", "2", "x", "4"], "k": [1, 2, 3, 4]})
    at = _prep_app(df)
    at.selectbox(key="cm_convert_col").set_value("z")
    at.selectbox(key="cm_target_type").set_value("Integer")
    at.run()
    _btn(at, "apply_convert_btn").click().run()
    assert not at.exception
    assert at.session_state["df"]["z"].tolist() == ["1", "2", "x", "4"], "blocked: data must be unchanged"
    assert any("cannot be converted" in w.value for w in at.warning)

    at.checkbox(key="cm_allow_loss").check()
    at.run()
    _btn(at, "apply_convert_btn").click().run()
    assert not at.exception
    assert int(at.session_state["df"]["z"].isna().sum()) == 1


def test_ui_invalid_custom_fill_shows_error_and_changes_nothing():
    df = pd.DataFrame({"a": [1.0, None, 3.0, None]})
    at = _prep_app(df)
    at.selectbox(key="mv_numeric_strategy").set_value("Custom value")
    at.run()
    at.text_input(key="mv_numeric_custom").set_value("abc")
    at.run()
    _btn(at, "apply_missing_btn").click().run()
    assert not at.exception
    assert any("must be a number" in e.value for e in at.error)
    assert int(at.session_state["df"]["a"].isna().sum()) == 2


def test_original_dataset_is_never_modified_by_cleaning():
    df = pd.DataFrame({"a": [1.0, None, 3.0, 3.0], "b": ["x ", None, "y", "y"]})
    at = _prep_app(df)
    snapshot = at.session_state["original_df"].copy(deep=True)
    _btn(at, "quick_auto_clean_btn").click().run()
    assert not at.exception
    assert at.session_state["original_df"].equals(snapshot)
    assert not at.session_state["df"].equals(snapshot), "cleaning should have changed the working copy"


# --- Stage 2: multi-sheet workbooks are no longer silently truncated ----------
def test_multi_sheet_workbook_shows_notice_in_sidebar():
    import io as _io
    buf = _io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame({"a": [1, 2]}).to_excel(w, sheet_name="First", index=False)
        pd.DataFrame({"b": [3]}).to_excel(w, sheet_name="Second", index=False)
    at = make_app()
    at.sidebar.file_uploader[0].set_value([("book.xlsx", buf.getvalue(), "application/vnd.ms-excel")])
    at.run()
    assert not at.exception
    assert any("2 sheets" in c.value for c in at.sidebar.caption)


def test_semicolon_csv_upload_end_to_end():
    at = make_app()
    upload(at, csv_bytes("a;b;c\n1;2;3\n4;5;6\n"), "euro.csv")
    assert list(at.session_state["df"].columns) == ["a", "b", "c"]


def test_session_defaults_are_not_shared_between_sessions():
    """Regression: default lists/dicts were one shared object, so cleaning history leaked across users."""
    from tests.conftest import make_app
    first = make_app()
    first.session_state["cleaning_history"] = [*first.session_state["cleaning_history"], {"action": "private step"}]
    second = make_app()
    assert second.session_state["cleaning_history"] == []
    assert second.session_state["import_notes"] == [] and second.session_state["import_steps"] == {}


def test_default_containers_are_distinct_objects_per_session():
    from tests.conftest import make_app
    a, b = make_app(), make_app()
    for key in ("cleaning_history", "import_notes", "cleaning_report", "import_steps"):
        assert a.session_state[key] is not b.session_state[key]
