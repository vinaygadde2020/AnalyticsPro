"""Tests for utils/helpers.py, utils/dataframe_utils.py and utils/session_state.py."""
import numpy as np
import pandas as pd
import pytest
import streamlit as st

from data import recommender as rc
from utils import dataframe_utils as du
from utils import helpers as h
from utils import session_state as ss

METRIC_NAMES = ["humidity", "width", "video_views", "paid_amount", "residual",
                "provider_score", "side", "tidal_height", "sales"]
ID_NAMES = ["id", "ID", "customer_id", "order_id", "customerId", "zip_code", "postal_code",
            "Row_Index", "index", "product-code", "CustomerID_2"]


def _frame(names):
    rng = np.random.default_rng(0)
    return pd.DataFrame({n: rng.normal(50, 5, 30) for n in names})


# --- regression: real metrics were silently dropped because their name contained "id"
@pytest.mark.parametrize("name", METRIC_NAMES)
def test_real_metric_columns_are_not_mistaken_for_ids(name):
    df = _frame([name, "other"])
    assert name in h.numeric_columns(df), f"{name!r} was silently excluded from numeric analysis"
    assert name in rc.usable_numeric_columns(df)


@pytest.mark.parametrize("name", ID_NAMES)
def test_identifier_columns_are_still_excluded(name):
    df = _frame([name, "sales"])
    assert name not in h.numeric_columns(df)
    assert name in h.numeric_columns(df, exclude_id=False)


def test_numeric_columns_edge_cases():
    assert h.numeric_columns(None) == [] and h.numeric_columns(pd.DataFrame()) == []
    assert h.numeric_columns(pd.DataFrame({"t": ["a", "b"]})) == []


def test_categorical_columns_and_get_column_types():
    df = pd.DataFrame({"n": [1, 2], "s": ["a", "b"], "c": pd.Categorical(["x", "y"]),
                       "d": pd.to_datetime(["2024-01-01", "2024-01-02"]), "b": [True, False]})
    assert set(h.categorical_columns(df)) == {"s", "c"}
    assert h.get_column_types(df) == {"n": "numeric", "s": "categorical", "c": "categorical",
                                      "d": "datetime", "b": "boolean"}
    assert h.get_column_types(pd.DataFrame()) == {}
    assert h.categorical_columns(None) == []


def test_formatters():
    assert h.format_number(1234.5) == "1,234.50" and h.format_number("x") == "x"
    assert h.format_number(1234.567, 0) == "1,235"
    assert h.format_bytes(0) == "0.0 B" and h.format_bytes(1536) == "1.5 KB"
    assert h.format_bytes(5 * 1024 ** 3) == "5.0 GB" and h.format_bytes("bad") == "0 B"
    assert h.format_bytes(2 * 1024 ** 4) == "2.0 TB"


# ------------------------------------------------------------- dataframe_utils
def test_safe_numeric_conversion_keeps_numbers_and_flags_failures():
    out = du.safe_numeric_conversion(pd.Series(["1", "2.5", "x", None]))
    assert out.iloc[0] == 1 and out.iloc[1] == 2.5 and pd.isna(out.iloc[2]) and pd.isna(out.iloc[3])


def test_safe_dataframe_never_mutates_and_survives_mixed_objects():
    df = pd.DataFrame({"m": pd.Series([1, "a", 2.5, None], dtype=object), "n": [1, 2, 3, 4]})
    snapshot = df.copy(deep=True)
    out = du.safe_dataframe(df)
    assert df.equals(snapshot), "input must not be mutated"
    assert len(out) == 4 and list(out.columns) == ["m", "n"]
    assert out["n"].tolist() == [1, 2, 3, 4]
    assert all(isinstance(v, str) or pd.isna(v) for v in out["m"]), "mixed column must be Arrow-safe"


def test_safe_dataframe_handles_empty_and_clean_frames():
    assert du.safe_dataframe(pd.DataFrame()).empty
    clean = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    assert du.safe_dataframe(clean).equals(clean)
    assert du.detect_mixed_object_columns(clean) == []


# --------------------------------------------------------------- session_state
@pytest.fixture()
def fake_state(monkeypatch):
    state = {}
    monkeypatch.setattr(st, "session_state", state)
    return state


def test_initialize_session_state_sets_defaults_without_overwriting(fake_state):
    fake_state["df"] = "keep me"
    ss.initialize_session_state({"custom_key": 5})
    assert fake_state["df"] == "keep me" and fake_state["custom_key"] == 5
    assert fake_state["current_page"] and fake_state["cleaning_history"] == []


def test_clear_dataset_dependent_state_removes_only_dependent_keys(fake_state):
    ss.initialize_session_state()
    fake_state.update({"cm_drop_cols": ["a"], "cm_allow_loss": True, "vis_group_x": "a", "unrelated": 1,
                       "cleaning_history": ["x"]})
    ss.clear_dataset_dependent_state()
    assert "cm_drop_cols" not in fake_state and "cm_allow_loss" not in fake_state
    assert "vis_group_x" not in fake_state and fake_state["unrelated"] == 1
    # the key is removed entirely; initialize_session_state() re-adds the default on the next run
    assert "cleaning_history" not in fake_state
    ss.initialize_session_state()
    assert fake_state["cleaning_history"] == []


def test_reset_dataset_state_clears_dataset_and_fingerprints(fake_state):
    ss.initialize_session_state()
    fake_state.update({"df": pd.DataFrame({"a": [1]}), "original_df": pd.DataFrame({"a": [1]}),
                       "dataset_name": "x.csv", "uploaded_file_name": "x.csv",
                       "uploaded_file_fingerprint": "id:1", "sheet_notice": "n"})
    ss.reset_dataset_state()
    for key in ("df", "original_df", "dataset_name", "uploaded_file_name",
                "uploaded_file_fingerprint", "sheet_notice"):
        assert fake_state[key] is None, key


def test_append_cleaning_history_adds_timestamped_entries(fake_state):
    ss.initialize_session_state()
    ss.append_cleaning_history("Dropped column 'a'")
    ss.append_cleaning_history("Renamed b")
    hist = fake_state["cleaning_history"]
    assert [e["action"] for e in hist] == ["Dropped column 'a'", "Renamed b"]
    assert all(e["time"] for e in hist)


def test_ensure_prep_checkpoint_snapshots_once_per_dataset(fake_state):
    ss.initialize_session_state()
    first = pd.DataFrame({"a": [1, 2]})
    ss.ensure_prep_checkpoint(first, "a.csv")
    assert fake_state["prep_checkpoint"] is not first, "snapshot must be a copy"
    first.iloc[0, 0] = 99                                       # later edits must not leak into it
    assert fake_state["prep_checkpoint"].iloc[0, 0] == 1
    fake_state["prep_checkpoint"].iloc[0, 0] = 5
    ss.ensure_prep_checkpoint(first, "a.csv")                   # same dataset: no re-snapshot
    assert fake_state["prep_checkpoint"].iloc[0, 0] == 5
    ss.ensure_prep_checkpoint(pd.DataFrame({"z": [7]}), "b.csv")    # new dataset: new snapshot
    assert list(fake_state["prep_checkpoint"].columns) == ["z"]
    assert fake_state["prep_checkpoint_name"] == "b.csv"


def test_escape_markdown_neutralises_links_bold_and_html():
    from utils.helpers import escape_markdown
    assert escape_markdown("[a](b) **c** <i>") == r"\[a\]\(b\) \*\*c\*\* \<i\>"
    assert escape_markdown(5) == "5"
