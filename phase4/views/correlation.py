"""Correlation & Relationships page."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from data.profiler import correlated_pairs
from utils.dataframe_utils import safe_dataframe
from utils.helpers import categorical_columns, numeric_columns
from views.common import (
    CHART_COLORS,
    HAS_STATSMODELS,
    badge_html,
    callout_html,
    card_container,
    goto_page_button,
    render_html,
    render_page_intro,
    render_section_heading,
    style_figure,
)

MAX_FEATURE_BADGES = 12  # numeric columns listed as chips before "+N more"


def _correlation_controls() -> tuple[str, float, str]:
    with card_container("corr_controls"):
        c1, c2, c3 = st.columns([1, 1, 1.2])
        with c1:
            method = st.selectbox("Correlation Method", ["pearson", "spearman", "kendall"], key="corr_method")
        with c2:
            threshold = st.slider("Minimum Absolute Correlation", 0.0, 1.0, 0.3, step=0.05, key="corr_threshold")
        with c3:
            color_scheme = st.selectbox("Heatmap Color Scale", ["RdBu", "Viridis", "Plasma", "Coolwarm", "Blues"],
                                        key="corr_colorscale")
    return method, threshold, color_scheme


def _render_feature_summary(df: pd.DataFrame, nums: list, pairs: list[dict]) -> None:
    """Which numeric columns are compared, how many rows have all of them, and the strongest pair found."""
    shown = "".join(badge_html(str(c), "info") + " " for c in nums[:MAX_FEATURE_BADGES])
    if len(nums) > MAX_FEATURE_BADGES:
        shown += badge_html(f"+{len(nums) - MAX_FEATURE_BADGES} more", "neutral")
    render_html(f'<div class="ap-small">Numeric features compared</div><div style="margin:4px 0 10px">{shown}</div>')
    complete = int(df[nums].dropna().shape[0])
    strongest = max(pairs, key=lambda p: abs(p["Correlation"])) if pairs else None
    a, b, c = st.columns(3)
    a.metric("Features Compared", f"{len(nums):,}")
    b.metric("Pairs Above Threshold", f"{len(pairs):,}")
    c.metric("Strongest |r|", f"{abs(strongest['Correlation']):.3f}" if strongest else "—")
    if strongest:
        st.caption(f"Strongest pair: {strongest['Feature A']} and {strongest['Feature B']} ({strongest['Strength']}). "
                   f"{complete:,} of {len(df):,} rows have a value in every compared column.")
    else:
        st.caption(f"{complete:,} of {len(df):,} rows have a value in every compared column.")


def _render_pairs_table(pairs: list[dict], threshold: float) -> None:
    render_section_heading(f"Filtered Relationships (|r| ≥ {threshold})", "Ranked by absolute correlation; each pair is listed once.")
    if pairs:
        pair_df = pd.DataFrame(pairs).sort_values(by="Correlation", key=abs, ascending=False)
        st.dataframe(safe_dataframe(pair_df), width="stretch", height=min(320, 38 + 35 * len(pair_df)), hide_index=True)
    else:
        st.info(f"No column pairs meet the correlation threshold of {threshold}.")


def _render_pair_inspector(df: pd.DataFrame, pairs: list[dict], cats: list) -> None:
    render_section_heading("Interactive Pairwise Inspector", "Pick a pair above the threshold to see how the two columns relate.")
    if not pairs:
        st.info("Adjust threshold slider to select feature pairs.")
        return
    controls, plot = st.columns([1, 2.4])
    with controls:
        chosen = st.selectbox(
            "Select Pair to Inspect", list(range(len(pairs))),
            format_func=lambda i: f"{pairs[i]['Feature A']} vs {pairs[i]['Feature B']}",
            key="corr_pair_select",
        )
        col_a, col_b = pairs[chosen]["Feature A"], pairs[chosen]["Feature B"]
        color_var = st.selectbox("Color by Categorical", ["None"] + cats, key="corr_scat_cat")
        render_html(badge_html(f"{pairs[chosen]['Strength']} · r = {pairs[chosen]['Correlation']}", "info"))
    with plot:
        scat_fig = px.scatter(
            df, x=col_a, y=col_b, color=None if color_var == "None" else color_var,
            trendline="ols" if HAS_STATSMODELS else None, title=f"Scatter: {col_b} vs {col_a}",
            color_discrete_sequence=CHART_COLORS,
        )
        st.plotly_chart(style_figure(scat_fig, 360), width="stretch")
    if not HAS_STATSMODELS:
        st.caption("Install the `statsmodels` package to overlay an OLS trendline.")


def render_correlation_page(df: pd.DataFrame) -> None:
    """Correlation matrix, ranked column pairs above a threshold, and a pairwise scatter inspector."""
    render_page_intro("See how numeric columns move together. Choose a method and a minimum strength, "
                      "then inspect any pair as a scatter plot.")
    if df is None or df.empty:
        st.info("Upload a dataset first.")
        return

    nums = numeric_columns(df, exclude_id=False)
    cats = categorical_columns(df)
    if len(nums) < 2:
        st.info("At least two numeric columns are required to run correlation analysis.")
        return

    method, threshold, color_scheme = _correlation_controls()
    corr = df[nums].corr(method=method, numeric_only=True)
    pairs = correlated_pairs(corr, threshold)
    _render_feature_summary(df, nums, pairs)

    left, right = st.columns([1.35, 1])
    with left, card_container("corr_heatmap"):
        render_section_heading("Correlation heatmap", f"{method.title()} coefficients between every pair of numeric columns.")
        fig = px.imshow(corr, text_auto=".2f", color_continuous_scale=color_scheme,
                        title=f"Correlation Matrix ({method.title()})")
        st.plotly_chart(style_figure(fig, 500), width="stretch")
    with right, card_container("corr_pairs"):
        _render_pairs_table(pairs, threshold)
    with card_container("corr_inspector"):
        _render_pair_inspector(df, pairs, cats)

    render_html(callout_html("Check the extremes", "A few unusually high or low values can distort a correlation. "
                                                   "Outlier Detection shows which records they are."))
    goto_page_button("Open Outlier Detection", "Outlier Detection", "corr_goto_outliers")
