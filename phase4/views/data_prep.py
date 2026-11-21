"""Data Preparation page."""

from __future__ import annotations

from html import escape as html_escape
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from data.cleaner import (
    analyze_missing_values,
    clean_dataframe,
    clean_text_columns,
    convert_column_type,
    detect_duplicates,
    drop_columns,
    fill_missing_values,
    fix_infinite_values,
    generate_cleaning_report,
    numeric_quality_scan,
    remove_duplicates,
    rename_column,
    reorder_columns,
)
from data.loader import detect_datetime_columns
from data.profiler import (
    calculate_dataset_health,
    get_column_statistics,
    get_data_quality_report,
    profile_dataset,
)
from data.validator import (
    detect_problematic_columns,
    validate_column_conversion,
    validate_dataframe,
)
from utils.dataframe_utils import safe_dataframe
from utils.helpers import categorical_columns, numeric_columns
from utils.session_state import append_cleaning_history, ensure_prep_checkpoint
from views.common import badge_html, card_container, render_html, render_page_intro, render_section_heading


def _custom_numeric_invalid(df: pd.DataFrame, columns: list, strategy: str, custom_value: Any) -> bool:
    """True when 'Custom value' was chosen for numeric columns that have gaps
    but the typed value is not a number."""
    if strategy != "Custom value":
        return False
    try:
        float(custom_value)
        return False
    except (TypeError, ValueError):
        pass
    return any(
        c in df.columns and pd.api.types.is_numeric_dtype(df[c]) and df[c].isna().any()
        for c in columns
    )


def _render_overview(df: pd.DataFrame) -> None:
    """Dataset overview metrics and validation warnings."""
    # ---------------- A. DATASET OVERVIEW ----------------
    ov = profile_dataset(df)
    render_section_heading("Dataset overview", "Live profile of the active dataset; it updates after every cleaning step.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows", f"{ov['rows']:,}")
    c2.metric("Columns", f"{ov['columns']:,}")
    c3.metric("Missing Values", f"{ov['missing']:,}")
    c4.metric("Duplicates", f"{ov['duplicates']:,}")
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Numeric Columns", f"{ov['numeric']:,}")
    c6.metric("Categorical Columns", f"{ov['categorical']:,}")
    c7.metric("Date/Time Columns", f"{ov['datetime']:,}")
    c8.metric("Memory Usage", ov["memory"])

    health = calculate_dataset_health(df)
    steps = len(st.session_state.get("cleaning_history", []))
    render_html(
        badge_html(f"Health {health['overall']}/100 · {health['status']}", "success" if health["overall"] > 85 else "warning", dot=True)
        + " " + badge_html(f"{steps} cleaning step(s) this session", "info" if steps else "neutral")
    )

    validation = validate_dataframe(df)
    if validation["warnings"]:
        for msg in validation["warnings"]:
            st.warning(f"⚠️ {msg}")


def _tab_data_quality(df: pd.DataFrame) -> None:
    """Data Quality tab: column-level quality summary and Quick Auto-Clean."""
    render_section_heading("Column-Level Data Quality Summary", "Per-column completeness, uniqueness and detected issues.")
    quality_df = get_data_quality_report(df)
    st.dataframe(safe_dataframe(quality_df), width="stretch", height=380, hide_index=True)

    problematic = detect_problematic_columns(df)
    if problematic:
        issue_labels = ", ".join(f"`{p['column']}` ({p['issue'].replace('_', ' ')})" for p in problematic)
        st.warning(f"Potentially problematic column(s) detected: {issue_labels}.")

    st.divider()
    render_section_heading("⚡ Quick Auto-Clean (Recommended Defaults)")
    st.caption(
        "One-click cleaning using sensible defaults: fills numeric missing values with the "
        "median, categorical missing values with the mode, and removes duplicate rows."
    )
    if st.button("⚡ Run Quick Auto-Clean", width="stretch", key="quick_auto_clean_btn"):
        updated, report = clean_dataframe(df)
        st.session_state["df"] = updated
        append_cleaning_history(
            f"Quick Auto-Clean: filled {report['filled_numeric'] + report['filled_categorical']:,} "
            f"missing value(s), removed {report['removed_duplicates']:,} duplicate row(s).",
            step=[
                {"op": "remove_duplicates", "action": "Keep first occurrence"},
                {"op": "fill_missing", "columns": list(df.columns), "numeric_strategy": "Median", "numeric_custom": None,
                 "categorical_strategy": "Mode", "categorical_custom": None},
            ],
        )
        st.success("Quick Auto-Clean applied using recommended defaults.")
        st.rerun()


def _tab_missing_values(df: pd.DataFrame) -> None:
    """Missing Values tab."""
    render_section_heading("Missing Value Treatment")
    missing_summary = analyze_missing_values(df)
    missing_cols = missing_summary["Column"].tolist() if not missing_summary.empty else []

    if missing_cols:
        st.warning(f"{len(missing_cols)} column(s) contain missing values.")
        st.dataframe(safe_dataframe(missing_summary), width="stretch", height=200, hide_index=True)
    else:
        st.success("No missing values detected in the current dataset.")

    selected_columns = st.multiselect(
        "Columns to treat",
        list(df.columns),
        default=missing_cols,
        key="mv_selected_columns"
    )

    a, b = st.columns(2)
    with a:
        st.markdown("**Numeric columns**")
        numeric_strategy = st.selectbox(
            "Strategy",
            ["Mean", "Median", "Zero", "Custom value", "Drop rows"],
            key="mv_numeric_strategy"
        )
        numeric_custom = None
        if numeric_strategy == "Custom value":
            numeric_custom = st.text_input("Custom numeric value", value="0", key="mv_numeric_custom")
    with b:
        st.markdown("**Categorical / text columns**")
        categorical_strategy = st.selectbox(
            "Strategy",
            ["Mode", "Unknown", "Custom value", "Drop rows"],
            key="mv_categorical_strategy"
        )
        categorical_custom = None
        if categorical_strategy == "Custom value":
            categorical_custom = st.text_input("Custom text value", value="Unknown", key="mv_categorical_custom")

    before_missing = int(df.isna().sum().sum())
    st.markdown(f"**Missing values currently:** {before_missing:,}")

    if st.button("🧹 Apply Missing Value Treatment", type="primary", width="stretch", key="apply_missing_btn"):
        if not selected_columns:
            st.warning("Select at least one column to treat.")
        elif _custom_numeric_invalid(df, selected_columns, numeric_strategy, numeric_custom):
            st.error("The custom numeric value must be a number (for example 0 or 12.5). Nothing was changed.")
        else:
            updated, report = fill_missing_values(
                df, selected_columns, numeric_strategy, numeric_custom,
                categorical_strategy, categorical_custom
            )
            repaired = report["filled_numeric"] + report["filled_categorical"]
            st.session_state["df"] = updated
            append_cleaning_history(
                f"Missing values: repaired {repaired:,}, dropped {report['dropped_rows']:,} row(s) "
                f"across {len(selected_columns)} column(s).",
                step={"op": "fill_missing", "columns": list(selected_columns), "numeric_strategy": numeric_strategy,
                      "numeric_custom": numeric_custom, "categorical_strategy": categorical_strategy,
                      "categorical_custom": categorical_custom},
            )
            st.success(
                f"Before: {before_missing:,} · After: {int(updated.isna().sum().sum()):,} · "
                f"Repaired: {repaired:,}"
            )
            st.rerun()


def _tab_duplicates(df: pd.DataFrame) -> None:
    """Duplicates tab."""
    render_section_heading("Duplicate Row Treatment")
    dup_count, dup_pct = detect_duplicates(df)
    a, b = st.columns(2)
    a.metric("Duplicate Rows", f"{dup_count:,}")
    b.metric("Duplicate %", f"{dup_pct:.2f}%")

    duplicate_action = st.radio(
        "Action",
        ["No action", "Keep first occurrence", "Keep last occurrence"],
        horizontal=True,
        key="dup_action"
    )

    if st.button("🗂️ Apply Duplicate Treatment", type="primary", width="stretch", key="apply_dup_btn"):
        if duplicate_action == "No action":
            st.info("No action selected.")
        else:
            updated, removed = remove_duplicates(df, duplicate_action)
            st.session_state["df"] = updated
            append_cleaning_history(
                f"Removed {removed:,} duplicate row(s) ({duplicate_action}).",
                step={"op": "remove_duplicates", "action": duplicate_action},
            )
            after_count, _ = detect_duplicates(updated)
            st.success(f"Before: {dup_count:,} · After: {after_count:,} · Removed: {removed:,}")
            st.rerun()


def _remove_columns_section(df: pd.DataFrame) -> None:
    st.markdown("**Remove columns**")
    drop_cols = st.multiselect("Columns to remove", list(df.columns), key="cm_drop_cols")
    if st.button("🗑️ Remove Selected Columns", width="stretch", key="apply_drop_cols_btn"):
        if drop_cols:
            st.session_state["df"] = drop_columns(df, drop_cols)
            append_cleaning_history(f"Removed column(s): {', '.join(drop_cols)}.",
                                    step={"op": "drop_columns", "columns": list(drop_cols)})
            st.success(f"Removed {len(drop_cols)} column(s).")
            st.rerun()
        else:
            st.warning("Select at least one column.")


def _rename_column_section(df: pd.DataFrame) -> None:
    st.markdown("**Rename column**")
    a, b = st.columns(2)
    with a:
        rename_col = st.selectbox("Column to rename", list(df.columns), key="cm_rename_col")
    with b:
        new_name = st.text_input("New column name", key="cm_new_name")
    if st.button("✏️ Apply Rename", width="stretch", key="apply_rename_btn"):
        new_name_clean = (new_name or "").strip()
        if not new_name_clean:
            st.warning("Enter a new column name.")
        elif new_name_clean in df.columns:
            st.warning("A column with that name already exists.")
        else:
            st.session_state["df"] = rename_column(df, rename_col, new_name_clean)
            append_cleaning_history(f"Renamed column '{rename_col}' to '{new_name_clean}'.",
                                    step={"op": "rename_column", "old": rename_col, "new": new_name_clean})
            st.success(f"Renamed '{rename_col}' to '{new_name_clean}'.")
            st.rerun()


def _reorder_columns_section(df: pd.DataFrame) -> None:
    st.markdown("**Reorder columns**")
    new_order = st.multiselect(
        "Select columns in the desired order (leave empty for no change)",
        list(df.columns),
        key="cm_reorder"
    )
    if st.button("↕️ Apply Reorder", width="stretch", key="apply_reorder_btn"):
        if not new_order:
            st.warning("Select the columns in your preferred order first.")
        else:
            st.session_state["df"] = reorder_columns(df, new_order)
            append_cleaning_history("Reordered columns.", step={"op": "reorder_columns", "order": list(new_order)})
            st.success("Column order updated.")
            st.rerun()


def _convert_type_section(df: pd.DataFrame) -> None:
    st.markdown("**Convert data type**")
    a, b = st.columns(2)
    with a:
        convert_col = st.selectbox("Column", list(df.columns), key="cm_convert_col")
    with b:
        target_type = st.selectbox(
            "Target type",
            ["Integer", "Float", "String", "Category", "DateTime", "Boolean"],
            key="cm_target_type"
        )
    is_safe, safety_message = validate_column_conversion(df, convert_col, target_type)
    allow_loss = False
    if not is_safe:
        st.caption(f"⚠️ {safety_message}")
        allow_loss = st.checkbox(
            "Convert anyway and set these values to missing",
            key="cm_allow_loss",
        )
    if st.button("🔁 Apply Type Conversion", width="stretch", key="apply_convert_btn"):
        updated, error = convert_column_type(df, convert_col, target_type, allow_data_loss=allow_loss)
        if error:
            st.warning(f"Could not convert '{convert_col}' to {target_type}: {error}. Column left unchanged.")
        else:
            st.session_state["df"] = updated
            append_cleaning_history(f"Converted column '{convert_col}' to {target_type}.",
                                    step={"op": "convert_type", "column": convert_col, "target_type": target_type})
            st.success(f"'{convert_col}' converted to {target_type}.")
            st.rerun()


def _tab_columns(df: pd.DataFrame) -> None:
    """Columns tab: remove, rename, reorder and convert types (one helper per action)."""
    render_section_heading("Column Management")
    _remove_columns_section(df)
    st.divider()
    _rename_column_section(df)
    st.divider()
    _reorder_columns_section(df)
    st.divider()
    _convert_type_section(df)


def _tab_text_cleaning(df: pd.DataFrame) -> None:
    """Text Cleaning tab."""
    render_section_heading("Text Cleaning")
    text_cols = categorical_columns(df)
    if not text_cols:
        st.info("No text/object columns detected in this dataset.")
    else:
        selected_text_cols = st.multiselect(
            "Columns to clean",
            text_cols,
            key="tc_selected_cols"
        )
        op_labels = {
            "strip": "Strip leading/trailing spaces",
            "lower": "Convert to lowercase",
            "upper": "Convert to UPPERCASE",
            "dedupe_spaces": "Remove duplicate spaces",
            "empty_to_nan": "Replace empty strings with NaN"
        }
        selected_ops = st.multiselect(
            "Operations to apply",
            list(op_labels.keys()),
            format_func=lambda k: op_labels[k],
            key="tc_selected_ops"
        )
        if st.button("🔤 Apply Text Cleaning", type="primary", width="stretch", key="apply_text_clean_btn"):
            if not selected_text_cols or not selected_ops:
                st.warning("Select at least one column and one operation.")
            else:
                updated = clean_text_columns(df, selected_text_cols, selected_ops)
                st.session_state["df"] = updated
                applied_labels = ", ".join(op_labels[o] for o in selected_ops)
                append_cleaning_history(
                    f"Applied text cleaning ({applied_labels}) on {len(selected_text_cols)} column(s).",
                    step={"op": "clean_text", "columns": list(selected_text_cols), "operations": list(selected_ops)},
                )
                st.success("Text cleaning applied.")
                st.rerun()


def _tab_numeric_check(df: pd.DataFrame) -> None:
    """Numeric Check tab."""
    render_section_heading("Numeric Data Quality Check")
    num_cols = numeric_columns(df, exclude_id=False)
    if not num_cols:
        st.info("No numeric columns detected in this dataset.")
    else:
        scan = numeric_quality_scan(df, num_cols)
        st.dataframe(safe_dataframe(scan), width="stretch", height=280, hide_index=True)
        st.caption(
            "Negative values are not assumed to be errors — they may be legitimate. "
            "Review before taking action."
        )
        inf_cols = [
            c for c in num_cols
            if np.isinf(pd.to_numeric(df[c], errors="coerce")).any()
        ]
        if inf_cols:
            st.warning(f"Infinite values detected in: {', '.join(inf_cols)}.")
            fix_cols = st.multiselect(
                "Columns to convert infinite values to missing (NaN)",
                inf_cols,
                default=inf_cols,
                key="nc_fix_inf_cols"
            )
            if st.button("♾️ Replace Infinite Values with NaN", width="stretch", key="apply_inf_fix_btn"):
                updated = fix_infinite_values(df, fix_cols)
                st.session_state["df"] = updated
                append_cleaning_history(f"Replaced infinite values with NaN in {len(fix_cols)} column(s).",
                                        step={"op": "fix_infinite", "columns": list(fix_cols)})
                st.success("Infinite values replaced.")
                st.rerun()
        else:
            st.success("No infinite values detected.")


def _tab_datetime(df: pd.DataFrame) -> None:
    """Date/Time tab."""
    render_section_heading("Date/Time Handling")
    candidate_dt_cols = list(dict.fromkeys(
        df.select_dtypes(include=["datetime", "datetimetz"]).columns.tolist()
        + detect_datetime_columns(df)
    ))
    if not candidate_dt_cols:
        st.info("No date/time columns detected in this dataset.")
    else:
        dt_col = st.selectbox("Date/time column", candidate_dt_cols, key="dt_selected_col")
        is_already_dt = pd.api.types.is_datetime64_any_dtype(df[dt_col])

        if not is_already_dt:
            overwrite = st.checkbox(
                f"Overwrite '{dt_col}' with parsed datetime (otherwise a new column is created)",
                key="dt_overwrite"
            )
            if st.button("🕐 Convert to DateTime", width="stretch", key="apply_dt_convert_btn"):
                updated = df.copy()
                parsed = pd.to_datetime(updated[dt_col], errors="coerce")
                if overwrite:
                    updated[dt_col] = parsed
                    append_cleaning_history(f"Converted '{dt_col}' to datetime.",
                                            step={"op": "datetime_convert", "column": dt_col, "overwrite": True})
                else:
                    new_col = f"{dt_col}_datetime"
                    updated[new_col] = parsed
                    append_cleaning_history(f"Created '{new_col}' as parsed datetime from '{dt_col}'.",
                                            step={"op": "datetime_convert", "column": dt_col, "overwrite": False})
                st.session_state["df"] = updated
                st.success("Date/time conversion applied.")
                st.rerun()
        else:
            st.markdown("**Extract date components**")
            extract_opts = st.multiselect(
                "Components to extract as new columns",
                ["Year", "Month", "Day", "Weekday", "Hour"],
                key="dt_extract_opts"
            )
            if st.button("📆 Extract Components", width="stretch", key="apply_dt_extract_btn"):
                if not extract_opts:
                    st.warning("Select at least one component to extract.")
                else:
                    updated = df.copy()
                    s = pd.to_datetime(updated[dt_col], errors="coerce")
                    if "Year" in extract_opts:
                        updated[f"{dt_col}_year"] = s.dt.year
                    if "Month" in extract_opts:
                        updated[f"{dt_col}_month"] = s.dt.month
                    if "Day" in extract_opts:
                        updated[f"{dt_col}_day"] = s.dt.day
                    if "Weekday" in extract_opts:
                        updated[f"{dt_col}_weekday"] = s.dt.day_name()
                    if "Hour" in extract_opts:
                        updated[f"{dt_col}_hour"] = s.dt.hour
                    st.session_state["df"] = updated
                    append_cleaning_history(f"Extracted {', '.join(extract_opts)} from '{dt_col}'.",
                                            step={"op": "datetime_extract", "column": dt_col, "parts": list(extract_opts)})
                    st.success("Date components extracted.")
                    st.rerun()


def _tab_column_stats(df: pd.DataFrame) -> None:
    """Column Stats tab."""
    render_section_heading("Column Statistics")
    stat_col = st.selectbox("Choose a column", list(df.columns), key="stats_selected_col")
    stats = get_column_statistics(df, stat_col)
    stat_type = stats.pop("type")
    stat_cols = st.columns(4)
    for i, (label, value) in enumerate(stats.items()):
        display_value = f"{value:,}" if isinstance(value, (int, float)) else str(value)
        stat_cols[i % 4].metric(label, display_value)
    st.caption(f"Detected type: {stat_type.title()}")


def _tab_before_after(df: pd.DataFrame, original_df: pd.DataFrame) -> None:
    """Before vs After tab."""
    render_section_heading("Before vs After Comparison")
    before_metrics = profile_dataset(original_df)
    after_metrics = profile_dataset(df)
    compare_df = pd.DataFrame({
        "Metric": ["Rows", "Columns", "Missing Values", "Duplicates", "Memory Usage"],
        "Before": [
            f"{before_metrics['rows']:,}", f"{before_metrics['columns']:,}",
            f"{before_metrics['missing']:,}", f"{before_metrics['duplicates']:,}",
            before_metrics["memory"]
        ],
        "After": [
            f"{after_metrics['rows']:,}", f"{after_metrics['columns']:,}",
            f"{after_metrics['missing']:,}", f"{after_metrics['duplicates']:,}",
            after_metrics["memory"]
        ]
    })
    st.dataframe(compare_df, width="stretch", hide_index=True)

    cleaning_report = generate_cleaning_report(before_metrics, after_metrics)
    a, b, c, d = st.columns(4)
    a.metric("Rows Removed", f"{cleaning_report['rows_removed']:,}")
    b.metric("Columns Removed", f"{cleaning_report['columns_removed']:,}")
    c.metric("Missing Repaired", f"{cleaning_report['missing_repaired']:,}")
    d.metric("Duplicates Removed", f"{cleaning_report['duplicates_removed']:,}")

    render_section_heading("Cleaning history", "Timestamped record of every change made in this session, newest first.")
    history = st.session_state.get("cleaning_history", [])
    if history:
        for entry in reversed(history):
            render_html(
                f'<div class="ap-insight ap-history"><time>{html_escape(str(entry["time"]))}</time>'
                f'<span>{html_escape(str(entry["action"]))}</span></div>'
            )
    else:
        st.info("No cleaning operations have been applied yet.")


def _tab_preview(df: pd.DataFrame) -> None:
    """Preview tab."""
    render_section_heading("Cleaned Dataset Preview")
    view_mode = st.radio(
        "View",
        ["First rows", "Last rows", "Random sample"],
        horizontal=True,
        key="preview_view_mode"
    )
    row_count = max(len(df), 1)
    if row_count <= 5:
        n_rows = row_count
        st.caption(f"Showing all {row_count} row(s) — too few rows for a range slider.")
    else:
        slider_max = min(200, row_count)
        n_rows = st.slider(
            "Rows to display", 5, slider_max, min(15, slider_max), key="preview_n_rows"
        )

    if view_mode == "First rows":
        preview_df = df.head(n_rows)
    elif view_mode == "Last rows":
        preview_df = df.tail(n_rows)
    else:
        preview_df = df.sample(min(n_rows, len(df)), random_state=42) if len(df) else df

    st.dataframe(safe_dataframe(preview_df), width="stretch", height=380)

    st.caption("To download processed data, Excel workbooks, reports, or Power BI files, open Export & Reporting.")

def _render_workflow_controls(original_df: pd.DataFrame) -> None:
    """Reset / restore buttons shown below the tabs."""
    # ---------------- K/P. WORKFLOW CONTROLS ----------------
    render_section_heading(
        "Reset & restore",
        "Reset returns to the dataset as it was when you opened this page; Restore returns to the original upload. Both clear the history.",
    )
    ctrl_a, ctrl_b = st.columns(2)
    with ctrl_a:
        if st.button("↺ Reset Changes (this session)", width="stretch", key="reset_prep_changes_btn"):
            checkpoint = st.session_state.get("prep_checkpoint")
            if checkpoint is not None:
                st.session_state["df"] = checkpoint.copy()
            st.session_state["cleaning_history"] = []
            st.success("Reverted to the dataset state from when Data Preparation was opened.")
            st.rerun()
    with ctrl_b:
        if st.button("⏮️ Restore Original Uploaded Dataset", width="stretch", key="restore_original_prep_btn"):
            st.session_state["df"] = original_df.copy()
            st.session_state["prep_checkpoint"] = original_df.copy()
            st.session_state["cleaning_history"] = []
            st.success("Original uploaded dataset restored.")
            st.rerun()


def render_data_prep_page(df: pd.DataFrame) -> None:
    render_page_intro("Clean and standardise the active dataset step by step. Every change is recorded in the cleaning history; "
                      "download results from Export & Reporting.")
    if df is None or df.empty:
        st.info("Upload a dataset first.")
        return

    dataset_name = st.session_state.get("dataset_name", "dataset")
    original_df = st.session_state.get("original_df")
    if original_df is None:
        original_df = df.copy()
        st.session_state["original_df"] = original_df

    ensure_prep_checkpoint(df, dataset_name)
    _render_overview(df)

    tabs = st.tabs([
        "📋 Data Quality",
        "🧹 Missing Values",
        "🗂️ Duplicates",
        "🧱 Columns",
        "🔤 Text Cleaning",
        "🔢 Numeric Check",
        "🕐 Date/Time",
        "🔎 Column Stats",
        "📈 Before vs After",
        "👁️ Preview"
    ])
    panels = [
        lambda: _tab_data_quality(df),
        lambda: _tab_missing_values(df),
        lambda: _tab_duplicates(df),
        lambda: _tab_columns(df),
        lambda: _tab_text_cleaning(df),
        lambda: _tab_numeric_check(df),
        lambda: _tab_datetime(df),
        lambda: _tab_column_stats(df),
        lambda: _tab_before_after(df, original_df),
        lambda: _tab_preview(df),
    ]
    for index, (tab, render_panel) in enumerate(zip(tabs, panels)):
        with tab, card_container(f"prep_tab_{index}"):
            render_panel()

    _render_workflow_controls(original_df)
