"""Automatic EDA page."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from data.loader import detect_datetime_columns
from data.profiler import (
    calculate_dataset_health,
    categorical_statistics,
    dataset_metrics,
    generate_eda_insights,
    numeric_statistics,
)
from data.report import insight_to_html
from utils.dataframe_utils import safe_dataframe
from utils.helpers import categorical_columns, numeric_columns
from views.common import (
    badge_html,
    callout_html,
    card_container,
    goto_page_button,
    insight_grid_html,
    insight_html,
    progress_html,
    render_html,
    render_page_intro,
    render_section_heading,
    share_bar_html,
    style_figure,
)


def _render_overview(m: dict, h: dict, nums: list, cats: list) -> None:
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Rows", f"{m['rows']:,}")
    c2.metric("Columns", f"{m['columns']:,}")
    c3.metric("Numeric", f"{len(nums):,}")
    c4.metric("Categorical", f"{len(cats):,}")
    c5.metric("Missing", f"{m['missing']:,}")
    c6.metric("Health", f"{h['overall']}/100")


def _render_health(m: dict, h: dict) -> None:
    render_section_heading("Dataset health", "Score = 60% completeness + 40% row uniqueness (see data/profiler.py).")
    a, b, c = st.columns(3)
    with a, card_container("eda_health_overall"):
        st.metric("Overall Score", f"{h['overall']}/100")
        render_html(badge_html(str(h["status"]), "success" if h["overall"] > 85 else "warning", dot=True))
    with b, card_container("eda_health_complete"):
        st.metric("Completeness", f"{h['completeness']}%")
        render_html(progress_html(h["completeness"], "Cells populated", f"{m['missing']:,} missing",
                                  "success" if m["missing"] == 0 else "warning"))
    with c, card_container("eda_health_unique"):
        st.metric("Uniqueness", f"{h['uniqueness']}%")
        render_html(progress_html(h["uniqueness"], "Distinct rows", f"{m['duplicates']:,} duplicate",
                                  "success" if m["duplicates"] == 0 else "warning"))
    if h["overall"] > 85:
        st.success(f"Dataset quality is {h['status']}.")
    elif h["overall"] > 70:
        st.info(f"Dataset quality is {h['status']}.")
    else:
        st.warning(f"Dataset quality is {h['status']}. Consider cleaning before modeling.")


def _render_insights(df: pd.DataFrame) -> None:
    render_section_heading("Automatic insights", "Fixed rules applied to your data (missing values, skew, duplicates, categories). No AI model is involved.")
    insights = generate_eda_insights(df)
    if insights:
        render_html(insight_grid_html([insight_html(insight_to_html(i)) for i in insights]))
    else:
        st.info("No automatic insights could be generated.")


def _dispersion_table(num_stats: pd.DataFrame) -> pd.DataFrame:
    """Spread of each numeric column, derived only from the statistics already computed (Q3 - Q1, max - min)."""
    needed = {"Column", "std", "25%", "50%", "75%", "min", "max"}
    if num_stats.empty or not needed <= set(num_stats.columns):
        return pd.DataFrame()
    out = pd.DataFrame({
        "Column": num_stats["Column"], "Std Dev": num_stats["std"], "Q1 (25%)": num_stats["25%"], "Median": num_stats["50%"],
        "Q3 (75%)": num_stats["75%"], "IQR (Q3 - Q1)": num_stats["75%"] - num_stats["25%"], "Range (max - min)": num_stats["max"] - num_stats["min"],
    })
    return out.round(3)


def _render_numeric_profile(df: pd.DataFrame) -> None:
    render_section_heading("Numeric feature statistical profile", "Count, centre, spread, quartiles and skewness for every numeric column.")
    num_stats = numeric_statistics(df)
    if num_stats.empty:
        st.info("No numeric columns available.")
        return
    st.dataframe(safe_dataframe(num_stats.round(3)), width="stretch", height=380, hide_index=True)
    dispersion = _dispersion_table(num_stats)
    if not dispersion.empty:
        render_section_heading("Feature dispersion & IQR", "A wider IQR means more spread in the middle 50% of values. "
                               "Use Outlier Detection for flagged records.")
        st.dataframe(safe_dataframe(dispersion), width="stretch", hide_index=True)


def _render_numeric_distributions(df: pd.DataFrame, nums: list) -> None:
    render_section_heading("Numeric distributions", "Histogram with box margin, and a box plot, for one column at a time.")
    if not nums:
        st.info("No numeric columns available for distributions.")
        return
    selected = st.selectbox("Select numeric column", nums, key="eda_distribution_col")
    left, right = st.columns(2)
    with left:
        st.plotly_chart(style_figure(px.histogram(df, x=selected, title=f"Distribution of {selected}", marginal="box")), width="stretch")
    with right:
        st.plotly_chart(style_figure(px.box(df, y=selected, title=f"Box Plot of {selected}")), width="stretch")


def _share_segments(series: pd.Series) -> list[tuple[str, float]]:
    """Top four values by count plus an 'Other' remainder (missing values are not counted)."""
    counts = series.dropna().astype(str).value_counts()
    top = counts.head(4)
    segments = [(str(k), float(v)) for k, v in top.items()]
    rest = float(counts.iloc[4:].sum())
    if rest > 0:
        segments.append(("Other", rest))
    return segments


def _render_cardinality(df: pd.DataFrame, cats: list) -> None:
    render_section_heading("Categorical cardinality & share", "Distinct values and how rows split across the most common ones.")
    if not cats:
        st.info("No categorical columns available.")
        return
    shown = cats[:6]
    blocks = []
    for col in shown:
        try:
            series = df[col]
            blocks.append(share_bar_html(str(col), f"{int(series.nunique(dropna=True)):,} distinct · {int(series.isna().sum()):,} missing",
                                         _share_segments(series)))
        except TypeError:  # unhashable cell values: skip this column rather than fail the page
            continue
    with card_container("eda_cardinality"):
        render_html("".join(blocks))
        if len(cats) > len(shown):
            st.caption(f"Showing {len(shown)} of {len(cats)} categorical columns; the table below lists all of them.")


def _render_categorical_analysis(df: pd.DataFrame, cats: list) -> None:
    cat_stats = categorical_statistics(df)
    if not cat_stats.empty:
        render_section_heading("Categorical analysis", "Unique values, missing values and the most common value per column.")
        st.dataframe(safe_dataframe(cat_stats), width="stretch", height=300, hide_index=True)
    if cats:
        selected_cat = st.selectbox("Select categorical column", cats, key="eda_category_col")
        counts = df[selected_cat].fillna("Missing").astype(str).value_counts().head(15).reset_index()
        counts.columns = ["Category", "Count"]
        fig = px.bar(counts, x="Category", y="Count", title=f"Top Categories — {selected_cat}")
        fig.update_layout(xaxis_tickangle=-35)
        st.plotly_chart(style_figure(fig), width="stretch")


def _render_missing_analysis(df: pd.DataFrame) -> None:
    render_section_heading("Missingness", "Columns with empty cells, worst first.")
    missing_df = pd.DataFrame({
        "Column": df.columns.astype(str),
        "Missing": [int(df[c].isna().sum()) for c in df.columns],
        "Missing %": [round(df[c].isna().mean() * 100, 2) for c in df.columns],
    })
    missing_df = missing_df[missing_df["Missing"] > 0].sort_values("Missing", ascending=False)
    if missing_df.empty:
        st.success("No missing values to visualize.")
        return
    left, right = st.columns([1, 1.3])
    with left, card_container("eda_missing_rows"):
        rows = "".join(
            progress_html(r["Missing %"], str(r["Column"]), f"{int(r['Missing']):,} cells · {r['Missing %']}%",
                          "danger" if r["Missing %"] >= 20 else "warning" if r["Missing %"] >= 5 else "info")
            for _, r in missing_df.head(12).iterrows()
        )
        render_html(rows)
        if len(missing_df) > 12:
            st.caption(f"Showing the 12 worst of {len(missing_df)} columns with missing values.")
    with right:
        fig = px.bar(missing_df, x="Column", y="Missing", title="Missing Values by Column")
        fig.update_layout(xaxis_tickangle=-35)
        st.plotly_chart(style_figure(fig), width="stretch")


def _render_further_analysis(m: dict, nums: list, dts: list) -> None:
    render_section_heading("Further analysis", "This page stays a first look; detailed tools live on their own pages.")
    left, right = st.columns(2)
    with left, card_container("eda_next_corr"):
        st.markdown("**📈 Correlation analysis**")
        if len(nums) >= 2:
            st.write(f"{len(nums)} numeric columns are available to compare.")
        else:
            st.write("At least two numeric columns are needed for correlation analysis.")
        goto_page_button("Open Correlation & Relationships", "Correlation & Relationships", "eda_goto_corr")
    with right, card_container("eda_next_outliers"):
        st.markdown("**⚠️ Outlier detection**")
        if nums:
            st.write(f"Outlier analysis can be performed on {len(nums)} numeric column(s).")
        else:
            st.write("No numeric columns are available for outlier analysis.")
        goto_page_button("Open Outlier Detection", "Outlier Detection", "eda_goto_outliers")
    if dts:
        st.markdown("**Date/Time columns:** " + ", ".join(f"`{c}`" for c in map(str, dts)))


def _render_conclusion(m: dict, nums: list, cats: list) -> None:
    render_section_heading("EDA conclusion")
    conclusion = ["The dataset has complete values." if m["missing"] == 0
                  else f"The dataset contains {m['missing']:,} missing cells that may require treatment."]
    conclusion.append("No duplicate rows were detected." if m["duplicates"] == 0
                      else f"{m['duplicates']:,} duplicate rows were detected.")
    if nums:
        conclusion.append(f"{len(nums)} numeric columns are available for statistical analysis.")
    if cats:
        conclusion.append(f"{len(cats)} categorical columns are available for segmentation.")
    render_html(insight_grid_html([insight_html(insight_to_html(item), "✓") for item in conclusion]))
    render_html(callout_html("Suggested next step", "Resolve missing values and duplicates in Data Preparation, or move on to the KPI Dashboard."))
    a, b = st.columns(2)
    with a:
        goto_page_button("Open Data Preparation", "Data Preparation", "eda_goto_prep")
    with b:
        goto_page_button("Proceed to KPI Dashboard", "KPI Dashboard", "eda_goto_kpi", primary=True)


def render_automatic_eda_page(df: pd.DataFrame) -> None:
    """First-look report: overview, health, insights, statistics, distributions and a conclusion."""
    render_page_intro("A first-look report built from fixed, explainable rules: data health, insights, distributions, "
                      "categories and missing values.")
    if df is None or df.empty:
        st.info("Upload a dataset first.")
        return

    m = dataset_metrics(df)
    h = calculate_dataset_health(df)
    nums = numeric_columns(df, exclude_id=False)
    cats = categorical_columns(df)
    dts = detect_datetime_columns(df)

    st.markdown(f"**Dataset:** `{st.session_state.get('dataset_name', 'Active dataset')}`")
    _render_overview(m, h, nums, cats)
    _render_health(m, h)
    _render_insights(df)
    _render_numeric_profile(df)
    _render_numeric_distributions(df, nums)
    _render_cardinality(df, cats)
    _render_categorical_analysis(df, cats)
    _render_missing_analysis(df)
    _render_further_analysis(m, nums, dts)
    _render_conclusion(m, nums, cats)
