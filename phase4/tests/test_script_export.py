"""The generated cleaning script must reproduce exactly what the app produced.

Each test loads a real file with the app's importer, applies steps with the app's own cleaning
functions (the oracle), generates the script, *executes* it on the original file and compares.
"""
import ast
import io

import numpy as np
import pandas as pd
import pytest

from data import cleaner
from data.loader import import_steps, load_dataset
from data.script_export import (SUPPORTED_OPS, build_cleaning_script, exportable_steps, unexportable_actions)
from tests.conftest import named_buffer

CSV_TEXT = (
    "Order ID;Zip;Price;Qty;Region;Note;Day;Score\n"
    "1;00123;12,50;3;north ;  hello   world ;2024-01-02;1.5\n"
    "2;01234;3,25;;South;;2024-02-03;inf\n"
    "3;90210;7,75;5;north ;  hello   world ;2024-03-04;2.5\n"
    "3;90210;7,75;5;north ;  hello   world ;2024-03-04;2.5\n"
    "4;00007;1.234,00;2;East;x;2024-04-05;\n"
)


def _datetime_oracle(df, step):
    out = df.copy()
    col = step["column"]
    if step["op"] == "datetime_convert":
        out[col if step["overwrite"] else f"{col}_datetime"] = pd.to_datetime(out[col], errors="coerce")
        return out
    s = pd.to_datetime(out[col], errors="coerce")
    for part in step["parts"]:
        if part == "Year":
            out[f"{col}_year"] = s.dt.year
        elif part == "Month":
            out[f"{col}_month"] = s.dt.month
        elif part == "Day":
            out[f"{col}_day"] = s.dt.day
        elif part == "Weekday":
            out[f"{col}_weekday"] = s.dt.day_name()
        elif part == "Hour":
            out[f"{col}_hour"] = s.dt.hour
    return out


def apply_steps(df, steps):
    """What the app does for each step (its own cleaning functions)."""
    for step in steps:
        op = step["op"]
        if op == "drop_columns":
            df = cleaner.drop_columns(df, step["columns"])
        elif op == "rename_column":
            df = cleaner.rename_column(df, step["old"], step["new"])
        elif op == "reorder_columns":
            df = cleaner.reorder_columns(df, step["order"])
        elif op == "remove_duplicates":
            df, _ = cleaner.remove_duplicates(df, step["action"])
        elif op == "fill_missing":
            df, _ = cleaner.fill_missing_values(df, step["columns"], step["numeric_strategy"], step["numeric_custom"],
                                                step["categorical_strategy"], step["categorical_custom"])
        elif op == "convert_type":
            df, error = cleaner.convert_column_type(df, step["column"], step["target_type"], allow_data_loss=True)
            assert error is None
        elif op == "clean_text":
            df = cleaner.clean_text_columns(df, step["columns"], step["operations"])
        elif op == "fix_infinite":
            df = cleaner.fix_infinite_values(df, step["columns"])
        else:
            df = _datetime_oracle(df, step)
    return df


def run_script(history, info, source_name, input_path, tmp_path):
    out = tmp_path / "out.csv"
    script = build_cleaning_script(history, info, source_name=source_name, input_path=str(input_path), output_path=str(out))
    ast.parse(script)                                   # always valid Python
    namespace: dict = {}
    exec(compile(script, "generated_cleaning_script.py", "exec"), namespace)   # noqa: S102
    return namespace["df"], script, out


def check(tmp_path, steps, raw=CSV_TEXT.encode("utf-8"), name="orders.csv"):
    path = tmp_path / name
    path.write_bytes(raw)
    loaded = load_dataset(named_buffer(raw, name))
    expected = apply_steps(loaded, steps)
    history = [{"action": f"step {i}", "step": s} for i, s in enumerate(steps, 1)]
    actual, script, out = run_script(history, import_steps(loaded), name, path, tmp_path)
    pd.testing.assert_frame_equal(actual, expected)
    return script, out, expected


# ---------------------------------------------------------------- loading alone
def test_script_without_steps_reproduces_the_import_exactly(tmp_path):
    script, out, expected = check(tmp_path, [])
    assert "no cleaning steps" in script and out.exists()


def test_import_cleanup_is_repeated_leading_zeros_decimal_commas_dates(tmp_path):
    _, _, df = check(tmp_path, [])
    assert df["Zip"].tolist() == ["00123", "01234", "90210", "90210", "00007"]
    assert df["Price"].tolist()[0] == 12.5 and df["Price"].tolist()[-1] == 1234.0
    assert pd.api.types.is_datetime64_any_dtype(df["Day"])


# ---------------------------------------------------------------- each operation matches the app
STEPS = {
    "drop_columns": {"op": "drop_columns", "columns": ["Note", "does not exist"]},
    "rename_column": {"op": "rename_column", "old": "Region", "new": "Area"},
    "reorder_columns": {"op": "reorder_columns", "order": ["Region", "Zip"]},
    "remove_duplicates_first": {"op": "remove_duplicates", "action": "Keep first occurrence"},
    "remove_duplicates_last": {"op": "remove_duplicates", "action": "Keep last occurrence"},
    "fill_median_mode": {"op": "fill_missing", "columns": ["Qty", "Region", "Note", "Score"], "numeric_strategy": "Median",
                         "numeric_custom": None, "categorical_strategy": "Mode", "categorical_custom": None},
    "fill_mean_unknown": {"op": "fill_missing", "columns": ["Qty", "Note"], "numeric_strategy": "Mean", "numeric_custom": None,
                          "categorical_strategy": "Unknown", "categorical_custom": None},
    "fill_zero_custom": {"op": "fill_missing", "columns": ["Qty", "Note"], "numeric_strategy": "Zero", "numeric_custom": None,
                         "categorical_strategy": "Custom value", "categorical_custom": "n/a"},
    "fill_custom_number": {"op": "fill_missing", "columns": ["Qty"], "numeric_strategy": "Custom value", "numeric_custom": "7.5",
                           "categorical_strategy": "Mode", "categorical_custom": None},
    "fill_drop_rows": {"op": "fill_missing", "columns": ["Qty", "Note"], "numeric_strategy": "Drop rows", "numeric_custom": None,
                       "categorical_strategy": "Drop rows", "categorical_custom": None},
    "to_integer": {"op": "convert_type", "column": "Qty", "target_type": "Integer"},
    "to_float": {"op": "convert_type", "column": "Qty", "target_type": "Float"},
    "to_string": {"op": "convert_type", "column": "Qty", "target_type": "String"},
    "to_category": {"op": "convert_type", "column": "Region", "target_type": "Category"},
    "to_datetime": {"op": "convert_type", "column": "Zip", "target_type": "DateTime"},
    "to_boolean": {"op": "convert_type", "column": "Qty", "target_type": "Boolean"},
    "text_all": {"op": "clean_text", "columns": ["Region", "Note"],
                 "operations": ["strip", "lower", "dedupe_spaces", "empty_to_nan"]},
    "text_upper": {"op": "clean_text", "columns": ["Region"], "operations": ["strip", "upper"]},
    "infinite": {"op": "fix_infinite", "columns": ["Score"]},
    "datetime_new": {"op": "datetime_convert", "column": "Day", "overwrite": False},
    "datetime_overwrite": {"op": "datetime_convert", "column": "Day", "overwrite": True},
    "datetime_extract": {"op": "datetime_extract", "column": "Day", "parts": ["Year", "Month", "Day", "Weekday", "Hour"]},
}


@pytest.mark.parametrize("name", list(STEPS))
def test_each_step_matches_the_app(tmp_path, name):
    check(tmp_path, [STEPS[name]])


def test_every_supported_operation_is_covered_by_a_test():
    assert {s["op"] for s in STEPS.values()} == set(SUPPORTED_OPS)


def test_realistic_multi_step_pipeline_matches_the_app(tmp_path):
    steps = [STEPS["text_all"], STEPS["infinite"], STEPS["remove_duplicates_first"], STEPS["fill_median_mode"],
             STEPS["to_integer"], STEPS["datetime_extract"], STEPS["rename_column"], STEPS["drop_columns"],
             STEPS["reorder_columns"] | {"order": ["Area", "Zip"]}]
    script, out, expected = check(tmp_path, steps)
    saved = pd.read_csv(out, dtype={"Zip": str})
    assert len(saved) == len(expected) and list(saved.columns) == list(expected.columns)
    assert saved["Zip"].tolist() == expected["Zip"].tolist()


def test_quick_auto_clean_composite_entry_matches_the_app(tmp_path):
    path = tmp_path / "q.csv"
    raw = CSV_TEXT.encode("utf-8")
    path.write_bytes(raw)
    loaded = load_dataset(named_buffer(raw, "q.csv"))
    expected, _ = cleaner.clean_dataframe(loaded)
    steps = [{"op": "remove_duplicates", "action": "Keep first occurrence"},
             {"op": "fill_missing", "columns": list(loaded.columns), "numeric_strategy": "Median", "numeric_custom": None,
              "categorical_strategy": "Mode", "categorical_custom": None}]
    actual, _, _ = run_script([{"action": "Quick Auto-Clean", "step": steps}], import_steps(loaded), "q.csv", path, tmp_path)
    pd.testing.assert_frame_equal(actual, expected)


# ---------------------------------------------------------------- other source formats
def test_comma_csv_and_tab_csv_sources(tmp_path):
    for sep in (",", "\t"):
        raw = CSV_TEXT.replace(";", sep).replace("12,50", '"12,50"').replace("3,25", '"3,25"').replace("7,75", '"7,75"') \
            .replace("1.234,00", '"1.234,00"').encode("utf-8")
        check(tmp_path, [STEPS["rename_column"]], raw=raw, name=f"o{'t' if sep == chr(9) else 'c'}.csv")


def test_latin1_encoded_csv_source(tmp_path):
    raw = "name;amount\ncafé;1,5\nnaïve;2,5\n".encode("cp1252")
    script, _, df = check(tmp_path, [], raw=raw, name="enc.csv")
    assert df["name"].tolist() == ["café", "naïve"] and "cp1252" in script


def test_excel_source_with_text_numbers_zeros_blank_rows_and_second_sheet(tmp_path):
    buf = io.BytesIO()
    first = pd.DataFrame({"a": [1, 2]})
    data = pd.DataFrame({"zip": ["00123", "01234", None, "90210"], "text_num": ["10", "20", None, "30"],
                         "price": ["12,50", "3,25", None, "7,75"], "n": [1.0, 2.0, np.nan, 4.0],
                         "when": pd.to_datetime(["2024-01-01", "2024-02-01", None, "2024-03-01"])})
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        first.to_excel(writer, sheet_name="First", index=False)
        data.to_excel(writer, sheet_name="Data", index=False)
    raw = buf.getvalue()
    path = tmp_path / "book.xlsx"
    path.write_bytes(raw)
    loaded = load_dataset(named_buffer(raw, "book.xlsx"), sheet_name="Data")
    steps = [STEPS["text_upper"] | {"columns": ["zip"]}]
    expected = apply_steps(loaded, steps)
    history = [{"action": "x", "step": s} for s in steps]
    actual, script, _ = run_script(history, import_steps(loaded), "book.xlsx", path, tmp_path)
    pd.testing.assert_frame_equal(actual, expected)
    assert "sheet_name='Data'" in script and "read_excel" in script
    assert expected["zip"].dropna().tolist() == ["00123", "01234", "90210"]
    assert expected["text_num"].dropna().tolist() == [10, 20, 30]


# ---------------------------------------------------------------- honesty and structure
def test_unrecognised_history_entries_become_comments_and_are_reported(tmp_path):
    history = [{"action": "Did something by hand"}, {"action": "Reordered", "step": STEPS["reorder_columns"]}]
    script = build_cleaning_script(history, {}, source_name="x.csv")
    assert "# Step 1: Did something by hand" in script and "could not be exported automatically" in script
    assert unexportable_actions(history) == ["Did something by hand"]
    assert exportable_steps(history) == [STEPS["reorder_columns"]]
    ast.parse(script)


def test_script_is_standalone_and_includes_only_needed_helpers():
    only_drop = build_cleaning_script([{"action": "d", "step": STEPS["drop_columns"]}], {}, source_name="x.csv")
    assert "def fill_missing" not in only_drop and "def convert_type" not in only_drop
    full = build_cleaning_script([{"action": "f", "step": STEPS["fill_zero_custom"]}], {}, source_name="x.csv")
    assert "def fill_missing" in full
    for script in (only_drop, full):
        assert "analyticspro" not in script.lower().replace("generated by analyticspro", "").replace("analyticspro's", "")
        assert "from data" not in script and "import streamlit" not in script


def test_user_text_in_names_cannot_break_out_of_the_script():
    nasty = "x'); import os; os.system('echo hi') #"
    script = build_cleaning_script(
        [{"action": nasty, "step": {"op": "rename_column", "old": nasty, "new": 'a"b'}}], {}, source_name=nasty + ".csv")
    tree = ast.parse(script)
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Import) and any(a.name == "os" for a in n.names)]
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "system"]


def test_unsupported_operation_is_rejected_loudly():
    with pytest.raises(ValueError, match="Unsupported step"):
        build_cleaning_script([{"action": "x", "step": {"op": "format_hard_drive"}}], {}, source_name="x.csv")


# ---------------------------------------------------------------- through the real UI
def _ui_session(tmp_path):
    from tests.conftest import make_app, upload
    raw = CSV_TEXT.encode("utf-8")
    (tmp_path / "orders.csv").write_bytes(raw)
    at = make_app()
    upload(at, raw, "orders.csv")
    at.session_state["current_page"] = "Data Preparation"
    at.run()
    return at


def test_steps_done_in_the_ui_are_recorded_and_the_script_reproduces_the_screen(tmp_path):
    at = _ui_session(tmp_path)
    at.button(key="quick_auto_clean_btn").click()
    at.run()
    at.multiselect(key="tc_selected_cols").set_value(["Region"])
    at.multiselect(key="tc_selected_ops").set_value(["strip", "lower"])
    at.button(key="apply_text_clean_btn").click()
    at.run()
    at.multiselect(key="cm_drop_cols").set_value(["Note"])
    at.button(key="apply_drop_cols_btn").click()
    at.run()
    assert not at.exception
    history = at.session_state["cleaning_history"]
    assert [list(exportable_steps([h])[i]["op"] for i in range(len(exportable_steps([h])))) for h in history] == \
        [["remove_duplicates", "fill_missing"], ["clean_text"], ["drop_columns"]]
    actual, _, _ = run_script(history, at.session_state["import_steps"], "orders.csv", tmp_path / "orders.csv", tmp_path)
    pd.testing.assert_frame_equal(actual, at.session_state["df"])


def test_export_page_offers_the_script_with_a_preview_and_counts_steps(tmp_path):
    at = _ui_session(tmp_path)
    at.multiselect(key="cm_drop_cols").set_value(["Note"])
    at.button(key="apply_drop_cols_btn").click()
    at.run()
    at.session_state["current_page"] = "Export & Reporting"
    at.run()
    assert not at.exception
    assert any("Reproducible Cleaning Script" in m.value for m in at.markdown)
    assert any(c.language == "python" and "df.drop(columns=['Note']" in c.value for c in at.code)
    assert any("1 cleaning step(s) included" in c.value for c in at.caption)


def test_export_page_without_any_cleaning_still_works_and_says_no_steps(tmp_path):
    at = _ui_session(tmp_path)
    at.session_state["current_page"] = "Export & Reporting"
    at.run()
    assert not at.exception and any("0 cleaning step(s) included" in c.value for c in at.caption)


def test_reset_changes_also_clears_the_recorded_steps(tmp_path):
    at = _ui_session(tmp_path)
    at.multiselect(key="cm_drop_cols").set_value(["Note"])
    at.button(key="apply_drop_cols_btn").click()
    at.run()
    assert at.session_state["cleaning_history"]
    at.button(key="reset_prep_changes_btn").click()
    at.run()
    assert at.session_state["cleaning_history"] == []
