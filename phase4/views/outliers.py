"""Outlier Detection page."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from data.profiler import detect_outliers
from utils.dataframe_utils import safe_dataframe
from utils.helpers import numeric_columns
from views.common import (
    CHART_COLORS,
    TOKENS,
    badge_html,
    callout_html,
    card_container,
    goto_page_button,
    render_html,
    render_page_intro,
    render_section_heading,
    style_figure,
)


def render_outlier_page(df: pd.DataFrame) -> None:
    render_page_intro("Find unusually high or low values in one numeric column, using the IQR (Tukey) rule "
                      "or a z-score threshold. Records are only flagged here; nothing is changed or removed.")
    if df is None or df.empty:
        st.info("Upload a dataset first.")
        return

    nums = numeric_columns(df, exclude_id=False)
    if not nums:
        st.info("No numeric columns available for outlier detection.")
        return

    with card_container("outlier_controls"):
        c1, c2, c3 = st.columns(3)
        with c1:
            target_col = st.selectbox("Target Column", nums, key="outlier_col")
        with c2:
            method = st.radio("Detection Method", ["IQR Method", "Z-Score Method"], horizontal=True, key="outlier_method")
        with c3:
            if method == "IQR Method":
                multiplier = st.slider("IQR Multiplier", 1.0, 3.0, 1.5, step=0.1, key="iqr_mult")
            else:
                z_thresh = st.slider("Z-Score Threshold", 1.5, 4.0, 3.0, step=0.1, key="z_thresh")

    s = df[target_col].dropna()
    if s.empty:
        st.info("Selected column contains no usable numeric data.")
        return

    if method == "IQR Method":
        detected = detect_outliers(df[target_col], "iqr", multiplier)
        rule = f"IQR rule · {multiplier}× IQR beyond Q1 and Q3"
    else:
        detected = detect_outliers(df[target_col], "zscore", z_thresh)
        rule = f"Z-score rule · more than {z_thresh} standard deviations from the mean"
    outlier_mask, lower_bound, upper_bound = detected.mask, detected.lower, detected.upper

    outlier_count = int(outlier_mask.sum())
    outlier_pct = round((outlier_count / max(len(df), 1)) * 100, 2)

    status = (badge_html("No outliers flagged", "success", dot=True) if outlier_count == 0
              else badge_html(f"{outlier_count:,} records flagged", "danger", dot=True))
    render_html(f"{status} {badge_html(rule, 'info')} {badge_html(str(target_col), 'neutral')}")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Outliers", f"{outlier_count:,}")
    k2.metric("Outlier Percentage", f"{outlier_pct}%")
    k3.metric("Lower Bound Limit", f"{lower_bound:,.2f}")
    k4.metric("Upper Bound Limit", f"{upper_bound:,.2f}")

    left, right = st.columns(2)
    with left, card_container("outlier_box"):
        render_section_heading("Box plot", "Quartiles and whiskers; dots outside the whiskers are outliers.")
        fig_box = px.box(df, y=target_col, points="outliers", title=f"Box Plot - {target_col}",
                         color_discrete_sequence=CHART_COLORS)
        st.plotly_chart(style_figure(fig_box, 380), width="stretch")

    with right, card_container("outlier_hist"):
        render_section_heading("Distribution and bounds", "Dashed lines mark the lower and upper bound.")
        fig_hist = px.histogram(df, x=target_col, title=f"Distribution & Bounds - {target_col}",
                                color_discrete_sequence=CHART_COLORS)
        fig_hist.add_vline(x=lower_bound, line_dash="dash", line_color=TOKENS["rose"], annotation_text="Lower Bound")
        fig_hist.add_vline(x=upper_bound, line_dash="dash", line_color=TOKENS["rose"], annotation_text="Upper Bound")
        st.plotly_chart(style_figure(fig_hist, 380), width="stretch")

    shown = min(outlier_count, 100)
    render_section_heading("Outlier Data Records", f"Showing the first {shown:,} of {outlier_count:,} flagged records." if outlier_count else None)
    with card_container("outlier_records"):
        if outlier_count > 0:
            st.dataframe(safe_dataframe(df[outlier_mask].head(100)), width="stretch", height=300)
        else:
            st.success(f"No outliers detected in '{target_col}' using the selected settings.")

    if outlier_count > 0:
        render_html(callout_html("Review the flagged values",
                                 "If they are data-entry problems, Data Preparation can fix missing, infinite or wrongly typed values "
                                 "and records every step in the cleaning history. Real extreme values are left as they are."))
        goto_page_button("Open Data Preparation", "Data Preparation", "outlier_goto_prep")
