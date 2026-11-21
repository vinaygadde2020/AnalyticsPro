"""Visualizations page and smart chart recommendations."""

from __future__ import annotations

import logging

import pandas as pd
import plotly.express as px
import streamlit as st

from data.charts import safe_build_chart
from data.columns import measure_first
from data.recommender import (
    compute_category_aggregation,
    compute_correlation_matrix,
    compute_kpi_summary,
    compute_time_trend,
    generate_visual_recommendations,
)
from utils.helpers import categorical_columns, format_number, numeric_columns
from views.common import (
    CHART_COLORS,
    badge_html,
    card_container,
    render_html,
    render_page_intro,
    render_section_heading,
    style_figure,
)

logger = logging.getLogger("analyticspro.visualizations")


def _apply_bar_recommendation(rec: dict, nums: list, cats: list, all_cols: list) -> list[str]:
    """Write a bar-chart recommendation into the manual controls; return what had to be adjusted."""
    adjusted: list[str] = []
    st.session_state["vis_chart_type"] = "Bar Chart"
    x_opts = cats if cats else all_cols
    y_opts = nums if nums else all_cols
    x_col = rec.get("x_column")
    y_col = rec.get("y_column")
    if x_col not in x_opts:
        x_col = x_opts[0] if x_opts else None
        adjusted.append("category column")
    if y_col not in y_opts:
        y_col = y_opts[0] if y_opts else None
        if rec.get("y_column") is not None:
            adjusted.append("metric column")
    if x_col is not None:
        st.session_state["vis_group_x"] = x_col
    if y_col is not None:
        st.session_state["vis_metric_y"] = y_col
    if rec.get("aggregation"):
        st.session_state["vis_agg"] = rec["aggregation"]
    return adjusted


def _apply_single_numeric_recommendation(chart_type: str, rec: dict, nums: list, all_cols: list) -> list[str]:
    """Histogram / box plot recommendation: pick the one numeric column (histogram prefers X, box prefers Y)."""
    adjusted: list[str] = []
    st.session_state["vis_chart_type"] = chart_type
    opts = nums if nums else all_cols
    first, second = ("x_column", "y_column") if chart_type == "Histogram" else ("y_column", "x_column")
    col = rec.get(first) or rec.get(second)
    if col not in opts:
        col = opts[0] if opts else None
        adjusted.append("numeric column")
    if col is not None:
        st.session_state["vis_single_num"] = col
    st.session_state["vis_color_by"] = "None"
    return adjusted


def _apply_scatter_recommendation(rec: dict, nums: list) -> list[str]:
    """Scatter recommendation: needs two distinct numeric columns."""
    adjusted: list[str] = []
    st.session_state["vis_chart_type"] = "Scatter Plot"
    if len(nums) < 2:
        return ["not enough numeric columns for a scatter plot"]
    x_col = rec.get("x_column")
    y_col = rec.get("y_column")
    if x_col not in nums:
        x_col = nums[0]
        adjusted.append("X-axis column")
    valid_y_opts = [c for c in nums if c != x_col] or nums
    if y_col not in valid_y_opts:
        y_col = valid_y_opts[0]
        adjusted.append("Y-axis column")
    st.session_state["vis_scat_x"] = x_col
    st.session_state["vis_scat_y"] = y_col
    st.session_state["vis_scat_cat"] = "None"
    return adjusted


def _apply_recommendation(rec: dict, nums: list, cats: list, all_cols: list) -> None:
    """
    Best-effort mapping of a Smart Visual Recommendation onto the
    manual visualization control widgets' session-state keys.

    Only ever writes a column value that is a genuine member of the
    same options list the corresponding widget itself uses (computed
    fresh from the current dataframe), so the manual controls below
    never receive an out-of-range / stale selection. If a recommended
    column isn't a valid option for that widget, a compatible
    fallback is chosen instead and noted so the user isn't silently
    given something different from what was recommended.
    """
    chart_type = rec["chart_type"]
    adjusted: list[str] = []
    if chart_type == "Bar Chart":
        adjusted = _apply_bar_recommendation(rec, nums, cats, all_cols)
    elif chart_type in ("Histogram", "Box Plot"):
        adjusted = _apply_single_numeric_recommendation(chart_type, rec, nums, all_cols)
    elif chart_type == "Scatter Plot":
        adjusted = _apply_scatter_recommendation(rec, nums)
    st.session_state["smart_rec_last_applied"] = {"title": rec["title"], "adjusted": adjusted}


def _render_recommendation_preview(df: pd.DataFrame, rec: dict) -> None:
    """
    Render an inline preview for a "summary-style" recommendation
    (one that doesn't map onto the existing manual chart controls).
    """
    chart_type = rec["chart_type"]
    try:
        if chart_type == "KPI Summary":
            summary = compute_kpi_summary(df, rec.get("columns") or [])
            if summary:
                metric_cols = st.columns(len(summary))
                for widget, item in zip(metric_cols, summary):
                    with widget:
                        mean_display = format_number(item["mean"]) if item["mean"] is not None else "—"
                        sum_display = format_number(item["sum"]) if item["sum"] is not None else "—"
                        st.metric(item["column"], mean_display)
                        st.caption(f"Sum: {sum_display} • Missing: {item['missing']:,}")

        elif chart_type == "Time Trend":
            trend_df = compute_time_trend(df, rec["x_column"], rec["y_column"], rec.get("aggregation") or "Mean")
            if not trend_df.empty:
                fig = px.line(
                    trend_df, x=rec["x_column"], y=rec["y_column"], markers=True,
                    title=rec["title"], color_discrete_sequence=CHART_COLORS,
                )
                st.plotly_chart(style_figure(fig, 320), width="stretch")
            else:
                st.caption("Not enough valid date values to build a trend preview.")

        elif chart_type == "Bottom Categories":
            bottom_df = compute_category_aggregation(
                df, rec["x_column"], rec["y_column"], rec.get("aggregation") or "Sum",
                ascending=True, top_n=10
            )
            if not bottom_df.empty:
                fig = px.bar(bottom_df, x=rec["x_column"], y=rec["y_column"], title=rec["title"],
                             color_discrete_sequence=CHART_COLORS)
                st.plotly_chart(style_figure(fig, 320), width="stretch")

        elif chart_type == "Correlation Heatmap":
            corr = compute_correlation_matrix(df, rec.get("columns") or [])
            if not corr.empty:
                fig = px.imshow(
                    corr, text_auto=".2f", title=rec["title"],
                    color_continuous_scale="RdBu_r", zmin=-1, zmax=1
                )
                st.plotly_chart(style_figure(fig, 380), width="stretch")
    except (ValueError, TypeError, KeyError) as exc:
        logger.warning("Recommendation preview failed (%s)", type(exc).__name__)
        st.caption("Preview unavailable for this recommendation.")


def _render_smart_recommendations(df: pd.DataFrame, nums: list, cats: list, all_cols: list) -> None:
    """
    Renders the "Smart Visual Recommendations" section: a data-driven
    set of chart suggestions generated from the current dataframe.
    This is purely additive - it never removes or alters the manual
    visualization controls that follow it.
    """
    recs = generate_visual_recommendations(df)

    with st.expander("✨ Smart Visual Recommendations", expanded=True):
        if not recs:
            st.caption("No automatic recommendations for this dataset yet — use the manual controls below.")
            return

        st.caption(
            "Data-driven chart suggestions based on this dataset's actual columns. "
            "The manual controls below remain fully available."
        )

        last_applied = st.session_state.pop("smart_rec_last_applied", None)
        if last_applied:
            msg = f"Applied **{last_applied['title']}** to the manual controls below."
            if last_applied.get("adjusted"):
                msg += f" (auto-adjusted: {', '.join(last_applied['adjusted'])})"
            st.success(msg)

        for i, rec in enumerate(recs):
            with card_container(f"viz_rec_{i}"):
                header_col, action_col = st.columns([5, 1.3])
                with header_col:
                    render_html(badge_html(str(rec["chart_type"]), "info"))
                    st.markdown(f"**{rec['title']}**")
                    st.caption(rec["description"])
                    st.caption(f"Why: {rec['reason']}")
                with action_col:
                    if rec["interactive"] and st.button("Use this", key=f"smart_rec_apply_{i}", width="stretch"):
                        _apply_recommendation(rec, nums, cats, all_cols)
                        st.rerun()
                if not rec["interactive"]:
                    _render_recommendation_preview(df, rec)


# Plotly's builtin sequential module has no "Indigo" scale, so a custom indigo palette
# (matching the app's brand colour) is defined here.
INDIGO_SEQUENTIAL = [
    "#eef2ff", "#c7d2fe", "#a5b4fc", "#818cf8",
    "#6366f1", "#4f46e5", "#4338ca", "#3730a3", "#312e81",
]
PALETTES = {
    "Indigo": INDIGO_SEQUENTIAL,
    "Viridis": px.colors.sequential.Viridis,
    "Plasma": px.colors.sequential.Plasma,
    "Cividis": px.colors.sequential.Cividis,
    "Spectral": px.colors.colorbrewer.Spectral,
    "Blues": px.colors.sequential.Blues,
}
MANUAL_CHART_TYPES = ["Bar Chart", "Line Chart", "Area Chart", "Pie Chart", "Histogram", "Box Plot", "Violin Plot", "Scatter Plot"]


def _style_controls() -> tuple[str, list, int, bool]:
    """Chart type, colour palette, height and gridline controls."""
    chart_type = st.selectbox("Chart Type", MANUAL_CHART_TYPES, key="vis_chart_type")
    theme = st.selectbox("Color Palette", list(PALETTES), key="vis_palette")
    chart_height = st.slider("Chart Height", 350, 700, 450, step=50, key="vis_height")
    show_grid = st.checkbox("Show Gridlines", value=True, key="vis_grid")
    return chart_type, PALETTES.get(theme, INDIGO_SEQUENTIAL), chart_height, show_grid


def _grouped_chart_options(chart_type: str, nums: list, cats: list, all_cols: list, color_seq: list) -> dict:
    """Controls for bar/line/area/pie: group by X, aggregate Y."""
    x_options = cats if cats else all_cols
    y_options = nums if nums else all_cols
    x_default = 0
    if not cats and y_options:
        # No text column: avoid defaulting X to the very column used for Y.
        x_default = next((i for i, col in enumerate(x_options) if col != y_options[0]), 0)
    x_col = st.selectbox("Category / Grouping Column (X)", x_options, index=x_default, key="vis_group_x")
    y_col = st.selectbox("Numerical Metric (Y)", y_options, key="vis_metric_y")
    agg_func = st.selectbox("Aggregation Method", ["Sum", "Mean", "Count", "Median", "Min", "Max"], key="vis_agg")
    top_n = st.slider("Limit Top Items", 5, 50, 10, key="vis_top_n")
    options: dict = dict(x=x_col, y=y_col, agg=agg_func, top_n=top_n, aggregate_numeric_x=True)
    options["palette" if chart_type == "Bar Chart" else "color_sequence"] = color_seq
    return options


def _distribution_options(chart_type: str, nums: list, cats: list, all_cols: list, color_seq: list) -> dict:
    """Controls for histogram/box/violin: one numeric column, optional grouping."""
    target_col = st.selectbox("Select Numerical Column", nums if nums else all_cols, key="vis_single_num")
    color_by = st.selectbox("Group / Color by (Optional)", ["None"] + cats, key="vis_color_by")
    color_var = None if color_by == "None" else color_by
    options: dict = dict(y=target_col, color=color_var, color_sequence=color_seq)
    if chart_type == "Histogram":
        options["bins"] = st.slider("Number of Bins", 5, 100, 30, key="vis_bins")
    else:
        options["x"] = color_var
        options["violin_points"] = "all"
    return options


def _scatter_options(nums: list, cats: list, color_seq: list) -> dict:
    """Controls for a scatter plot; empty dict (with a note) if fewer than two numeric columns."""
    if len(nums) < 2:
        st.info("At least two numeric columns are required for a Scatter Plot.")
        return {}
    x_num = st.selectbox("X-Axis (Numeric)", nums, key="vis_scat_x")
    y_num = st.selectbox("Y-Axis (Numeric)", [col for col in nums if col != x_num] or nums, key="vis_scat_y")
    color_cat = st.selectbox("Color Category (Optional)", ["None"] + cats, key="vis_scat_cat")
    return dict(x=x_num, y=y_num, color=None if color_cat == "None" else color_cat, color_sequence=color_seq)


def _chart_options(chart_type: str, nums: list, cats: list, all_cols: list, color_seq: list) -> dict:
    """Draw the controls that belong to ``chart_type`` and return the builder options."""
    if chart_type in ("Bar Chart", "Line Chart", "Area Chart", "Pie Chart"):
        return _grouped_chart_options(chart_type, nums, cats, all_cols, color_seq)
    if chart_type in ("Histogram", "Box Plot", "Violin Plot"):
        return _distribution_options(chart_type, nums, cats, all_cols, color_seq)
    return _scatter_options(nums, cats, color_seq)


def render_visualizations_page(df: pd.DataFrame) -> None:
    """Build one styled chart at a time, plus automatic chart recommendations."""
    render_page_intro("Build one chart at a time with full styling control (palette, height, grid). "
                      "For filters, KPI cards and several charts at once, use the Interactive Dashboard.")

    if df is None or df.empty:
        st.info("Upload a dataset first.")
        return

    nums = measure_first(df, numeric_columns(df, exclude_id=False))
    cats = categorical_columns(df)
    all_cols = list(df.columns)
    if not all_cols:
        st.info("No columns available to visualize.")
        return

    _render_smart_recommendations(df, nums, cats, all_cols)

    render_section_heading("Chart studio", "Choose a chart type, style and columns on the left; the chart updates with every change.")
    config_col, chart_col = st.columns([1, 2.3])
    with config_col, card_container("viz_config"):
        render_section_heading("Chart type and style")
        chart_type, color_seq, chart_height, show_grid = _style_controls()
        st.divider()
        render_section_heading("Data mapping")
        options = _chart_options(chart_type, nums, cats, all_cols, color_seq)
    if not options:
        return
    with chart_col, card_container("viz_chart"):
        render_html(badge_html(chart_type, "info") + " " + badge_html(f"{len(df):,} rows", "neutral"))
        fig, message = safe_build_chart(df, chart_type, **options)
        if fig is None:
            st.info(message)
            return
        style_figure(fig)
        fig.update_layout(height=chart_height, xaxis=dict(showgrid=show_grid), yaxis=dict(showgrid=show_grid))
        st.plotly_chart(fig, width="stretch")
