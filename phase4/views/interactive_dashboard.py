"""Interactive Dashboard page: filters, KPI cards, custom charts and the Smart Dashboard Builder.

All charts come from data/charts.py and all aggregation from data/aggregation.py, so
this module only decides *what to show*; it does not compute statistics itself.
"""

from __future__ import annotations

import logging
from html import escape
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.aggregation import aggregate_values, normalize_aggregation
from data.charts import CHART_TYPES, build_donut, build_trend_chart, finish_figure, safe_build_chart
from data.columns import columns_by_role, measure_first, rank_measures
from data.dashboard_cards import (
    compact_number,
    completeness_summary,
    composition,
    kpi_cards,
    latest_records,
    quality_checks,
)
from data.export import (
    dataframe_to_csv_bytes,
    dataframe_to_excel_bytes,
    excel_export_available,
)
from data.loader import detect_datetime_columns
from utils.dataframe_utils import safe_dataframe
from utils.helpers import categorical_columns, numeric_columns
from views.common import (
    CHART_COLORS,
    badge_html,
    card_container,
    render_html,
    render_page_intro,
    render_section_heading,
    style_figure,
)
from views.dashboard_ui import (
    DONUT_PALETTE,
    card_title_html,
    dashboard_css,
    kpi_row_html,
    legend_html,
    ring_html,
    status_list_html,
)

logger = logging.getLogger("analyticspro.dashboard")

_BLUE, _PURPLE = CHART_COLORS[0], CHART_COLORS[1]   # shared chart palette: indigo, teal
_KPI_STATS = ["Average", "Sum", "Median", "Minimum", "Maximum", "Count"]
_NONE = "(None)"


def _format_value(value: Any, label: str) -> str:
    """KPI text: whole number for Count, two decimals otherwise, dash when empty."""
    if value is None or pd.isna(value):
        return "—"
    return f"{value:,.0f}" if label == "Count" else f"{value:,.2f}"


def _subheading(text: str) -> None:
    """Small heading inside a card (the card's own title level)."""
    render_html(f'<div class="ap-card-title">{escape(text)}</div>')


def _show_figure(fig: go.Figure, key: str, height: int = 350, top_margin: int = 50) -> None:
    styled = style_figure(fig)
    if top_margin < 30:      # the card already has a title; a clipped in-chart title would only repeat it
        styled.update_layout(title_text=None)
    st.plotly_chart(finish_figure(styled, height, top_margin), width="stretch", key=key)


def _show_chart(
    df: pd.DataFrame,
    chart_type: str,
    key: str,
    *,
    height: int = 350,
    top_margin: int = 50,
    **options: Any,
) -> bool:
    """Build a chart with the shared builder and show it, or show why it cannot be built."""
    fig, message = safe_build_chart(df, chart_type, **options)
    if fig is None:
        st.info(f"{chart_type}: {message}")
        return False
    _show_figure(fig, key, height, top_margin)
    return True


# --------------------------------------------------------------------------- filters
def _date_filter(filtered: pd.DataFrame, date_cols: list) -> tuple[pd.DataFrame, str]:
    """Date-column picker + range slider. Returns (filtered, date_col)."""
    date_col = st.selectbox("Date filter", [_NONE] + date_cols, key="linked_dash_date_col")
    if date_col != _NONE:
        parsed = pd.to_datetime(filtered[date_col], errors="coerce").dropna()
        if not parsed.empty:
            min_date, max_date = parsed.min().date(), parsed.max().date()
            picked = st.date_input("Date range", value=(min_date, max_date), min_value=min_date,
                                   max_value=max_date, key=f"linked_dash_date_range_{date_col}")
            if isinstance(picked, (tuple, list)) and len(picked) == 2:
                dates = pd.to_datetime(filtered[date_col], errors="coerce").dt.date
                filtered = filtered[dates.between(picked[0], picked[1])]
    return filtered, date_col


def _category_filter(filtered: pd.DataFrame, category: str, key_prefix: str, label: str) -> pd.DataFrame:
    """Multiselect of the values of ``category``; empty selection keeps everything."""
    values = sorted(filtered[category].dropna().astype(str).unique().tolist())
    chosen = st.multiselect(label, values, default=[], key=f"{key_prefix}{category}",
                            help="Leave empty to include every category.")
    if chosen:
        filtered = filtered[filtered[category].astype(str).isin(chosen)]
    return filtered


def _range_filter(filtered: pd.DataFrame, nums: list) -> pd.DataFrame:
    """Optional numeric range slider (missing values are kept)."""
    range_col = st.selectbox("Optional numeric range filter", [_NONE] + nums, key="linked_dash_range_column") if nums else _NONE
    if range_col == _NONE:
        return filtered
    numeric_all = pd.to_numeric(filtered[range_col], errors="coerce")
    valid = numeric_all.dropna()
    if valid.empty:
        return filtered
    low, high = float(valid.min()), float(valid.max())
    if low >= high:
        st.caption(f"{range_col} has only one distinct non-missing value; no range slider is needed.")
        return filtered
    chosen = st.slider(f"Range for {range_col}", min_value=low, max_value=high, value=(low, high),
                       key=f"linked_dash_num_range_{range_col}")
    return filtered[numeric_all.between(chosen[0], chosen[1]) | numeric_all.isna()]


def _render_filters(df: pd.DataFrame, nums: list, cats: list, date_cols: list) -> tuple[pd.DataFrame, dict]:
    """Draw the slicers and return ``(filtered, settings)`` where settings is a dict."""
    filtered = df.copy()
    render_section_heading("Dashboard filters", "Slice the data. Every KPI card, chart, table and download below uses the filtered records.")
    with card_container("dash_filters"):
        f1, f2, f3, f4 = st.columns([1.05, 1.2, 1.2, 1.15])
        with f1:
            metric = st.selectbox("Primary metric", nums, key="linked_dash_metric") if nums else None
            aggregation = st.selectbox("Aggregation", ["Sum", "Average", "Median", "Count"], key="linked_dash_aggregation")
        with f2:
            category = st.selectbox("Segment by", [_NONE] + cats, key="linked_dash_category")
            if category != _NONE:
                filtered = _category_filter(filtered, category, "linked_dash_values_", "Keep categories")
        with f3:
            filtered, date_col = _date_filter(filtered, date_cols)
        with f4:
            grain = st.selectbox("Trend interval", ["Daily", "Weekly", "Monthly"], key="linked_dash_trend_grain",
                                 disabled=date_col == _NONE)
        remaining = [c for c in cats if c != category]
        extra_col, range_col = st.columns(2) if remaining else (None, st.container())
        if extra_col is not None:
            with extra_col:
                extra = st.selectbox("Additional slicer", [_NONE] + remaining, key="linked_dash_extra_category")
                if extra != _NONE:
                    filtered = _category_filter(filtered, extra, "linked_dash_second_values_", "Filter additional values")
        with range_col:
            filtered = _range_filter(filtered, nums)
    return filtered, {"metric": metric, "aggregation": aggregation, "category": category,
                      "date_col": date_col, "grain": grain}


# --------------------------------------------------------------------------- KPI + custom charts
def _render_kpi_cards(df: pd.DataFrame, filtered: pd.DataFrame, settings: dict) -> None:
    """The four headline KPI cards (records, chosen metric, completeness, segments)."""
    category = settings["category"] if settings["category"] != _NONE else None
    cards = kpi_cards(df, filtered, settings["metric"], settings["aggregation"], category)
    render_html(kpi_row_html(cards))


def _render_composition_card(filtered: pd.DataFrame, settings: dict, cats: list) -> None:
    """Donut of the chosen metric's total split by category, with a legend (top 5 + Other)."""
    category = settings["category"] if settings["category"] != _NONE else (cats[0] if cats else None)
    result = composition(filtered, category, settings["metric"], settings["aggregation"])
    with st.container(key="dashcard_composition"):
        render_html(card_title_html("Composition", f"by {category}" if category else ""))
        if not result["items"]:
            st.info(result["note"] or "Nothing to compare yet.")
            return
        donut_col, legend_col = st.columns([1, 1.15])
        with donut_col:
            fig = build_donut([i["label"] for i in result["items"]], [i["value"] for i in result["items"]],
                              compact_number(result["total"]), result["basis"], DONUT_PALETTE)
            st.plotly_chart(fig, width="stretch", key="dash_donut")
        with legend_col:
            render_html(legend_html(result["items"], compact_number))


def _render_quality_card(filtered: pd.DataFrame) -> None:
    with st.container(key="dashcard_quality"):
        render_html(card_title_html("Data Quality Checks"))
        render_html(status_list_html(quality_checks(filtered)))


def _render_progress_card(filtered: pd.DataFrame) -> None:
    summary = completeness_summary(filtered)
    with st.container(key="dashcard_progress"):
        render_html(card_title_html("Completeness"))
        render_html(ring_html(
            summary["complete_rows_pct"], f"{summary['complete_rows_pct']:.0f}%",
            f"{summary['complete_rows']:,} / {summary['total_rows']:,}",
            [(f"{summary['complete_rows']:,}", "Complete rows"), (f"{summary['rows_with_gaps']:,}", "Rows with gaps"),
             (f"{summary['duplicate_rows']:,}", "Duplicate rows")]))


def _render_overview_row(filtered: pd.DataFrame, settings: dict, cats: list) -> None:
    left, middle, right = st.columns([1.35, 1, 0.9])
    with left:
        _render_composition_card(filtered, settings, cats)
    with middle:
        _render_quality_card(filtered)
    with right:
        _render_progress_card(filtered)


def _render_custom_kpis(filtered: pd.DataFrame, nums: list, measures: list) -> None:
    _subheading("Choose KPI cards")
    if not nums:
        st.info("Upload a dataset with numeric columns to create custom KPI cards.")
        return
    pick_col, stat_col = st.columns([3, 1])
    with pick_col:
        selected = st.multiselect("Numeric columns for KPI cards", nums, default=(measures or nums)[:3],
                                  key="linked_dash_custom_kpi_columns", help="Select the numeric fields you want to monitor.")
    with stat_col:
        stat = st.selectbox("KPI calculation", _KPI_STATS, key="linked_dash_custom_kpi_stat")
    if selected:
        columns = st.columns(min(4, len(selected)))
        for i, name in enumerate(selected):
            with columns[i % len(columns)]:
                st.metric(f"{stat} {name}", _format_value(aggregate_values(filtered[name], stat), stat))


def _render_custom_charts(
    filtered: pd.DataFrame,
    nums: list,
    cats: list,
    date_cols: list,
    settings: dict,
) -> None:
    st.divider()
    _subheading("Choose charts")
    chosen = st.multiselect(
        "Charts to display", list(CHART_TYPES), default=["Bar Chart", "Line Chart", "Area Chart"],
        key="linked_dash_custom_chart_types",
        help="Select one or more chart types. Some charts require categorical or numeric columns.")
    x_options = list(dict.fromkeys(cats + date_cols + nums))
    x_default = (settings["category"] if settings["category"] != _NONE
                 else settings["date_col"] if settings["date_col"] != _NONE
                 else (x_options[0] if x_options else None))
    y_default = settings["metric"] if settings["metric"] in nums else (nums[0] if nums else None)
    xc, yc, cc = st.columns(3)
    with xc:
        x_col = st.selectbox("X-axis / category", x_options,
                             index=x_options.index(x_default) if x_default in x_options else 0,
                             key="linked_dash_custom_x") if x_options else None
    with yc:
        y_col = st.selectbox("Y-axis / numeric value", nums, index=nums.index(y_default) if y_default in nums else 0,
                             key="linked_dash_custom_y") if nums else None
    with cc:
        color_by = st.selectbox("Color / group by (optional)", [_NONE] + cats, key="linked_dash_custom_color")

    if not chosen:
        return
    columns = st.columns(2)
    shown = 0
    for chart_type in chosen:
        fig, message = safe_build_chart(
            filtered, chart_type, x=x_col, y=None if chart_type in ("Pie Chart", "Donut Chart") else y_col,
            color=None if color_by == _NONE else color_by, agg=settings["aggregation"],
            top_n=30, columns=nums, date_columns=date_cols)
        with columns[shown % 2] if fig is not None else st.container():
            if fig is None:
                st.info(f"{chart_type}: {message}")
            else:
                _show_figure(fig, f"linked_dash_custom_chart_{shown}")
        if fig is not None:
            shown += 1


def _render_customize_section(
    filtered: pd.DataFrame,
    nums: list,
    cats: list,
    date_cols: list,
    settings: dict,
    measures: list,
) -> None:
    render_section_heading("Customize your dashboard", "Choose your own KPI cards and chart types. All results update with the filters "
                           "above, and charts use the Aggregation chosen above.")
    with card_container("dash_customize"):
        _render_custom_kpis(filtered, nums, measures)
        _render_custom_charts(filtered, nums, cats, date_cols, settings)


# --------------------------------------------------------------------------- smart builder
def _smart_columns(filtered: pd.DataFrame) -> tuple[list, list, list]:
    """Pick columns for the generated dashboard: real measures/categories, never identifiers."""
    roles = columns_by_role(filtered)
    measures = [c for c in rank_measures(roles["measure"])
                if pd.to_numeric(filtered[c], errors="coerce").notna().any()]
    if not measures:
        measures = [c for c in numeric_columns(filtered, exclude_id=False)
                    if pd.to_numeric(filtered[c], errors="coerce").notna().any()]
    cats = roles["category"] or categorical_columns(filtered)
    return measures, cats, detect_datetime_columns(filtered)


def _render_smart_builder(filtered: pd.DataFrame, aggregation: str) -> None:
    render_section_heading("Smart Dashboard Builder", "Generate a suggested dashboard from the active filtered data. Existing slicers "
                           "and manual charts remain available. It is rule-based and runs locally; no AI service is called.")
    with card_container("dash_smart"):
        _smart_builder_body(filtered, aggregation)


def _smart_builder_body(filtered: pd.DataFrame, aggregation: str) -> None:
    build_col, hide_col, _spacer = st.columns([1.3, 1.7, 4])
    with build_col:
        if st.button("⚡ Build dashboard", key="linked_dash_build_smart", type="primary", width="stretch"):
            st.session_state["linked_dash_smart_built"] = True
    with hide_col:
        if st.button("Hide generated dashboard", key="linked_dash_hide_smart", width="stretch"):
            st.session_state["linked_dash_smart_built"] = False
    if not st.session_state.get("linked_dash_smart_built", False):
        return

    nums, cats, dates = _smart_columns(filtered)
    st.divider()
    _subheading("Generated dashboard")
    if nums:
        kpi_cols = st.columns(min(4, len(nums)))
        for i, name in enumerate(nums[:4]):
            values = pd.to_numeric(filtered[name], errors="coerce").dropna()
            with kpi_cols[i]:
                st.metric(f"Average {name}", _format_value(aggregate_values(values, "Average"), "Average"))
                st.caption(f"Total: {values.sum():,.2f} · Valid values: {len(values):,}")

    plan = []   # (key, chart type, options)
    if cats and nums:
        plan.append(("linked_dash_smart_bar", "Bar Chart", dict(x=cats[0], y=nums[0], agg=aggregation, top_n=12, color_sequence=[_BLUE])))
    elif nums:
        plan.append(("linked_dash_smart_hist", "Histogram", dict(y=nums[0], color_sequence=[_BLUE])))
    if len(nums) >= 2:
        plan.append(("linked_dash_smart_scatter", "Scatter Plot", dict(x=nums[0], y=nums[1], color=cats[0] if cats else None)))
        plan.append(("linked_dash_smart_corr", "Heatmap", dict(columns=nums)))

    slots = st.columns(2)
    shown = 0

    def place(fig, key):
        nonlocal shown
        with slots[shown % 2]:
            _show_figure(fig, key)
        shown += 1

    for key, chart_type, options in plan[:1]:
        fig, message = safe_build_chart(filtered, chart_type, **options)
        if fig is not None:
            place(fig, key)
    if dates and nums:
        try:
            place(build_trend_chart(filtered, dates[0], nums[0], aggregation, "Monthly", [_PURPLE]), "linked_dash_smart_trend")
        except ValueError:
            st.caption("The monthly trend was skipped because no valid dates remain.")
    for key, chart_type, options in plan[1:]:
        fig, message = safe_build_chart(filtered, chart_type, **options)
        if fig is not None:
            place(fig, key)
        else:
            st.caption(f"{chart_type} skipped: {message}")
    if not nums and not cats:
        st.info("This dataset has no usable numeric or categorical columns for automatic charts.")
    st.download_button("⬇️ Download generated dashboard data (CSV)", data=dataframe_to_csv_bytes(filtered),
                       file_name="analyticspro_smart_dashboard_data.csv", mime="text/csv", key="linked_dash_smart_download")


# --------------------------------------------------------------------------- explore + records
def _render_latest_records_card(filtered: pd.DataFrame, settings: dict) -> None:
    date_col = settings["date_col"] if settings["date_col"] != _NONE else None
    with st.container(key="dashcard_latest"):
        render_html(card_title_html("Latest Records", "newest first" if date_col else "first rows"))
        st.dataframe(safe_dataframe(latest_records(filtered, date_col)), width="stretch", hide_index=True)


def _render_segment_card(filtered: pd.DataFrame, settings: dict) -> None:
    """Bar chart of the metric per segment (or a histogram when no segment is chosen)."""
    metric, label, category = settings["metric"], settings["aggregation"], settings["category"]
    with st.container(key="dashcard_segments"):
        if metric and category != _NONE:
            render_html(card_title_html(f"{label} {metric} by {category}", "top 15"))
            _show_chart(filtered, "Bar Chart", "linked_dash_bar", height=300, top_margin=10, x=category, y=metric,
                        agg=label, top_n=15, palette=["#c7d2fe", "#4f46e5", "#312e81"])
        elif metric:
            render_html(card_title_html(f"Distribution of {metric}"))
            _show_chart(filtered, "Histogram", "linked_dash_hist", height=300, top_margin=10, y=metric,
                        color_sequence=[_BLUE])
        else:
            st.info("No numeric column is available for metric charts.")


def _render_records_and_segments(filtered: pd.DataFrame, settings: dict) -> None:
    left, right = st.columns([1.15, 1])
    with left:
        _render_latest_records_card(filtered, settings)
    with right:
        _render_segment_card(filtered, settings)


def _render_trend_card(filtered: pd.DataFrame, nums: list, settings: dict) -> None:
    """Trend over time (when a date column is chosen), otherwise a scatter or box plot."""
    metric, label = settings["metric"], settings["aggregation"]
    category, date_col, grain = settings["category"], settings["date_col"], settings["grain"]
    with st.container(key="dashcard_trend"):
        if date_col != _NONE and metric:
            render_html(card_title_html(f"{grain} {normalize_aggregation(label).lower()} {metric}", "trend"))
            try:
                _show_figure(build_trend_chart(filtered, date_col, metric, label, grain, [_PURPLE]), "linked_dash_trend", 330, 10)
            except ValueError:
                st.info("No valid dates remain in the filtered data.")
        elif len(nums) >= 2:
            render_html(card_title_html(f"{nums[1]} vs {nums[0]}", "relationship"))
            _show_chart(filtered, "Scatter Plot", "linked_dash_scatter", height=330, top_margin=10, x=nums[0], y=nums[1],
                        color=category if category != _NONE else None)
        elif metric:
            render_html(card_title_html(f"Spread of {metric}"))
            _show_chart(filtered, "Box Plot", "linked_dash_box", height=330, top_margin=10, y=metric, color_sequence=[_PURPLE])


def _render_records(filtered: pd.DataFrame) -> None:
    render_section_heading("Filtered records", f"Showing {min(len(filtered), 500):,} of {len(filtered):,} matching records in the preview.")
    with card_container("dash_records"):
        st.dataframe(safe_dataframe(filtered.head(500)), width="stretch", height=300)
        csv_col, xlsx_col, _spacer = st.columns([1.4, 1.4, 3])
        with csv_col:
            st.download_button("⬇️ Download filtered data (CSV)", data=dataframe_to_csv_bytes(filtered),
                               file_name="analyticspro_filtered_data.csv", mime="text/csv", key="linked_dash_download",
                               width="stretch")
        if excel_export_available():
            with xlsx_col:
                st.download_button("📗 Download filtered data (Excel)", data=dataframe_to_excel_bytes(filtered),
                                   file_name="analyticspro_filtered_data.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   key="linked_dash_excel_download", width="stretch")


def render_interactive_dashboard_page(df: pd.DataFrame) -> None:
    """Card-style dashboard: filters, KPI cards, composition / quality / completeness, records and charts.

    Every visual and download uses the same filtered frame.
    """
    if df is None or df.empty:
        st.info("Upload a dataset first.")
        return

    render_html(dashboard_css())
    name = st.session_state.get("dataset_name") or "Active dataset"
    render_page_intro(f"{name} · use the filters to update every card, chart, table and download.")

    nums = measure_first(df, numeric_columns(df, exclude_id=False))
    measures = [c for c in nums if c in set(columns_by_role(df)["measure"])]
    cats = categorical_columns(df)
    date_cols = detect_datetime_columns(df)

    # Reset dashboard controls before widgets are instantiated.
    reset_col, _spacer = st.columns([1.2, 4])
    with reset_col:
        if st.button("↺ Reset dashboard filters", key="linked_dash_reset", width="stretch"):
            for key in list(st.session_state.keys()):
                if str(key).startswith("linked_dash_") and key != "linked_dash_reset":
                    del st.session_state[key]
            st.rerun()

    filtered, settings = _render_filters(df, nums, cats, date_cols)
    if filtered.empty:
        st.warning("No records match the selected filters. Widen the filters to see results.")
        return

    share = len(filtered) / max(len(df), 1) * 100
    render_html(badge_html(f"Active slice · {len(filtered):,} of {len(df):,} records ({share:.1f}%)",
                           "success" if len(filtered) == len(df) else "info", dot=True))
    render_section_heading("Key metrics", "Each card shows the slice and its change versus the full dataset.")
    _render_kpi_cards(df, filtered, settings)
    render_section_heading("Composition, data quality and completeness", "How the slice splits by category and how clean it is.")
    _render_overview_row(filtered, settings, cats)
    render_section_heading("Records and segments", "Newest records and the metric per segment.")
    _render_records_and_segments(filtered, settings)
    render_section_heading("Trend and relationships", "Metric over time when a date filter is chosen, otherwise how numeric columns relate.")
    _render_trend_card(filtered, nums, settings)
    _render_customize_section(filtered, nums, cats, date_cols, settings, measures)
    _render_smart_builder(filtered, settings["aggregation"])
    _render_records(filtered)
