"""Ask Your Data page: rule-based, data-grounded questions (no AI service is called)."""

from __future__ import annotations

import logging
import re

import pandas as pd
import plotly.express as px
import streamlit as st

from data.analyst import (
    SUPPORTED_OPERATIONS,
    Answer,
    answer_question,
    automatic_insights,
    suggest_prompts,
)
from data.columns import classify_columns
from data.intent import build_chart_data
from data.report import insight_to_html
from utils.dataframe_utils import safe_dataframe
from views.common import (
    CHART_COLORS,
    HAS_STATSMODELS,
    badge_html,
    card_container,
    insight_grid_html,
    insight_html,
    notice_html,
    render_html,
    render_page_intro,
    render_section_heading,
    style_figure,
)

logger = logging.getLogger("analyticspro.analyst")

_INDIGO_SCALE = [[0.0, "#c7d2fe"], [1.0, CHART_COLORS[0]]]
_OPERATION_LABELS = {key: description for key, description, _ in SUPPORTED_OPERATIONS}
MAX_ROLE_BADGES = 24


def render_chart_from_intent(df: pd.DataFrame, intent: dict) -> None:
    """Draw the chart a parsed chart request describes (see data/intent.py)."""
    try:
        chart_type = intent["chart_type"]
        if chart_type == "Histogram":
            fig = px.histogram(df, x=intent["x"], title=intent["title"], marginal="box")
            st.plotly_chart(style_figure(fig), width="stretch")

            s = pd.to_numeric(df[intent["x"]], errors="coerce").dropna()
            if not s.empty:
                st.markdown(
                    f"💡 **Summary:** `{intent['x']}` has a mean of **{s.mean():,.2f}**, "
                    f"median of **{s.median():,.2f}**, min of **{s.min():,.2f}**, and max of **{s.max():,.2f}**."
                )

        elif chart_type == "Bar Chart":
            data, value_col = build_chart_data(df, intent)
            fig = px.bar(
                data, x=intent["x"], y=value_col, title=intent["title"],
                color=value_col, color_continuous_scale=_INDIGO_SCALE,
            )
            st.plotly_chart(style_figure(fig), width="stretch")
            if not data.empty:
                top_row = data.iloc[0]
                st.markdown(
                    f"💡 **Key Finding:** Top record for `{intent['x']}` is **{top_row[intent['x']]}** "
                    f"with a {intent.get('agg', 'sum')} `{intent['y']}` of **{top_row[value_col]:,.2f}**."
                )

        elif chart_type == "Line Chart":
            data, value_col = build_chart_data(df, intent)
            fig = px.line(data, x=intent["x"], y=value_col, title=intent["title"], markers=True)
            st.plotly_chart(style_figure(fig), width="stretch")

        elif chart_type == "Scatter Plot":
            fig = px.scatter(
                df, x=intent["x"], y=intent["y"], title=intent["title"],
                trendline="ols" if HAS_STATSMODELS else None,
            )
            st.plotly_chart(style_figure(fig), width="stretch")

    except (ValueError, TypeError, KeyError) as exc:
        logger.warning("Could not render chart for prompt (%s)", type(exc).__name__)
        st.warning("I couldn't draw a chart for that request with these columns. Try naming other columns.")


def _render_answer(df: pd.DataFrame, answer: Answer) -> None:
    """Show one computed ``Answer`` (see data/analyst.py)."""
    show = {"success": st.success, "info": st.info, "warning": st.warning}[answer.level]
    show(answer.message)
    if answer.table is not None:
        st.dataframe(safe_dataframe(answer.table), width="stretch", hide_index=answer.handler != "correlation")
        if answer.bar_from_table and len(answer.table.columns) >= 2:
            st.bar_chart(answer.table.set_index(answer.table.columns[0]))
    if answer.chart_intent:
        render_chart_from_intent(df, answer.chart_intent)


def _markup(finding: str) -> str:
    """Escape an insight, then turn **bold** into <b> and `column` into <code> (the text is escaped first)."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", insight_to_html(finding))


def _render_summary_and_insights(df: pd.DataFrame) -> None:
    render_section_heading("Dataset at a glance", "Computed from the active dataset every time the page loads.")
    total_cells = int(df.shape[0] * df.shape[1])
    missing_cells = int(df.isna().sum().sum())
    quality_cols = st.columns(4)
    quality_cols[0].metric("Rows", f"{len(df):,}")
    quality_cols[1].metric("Columns", f"{len(df.columns):,}")
    quality_cols[2].metric(
        "Missing cells", f"{missing_cells:,}",
        delta=(f"{(missing_cells / total_cells * 100):.1f}% of cells" if total_cells else "0%"),
        delta_color="off",
    )
    quality_cols[3].metric("Duplicate rows", f"{int(df.duplicated().sum()):,}")

    render_section_heading("✨ Automatic, data-grounded insights", "Findings from fixed rules, not from a language model.")
    findings = automatic_insights(df)
    if findings:
        render_html(insight_grid_html([insight_html(_markup(f), "•") for f in findings]))
    else:
        st.info("No automatic insights could be generated for this dataset.")
    st.caption("Insights are computed locally from the active dataset. They are descriptive findings, not causal conclusions.")


def _render_question_area(df: pd.DataFrame) -> str:
    """Question box with suggested prompts. Returns the current question text.

    The input is created *after* the prompt buttons (in script order) because a button writes the input's value; the
    ``slot`` container only places the input above the buttons on screen.
    """
    render_section_heading("Ask a question", "Type a plain-English question, or pick a suggested prompt built from your own columns.")
    with card_container("ask_input"):
        slot = st.container()
        suggestions = suggest_prompts(df)
        if suggestions:
            st.caption("Suggested prompts (click to fill the question box)")
            per_row = 2
            for start in range(0, len(suggestions), per_row):
                row = suggestions[start:start + per_row]
                for offset, (col, text) in enumerate(zip(st.columns(len(row)), row)):
                    if col.button(text, key=f"sug_btn_{start + offset}", width="stretch"):
                        st.session_state["ai_query_input"] = text
        with slot:
            return st.text_input(
                "Ask a question in plain English:",
                placeholder="e.g. Show top 5 categories by total sales",
                key="ai_query_input",
            )


def _render_result(df: pd.DataFrame, user_query: str) -> None:
    render_section_heading("Answer")
    if not user_query:
        render_html(notice_html("Your answer, with a table or chart where the question calls for one, will appear here.", "info"))
        return
    answer = answer_question(user_query, df)
    matched = _OPERATION_LABELS.get(answer.handler)
    with card_container("ask_answer"):
        render_html(f'<div class="ap-eyebrow">Your question</div><div class="ap-section-title">{_markup(user_query)}</div>'
                    + (badge_html(f"Matched rule: {matched}", "success") if matched else ""))
        _render_answer(df, answer)


def _render_guide(df: pd.DataFrame) -> None:
    render_section_heading("What can I ask?", "Each kind of question the rules understand.")
    with card_container("ask_guide"):
        for _, description, example in SUPPORTED_OPERATIONS:
            st.markdown(f"- **{description}** — e.g. _{example}_")
        st.caption("Identifier columns (IDs, codes) are not used as metrics unless you name them in the question.")
    roles = classify_columns(df)
    render_section_heading("Column roles", "How each column is treated when answering.")
    with card_container("ask_roles"):
        shown = list(roles.items())[:MAX_ROLE_BADGES]
        render_html('<div class="ap-topbar-aside">' + "".join(
            badge_html(f"{col} · {role}", "warning" if role == "identifier" else "neutral") for col, role in shown) + "</div>")
        if len(roles) > len(shown):
            st.caption(f"Showing {len(shown)} of {len(roles)} columns.")


def render_ask_your_data_page(df: pd.DataFrame) -> None:
    render_page_intro("Ask plain-English questions about your active dataset and get computed answers, tables and charts.")
    with card_container("ask_trust"):
        st.caption(
            "Plain-English questions answered by fixed rules over your active dataset. "
            "This is not an AI model: nothing is sent anywhere and no API key is used."
        )

    if df is None or df.empty:
        st.info("Upload a dataset first.")
        return

    main, side = st.columns([2.2, 1])
    with main:
        _render_summary_and_insights(df)
        user_query = _render_question_area(df)
        _render_result(df, user_query)
    with side:
        _render_guide(df)
