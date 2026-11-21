"""
utils/session_state.py
========================
Centralized Streamlit session-state initialization for AnalyticsPro,
so app.py doesn't need to scatter `if key not in st.session_state`
checks across multiple pages.
"""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

# Core defaults every page can rely on existing.
_CORE_DEFAULTS: dict[str, Any] = {
    "current_page": "Data Upload & Preview",
    "df": None,
    "original_df": None,
    "dataset_name": None,
    "uploaded_file_name": None,
    "uploaded_file_fingerprint": None,
    "sheet_notice": None,
    "import_notes": [],
    "import_steps": {},
    "cleaning_applied": False,
    "cleaning_report": {},
    "cleaning_history": []
}

# Widget/report state that only makes sense for the currently loaded
# dataset. This is cleared whenever a new file is uploaded or the
# active dataset is reset, so stale selections from a previous
# dataset (e.g. a column name that no longer exists) never leak into
# a new one.
DATASET_DEPENDENT_KEYS = [
    "missing_strategy", "numeric_fill_strategy", "categorical_fill_strategy",
    "cleaning_columns", "duplicate_action",
    "eda_distribution_col", "eda_category_col",
    "kpi_primary_metric", "kpi_breakdown_cat",
    "vis_group_x", "vis_metric_y", "vis_single_num", "vis_color_by",
    "vis_scat_x", "vis_scat_y", "vis_scat_cat", "smart_rec_last_applied",
    "corr_pair_select", "corr_scat_cat", "outlier_col",
    "ai_query_input",
    "linked_dash_metric", "linked_dash_category", "linked_dash_values",
    "linked_dash_date_col", "linked_dash_date_range", "linked_dash_aggregation",
    "linked_dash_trend_grain",
    # Data Preparation module widget/report state
    "mv_selected_columns", "mv_numeric_strategy", "mv_numeric_custom",
    "mv_categorical_strategy", "mv_categorical_custom",
    "dup_action",
    "cm_drop_cols", "cm_rename_col", "cm_new_name", "cm_reorder",
    "cm_convert_col", "cm_target_type", "cm_allow_loss",
    "tc_selected_cols", "tc_selected_ops",
    "nc_fix_inf_cols",
    "dt_selected_col", "dt_overwrite", "dt_extract_opts",
    "stats_selected_col",
    "preview_view_mode", "preview_n_rows",
    "cleaning_history", "prep_checkpoint", "prep_checkpoint_name"
]


def initialize_session_state(extra_defaults: dict | None = None) -> None:
    """
    Ensure every core AnalyticsPro session-state key exists, without
    overwriting any value that's already set (so this is safe to call
    on every rerun). Additional {key: default} pairs can be supplied
    via `extra_defaults` for page-specific needs.
    """
    defaults = dict(_CORE_DEFAULTS)
    if extra_defaults:
        defaults.update(extra_defaults)

    for key, value in defaults.items():
        if key not in st.session_state:
            # Deep copy: the defaults hold lists/dicts, and sharing one object between sessions
            # would leak one user's data (e.g. cleaning history) into another user's session.
            st.session_state[key] = copy.deepcopy(value)


def clear_dataset_dependent_state() -> None:
    """
    Remove every dataset-dependent widget/report key from session
    state. Call this whenever the active dataset changes (a new file
    is uploaded, or the dataset is reset) so stale UI selections from
    a previous dataset don't linger.
    """
    for key in list(st.session_state.keys()):
        if key in DATASET_DEPENDENT_KEYS or str(key).startswith("linked_dash_"):
            st.session_state.pop(key, None)


def reset_dataset_state() -> None:
    """Clear both the active dataset and any dataset-dependent widget state."""
    clear_dataset_dependent_state()
    st.session_state["df"] = None
    st.session_state["original_df"] = None
    st.session_state["dataset_name"] = None
    st.session_state["uploaded_file_name"] = None
    st.session_state["uploaded_file_fingerprint"] = None
    st.session_state["sheet_notice"] = None
    st.session_state["import_notes"] = []
    st.session_state["import_steps"] = {}
    st.session_state["cleaning_applied"] = False
    st.session_state["cleaning_report"] = {}


def append_cleaning_history(action_text: str, step: dict | list[dict] | None = None) -> None:
    """Append a timestamped entry to the 'cleaning_history' session-state list.

    ``step`` is an optional structured description of the operation (see
    ``data/script_export.py``); entries that have one can be exported as a Python script.
    """
    timestamp = datetime.now().strftime("%d %b %Y, %H:%M")
    entry: dict = {"time": timestamp, "action": action_text}
    if step is not None:
        entry["step"] = step
    # Build a new list instead of appending in place, so no other holder of the old list changes.
    st.session_state["cleaning_history"] = [*st.session_state.get("cleaning_history", []), entry]


def ensure_prep_checkpoint(df: pd.DataFrame, dataset_name: str | None) -> None:
    """
    Snapshot the dataset the first time the Data Preparation page is
    opened for a given dataset_name, so "Reset Changes" can revert to
    it later without needing a second upload.
    """
    if (
        st.session_state.get("prep_checkpoint") is None
        or st.session_state.get("prep_checkpoint_name") != dataset_name
    ):
        st.session_state["prep_checkpoint"] = df.copy()
        st.session_state["prep_checkpoint_name"] = dataset_name
