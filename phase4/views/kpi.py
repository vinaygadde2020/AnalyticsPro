"""KPI Dashboard page: headline numbers for the whole active dataset (no filters; see Interactive Dashboard for slices)."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from data.aggregation import AGGREGATION_LABELS, aggregate_values, to_numeric_clean
from data.charts import ChartConfigError, build_donut, build_trend_chart
from data.columns import measure_first
from data.loader import detect_datetime_columns
from data.profiler import calculate_dataset_health, dataset_metrics
from utils.dataframe_utils import safe_dataframe
from utils.helpers import categorical_columns, numeric_columns
from views.common import (
    CHART_COLORS,
    badge_html,
    callout_html,
    card_container,
    goto_page_button,
    kv_rows_html,
    render_html,
    render_page_intro,
    render_section_heading,
    style_figure,
)

TREND_GRAINS = ("Monthly", "Weekly", "Daily")
DONUT_SLICES = 5  # largest categories shown; the rest are grouped as "Other"


def _render_overview_kpis(df: pd.DataFrame, nums: list, cats: list) -> None:
    m = dataset_metrics(df)
    h = calculate_dataset_health(df)
    render_section_heading("Dataset overview KPIs", "Size and quality of the whole active dataset.")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total Records", f"{m['rows']:,}")
    c2.metric("Total Columns", f"{m['columns']:,}")
    c3.metric("Numeric Metrics", f"{len(nums):,}")
    c4.metric("Categorical Features", f"{len(cats):,}")
    c5.metric("Missing Cells", f"{m['missing']:,}")
    c6.metric("Health Score", f"{h['overall']}/100")


def _render_controls(df: pd.DataFrame, nums: list, cats: list, dates: list) -> dict:
    """Metric, aggregation, category and trend settings. Returns the choices as a dict."""
    render_section_heading("Metric focus", "Choose what the cards, trend and category views below describe.")
    with card_container("kpi_controls"):
        a, b, c = st.columns(3)
        metric = a.selectbox("Select Primary Metric", nums, key="kpi_primary_metric")
        agg = b.selectbox("Aggregation for trend", AGGREGATION_LABELS, key="kpi_aggregation",
                          help="Used for the trend chart. The metric cards always show Sum, Average, Median, Min and Max.")
        category = c.selectbox("Break down metric by category", cats, key="kpi_breakdown_cat") if cats else None
        date_col, grain = None, "Monthly"
        if dates:
            d, e = st.columns(2)
            date_col = d.selectbox("Date column for trend", dates, key="kpi_trend_date")
            grain = e.selectbox("Trend interval", TREND_GRAINS, key="kpi_trend_grain")
    return {"metric": metric, "agg": agg, "category": category, "date": date_col, "grain": grain}


def _render_metric_kpis(df: pd.DataFrame, metric: str) -> bool:
    """Sum / mean / median / min / max of one column, via the shared aggregation helpers
    (missing and infinite values are ignored, as on the Interactive Dashboard). Returns False if nothing is numeric."""
    render_section_heading(f"Metric specific KPIs — {metric}", "Missing and infinite values are ignored.")
    values = df[metric]
    if to_numeric_clean(values).dropna().empty:
        st.info(f"Column '{metric}' has no numeric values to summarise.")
        return False
    labels = [("Total Sum", "Sum"), ("Average / Mean", "Average"), ("Median Value", "Median"),
              ("Minimum Value", "Min"), ("Maximum Value", "Max")]
    for column, (title, agg) in zip(st.columns(5), labels):
        column.metric(title, f"{aggregate_values(values, agg):,.2f}")
    return True


def _render_trend(df: pd.DataFrame, choice: dict) -> None:
    render_section_heading("Trend over time", f"{choice['agg']} of {choice['metric']}, grouped {choice['grain'].lower()}.")
    if not choice["date"]:
        st.info("No date column was found, so there is no trend to draw.")
        return
    try:
        fig = build_trend_chart(df, choice["date"], choice["metric"], choice["agg"], choice["grain"], color_sequence=CHART_COLORS)
    except ChartConfigError as exc:
        st.info(str(exc))
        return
    st.plotly_chart(style_figure(fig, 340), width="stretch")


def _share_frame(df: pd.DataFrame, metric: str, category: str) -> pd.DataFrame:
    """Total of ``metric`` per category value (top slices plus 'Other'); missing categories are labelled 'Missing'."""
    working = pd.DataFrame({"cat": df[category].astype("object").where(df[category].notna(), "Missing").astype(str),
                            "val": to_numeric_clean(df[metric])})
    totals = working.groupby("cat")["val"].sum(min_count=1).dropna().sort_values(ascending=False)
    totals = totals[totals > 0]
    top, rest = totals.head(DONUT_SLICES), float(totals.iloc[DONUT_SLICES:].sum())
    frame = pd.DataFrame({"Category": top.index.tolist(), "Total": top.values.tolist()})
    if rest > 0:
        frame = pd.concat([frame, pd.DataFrame({"Category": ["Other"], "Total": [rest]})], ignore_index=True)
    return frame


def _render_share(df: pd.DataFrame, choice: dict) -> None:
    render_section_heading("Category share", f"Share of total {choice['metric']} (sum) by {choice['category']}." if choice["category"]
                           else "Share of total by category.")
    if not choice["category"]:
        st.info("No categorical column was found for a share view.")
        return
    frame = _share_frame(df, choice["metric"], choice["category"])
    if frame.empty:
        st.info("Share needs positive totals; this column has none for the selected category.")
        return
    total = float(frame["Total"].sum())
    fig = build_donut(frame["Category"].tolist(), frame["Total"].tolist(), f"{total:,.0f}", "total", CHART_COLORS, height=220)
    st.plotly_chart(fig, width="stretch")
    # The legend is text (name, value, share), so the chart is readable without colour.
    render_html(kv_rows_html([(str(r.Category), f"{r.Total:,.2f} ({r.Total / total * 100:.0f}%)") for r in frame.itertuples()]))


def _render_category_breakdown(df: pd.DataFrame, metric: str, col_cat: str) -> None:
    render_section_heading("Categorical breakdown", f"Total, average and record count of {metric} for each {col_cat}.")
    agg_df = (
        df.groupby(col_cat, dropna=False)[metric]
        .agg(["sum", "mean", "count"])
        .reset_index()
        .rename(columns={"sum": f"Total {metric}", "mean": f"Avg {metric}", "count": "Record Count"})
        .sort_values(f"Total {metric}", ascending=False)
    )
    left, right = st.columns([1.2, 1])
    with left:
        st.dataframe(safe_dataframe(agg_df.head(15)), width="stretch", height=350, hide_index=True)
    with right:
        fig = px.bar(agg_df.head(10), x=col_cat, y=f"Total {metric}", title=f"Top 10 {col_cat} by {metric}")
        st.plotly_chart(style_figure(fig, 350), width="stretch")


def render_kpi_dashboard_page(df: pd.DataFrame) -> None:
    """Whole-dataset headline KPIs, a chosen metric's statistics, a trend and a per-category breakdown."""
    render_page_intro("Headline numbers for the whole dataset, with a trend and top segments. "
                      "To slice by filters or build your own cards, use the Interactive Dashboard.")
    if df is None or df.empty:
        st.info("Upload a dataset first.")
        return

    nums = measure_first(df, numeric_columns(df, exclude_id=False))
    cats = categorical_columns(df)
    _render_overview_kpis(df, nums, cats)
    if not nums:
        st.info("No numeric columns found to construct numerical KPI cards.")
        return

    choice = _render_controls(df, nums, cats, detect_datetime_columns(df))
    render_html(badge_html(f"Whole dataset · {len(df):,} rows", "info"))
    if not _render_metric_kpis(df, choice["metric"]):
        return

    left, right = st.columns([1.6, 1])
    with left, card_container("kpi_trend"):
        _render_trend(df, choice)
    with right, card_container("kpi_share"):
        _render_share(df, choice)
    if choice["category"]:
        _render_category_breakdown(df, choice["metric"], choice["category"])

    render_html(callout_html("Need filters or custom cards?",
                             "The Interactive Dashboard adds category, date and numeric slicers, custom KPI cards and the Smart Dashboard Builder."))
    goto_page_button("Open Interactive Dashboard", "Interactive Dashboard", "kpi_goto_interactive")
