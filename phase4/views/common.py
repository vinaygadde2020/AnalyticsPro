"""Helpers shared by every page module.

This module is the single home of AnalyticsPro's shared look and feel ("Precision Intelligence"):

* ``TOKENS``            - the design tokens (colours, radii, shadow, font) as one dictionary.
* ``build_global_css``  - the one application-wide stylesheet, built from ``TOKENS``.
* ``inject_global_css`` - injects that stylesheet; ``app.py`` calls it once per run.
* ``page_header_html`` / ``section_heading_html`` / ``badge_html`` / ``notice_html`` / ``card_html``
  - small, escaped HTML builders (and ``render_*`` wrappers) for consistent headers, badges,
  notifications and cards on any page.

Page modules should use these helpers (or the ``ap-*`` classes they emit) instead of adding their own
colour values, so the palette only ever has to change here.
"""

from __future__ import annotations

from html import escape
from importlib.util import find_spec

import streamlit as st

# Plotly's scatter trendline ("ols") needs statsmodels; only detect it, do not import it.
HAS_STATSMODELS = find_spec("statsmodels") is not None

# --------------------------------------------------------------------------------------
# Design tokens (Stitch "Precision Intelligence")
# --------------------------------------------------------------------------------------
TOKENS: dict[str, str] = {
    # Sidebar
    "sidebar-bg": "#0a1f4d",
    "sidebar-surface": "#0f2a63",  # inputs / uploader / expander inside the sidebar
    "sidebar-border": "#1d3d82",
    "sidebar-hover": "#12306b",
    "sidebar-active": "#4f46e5",
    "sidebar-text": "#cbd5e1",
    "sidebar-text-strong": "#ffffff",
    "sidebar-muted": "#94a3b8",
    "sidebar-focus": "#a5b4fc",
    # Workspace
    "surface": "#f8f9ff",
    "card": "#ffffff",
    "border": "#e2e8f0",
    # Text
    "text": "#0f172a",
    "text-secondary": "#475569",
    "text-muted": "#64748b",
    # Brand and status
    "indigo": "#4f46e5",
    "indigo-hover": "#4338ca",
    "indigo-light": "#eef2ff",
    "teal": "#0d9488",
    "teal-text": "#0f766e",  # teal darkened so small text reaches WCAG AA on the light tint
    "teal-light": "#f0fdfa",
    "amber": "#d97706",
    "amber-text": "#92400e",  # amber darkened for small text on the light tint
    "amber-light": "#fffbeb",
    "rose": "#e11d48",
    "rose-text": "#be123c",  # rose darkened for small text on the light tint
    "rose-light": "#fff1f2",
    # Shape and type
    "radius-card": "12px",
    "radius-control": "8px",
    "radius-pill": "9999px",
    "shadow": "0 1px 3px 0 rgba(0,0,0,.05), 0 1px 2px -1px rgba(0,0,0,.05)",
    "font": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
}

#: badge/notice tone -> (foreground token, background token, border-accent token)
_TONES: dict[str, tuple[str, str, str]] = {
    "neutral": ("text-secondary", "surface", "border"),
    "info": ("indigo", "indigo-light", "indigo"),
    "success": ("teal-text", "teal-light", "teal"),
    "warning": ("amber-text", "amber-light", "amber"),
    "danger": ("rose-text", "rose-light", "rose"),
}


def _tone(tone: str) -> str:
    return tone if tone in _TONES else "neutral"


def render_html(html_code: str) -> None:
    st.markdown(html_code, unsafe_allow_html=True)


# --------------------------------------------------------------------------------------
# Global stylesheet
# --------------------------------------------------------------------------------------
# Selector policy: only documented ``data-testid`` hooks, ``data-baseweb`` attributes, ARIA roles and
# the ``st-key-*`` classes Streamlit derives from widget keys. No positional/emotion-generated classes.
# Everything reads the ``--ap-*`` custom properties declared in ``:root`` (generated from TOKENS).
_GLOBAL_CSS = """
/* ---------- Page chrome ---------- */
/* The header hosts the sidebar open/close toggle, so it stays in the DOM: transparent and click-through.
   Only the toolbar actions, main menu, deploy button and decoration are hidden. */
header[data-testid="stHeader"] { background: transparent !important; pointer-events: none !important; }
[data-testid="stDecoration"], [data-testid="stToolbarActions"], [data-testid="stMainMenu"],
[data-testid="stAppDeployButton"] { display: none !important; }
[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapsedControl"] {
    pointer-events: auto !important; background: var(--ap-sidebar-bg) !important; border-radius: var(--ap-radius-control) !important;
}
[data-testid="stExpandSidebarButton"] *, [data-testid="stSidebarCollapsedControl"] * { color: var(--ap-sidebar-text-strong) !important; }
/* While the sidebar is collapsed the toggle floats top-left: keep the page header clear of it. */
[data-testid="stAppViewContainer"]:has([data-testid="stSidebar"]:is([aria-expanded="false"], [data-collapsed="true"])) .ap-topbar { padding-left: 3.25rem !important; }

/* ---------- Workspace ---------- */
.stApp, [data-testid="stApp"] { font-family: var(--ap-font); color: var(--ap-text); }
/* !important so a page that injects its own canvas colour (Interactive Dashboard) stays on the shared one. */
[data-testid="stAppViewContainer"] { background: var(--ap-surface) !important; }
.block-container {
    padding: .5rem 1.5rem 3rem !important;
    max-width: 1720px !important;
}
[data-testid="stMain"] :is(h1, h2, h3, h4), [data-testid="stMarkdownContainer"] :is(h1, h2, h3, h4) {
    font-family: var(--ap-font); color: var(--ap-text); letter-spacing: -.01em;
}
[data-testid="stMain"] h1 { font-size: 28px; line-height: 1.2; font-weight: 700; }
[data-testid="stMain"] h2 { font-size: 20px; line-height: 1.3; font-weight: 600; }
[data-testid="stMain"] h3 { font-size: 16px; line-height: 1.4; font-weight: 600; }
[data-testid="stMain"] :is(p, li, label) { font-size: 14px; line-height: 1.5; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * { color: var(--ap-text-muted); font-size: 12px; line-height: 1.4; }

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] { background: var(--ap-sidebar-bg); border-right: 1px solid var(--ap-sidebar-hover); font-family: var(--ap-font); }
@media (min-width: 769px) {
    [data-testid="stSidebar"][aria-expanded="true"] { min-width: 248px !important; max-width: 248px !important; }
}
[data-testid="stSidebarHeader"] { height: 34px !important; min-height: 34px !important; padding: 0 !important; margin: 0 !important; }
[data-testid="stSidebarHeader"] button { margin-top: 2px !important; }
[data-testid="stSidebar"] > div:first-child { padding: 0 .75rem !important; }
[data-testid="stSidebarHeader"] + div { margin-top: -2px !important; }
/* Default sidebar text; more specific rules below win for buttons and brand. */
[data-testid="stSidebar"] * { color: var(--ap-sidebar-text) !important; }
[data-testid="stSidebar"] hr { margin: 10px 0 !important; border-color: var(--ap-sidebar-border) !important; }
[data-testid="stSidebar"] code { background: var(--ap-sidebar-surface) !important; color: var(--ap-sidebar-text-strong) !important; }
[data-testid="stSidebar"] strong { color: var(--ap-sidebar-text-strong) !important; }

/* Brand block */
.ap-brand-block { display: flex; align-items: center; gap: 10px; padding: 4px 4px 2px; }
.ap-brand-mark {
    width: 32px; height: 32px; flex: 0 0 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center;
    background: var(--ap-indigo); font-weight: 800; font-size: 17px; line-height: 1;
}
[data-testid="stSidebar"] .ap-brand-mark { color: #ffffff !important; }
.ap-brand { font-size: 19px; font-weight: 700; letter-spacing: -.02em; line-height: 1.15; }
[data-testid="stSidebar"] .ap-brand { color: var(--ap-sidebar-text-strong) !important; }
.ap-sub { font-size: 11px; line-height: 1.3; font-weight: 500; margin-top: 2px; }
[data-testid="stSidebar"] .ap-sub { color: var(--ap-sidebar-muted) !important; }
.ap-nav-label { font-size: 11px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; padding: 14px 6px 6px; }
[data-testid="stSidebar"] .ap-nav-label { color: var(--ap-sidebar-muted) !important; }

/* Navigation buttons (one st.button per page) */
[data-testid="stSidebar"] .stButton { margin: 0 !important; padding: 0 !important; }
[data-testid="stSidebar"] .stButton > button {
    justify-content: flex-start !important; text-align: left !important; min-height: 38px !important; height: 38px !important;
    padding: 0 12px !important; margin: 1px 0 !important; border: 1px solid transparent !important; background: transparent !important;
    color: var(--ap-sidebar-text) !important; font-size: 13px !important; font-weight: 500 !important;
    border-radius: var(--ap-radius-control) !important; white-space: nowrap !important; overflow: hidden !important;
    text-overflow: ellipsis !important; box-shadow: none !important; transition: background-color .15s ease, color .15s ease;
}
[data-testid="stSidebar"] .stButton > button * { color: inherit !important; font-size: inherit !important; font-weight: inherit !important; }
[data-testid="stSidebar"] .stButton > button:hover { background: var(--ap-sidebar-hover) !important; color: var(--ap-sidebar-text-strong) !important; }
/* The page you are on: solid indigo with white text. */
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"],
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"]:hover {
    background: var(--ap-sidebar-active) !important; border-color: var(--ap-sidebar-active) !important;
    color: var(--ap-sidebar-text-strong) !important; font-weight: 600 !important; box-shadow: 0 1px 3px rgba(0,0,0,.25) !important;
}
/* "Reload original dataset": an outlined utility button, visually distinct from navigation. */
[data-testid="stSidebar"] [class*="st-key-reset_dataset_btn"] .stButton > button,
[data-testid="stSidebar"] [class*="st-key-reset_dataset_btn"] button {
    border-color: var(--ap-sidebar-border) !important; margin-top: 6px !important; justify-content: center !important;
}
/* The button has a help tooltip, which wraps it in extra spans, so the direct-child rule above does not match it:
   restate the navigation-button look here (otherwise it falls back to a light background with light text). */
[data-testid="stSidebar"] [class*="st-key-reset_dataset_btn"] button {
    background: transparent !important; color: var(--ap-sidebar-text) !important; border: 1px solid var(--ap-sidebar-border) !important;
    border-radius: var(--ap-radius-control) !important; font-size: 13px !important; font-weight: 500 !important; box-shadow: none !important;
}
[data-testid="stSidebar"] [class*="st-key-reset_dataset_btn"] button:hover { background: var(--ap-sidebar-hover) !important; color: var(--ap-sidebar-text-strong) !important; }
[data-testid="stSidebar"] [class*="st-key-reset_dataset_btn"] button:hover { border-color: var(--ap-sidebar-muted) !important; }

/* Sidebar form controls sit on the dark sidebar surface. */
[data-testid="stSidebar"] [data-testid="stFileChip"] { background: var(--ap-sidebar-border) !important; }
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"],
[data-testid="stSidebar"] [data-testid="stFileUploaderFile"] {
    background: var(--ap-sidebar-surface) !important; border: 1px dashed #3b5aa0 !important; border-radius: var(--ap-radius-control) !important;
}
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button {
    background: var(--ap-sidebar-border) !important; border: 1px solid #5b7bc0 !important; color: var(--ap-sidebar-text-strong) !important;
}
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] small { color: var(--ap-sidebar-text) !important; }
[data-testid="stSidebar"] [data-testid="stExpander"] {
    background: var(--ap-sidebar-surface) !important; border: 1px solid var(--ap-sidebar-border) !important; border-radius: var(--ap-radius-control) !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] > div, [data-testid="stSidebar"] [data-baseweb="input"] {
    background: var(--ap-sidebar-bg) !important; border-color: var(--ap-sidebar-border) !important;
}
/* Indigo on navy is too faint for a focus ring; use the light indigo inside the sidebar. */
[data-testid="stSidebar"] :is(button, [role="button"], a, input, textarea):focus-visible,
[data-testid="stSidebar"] [data-baseweb="select"]:focus-within { outline: 3px solid var(--ap-sidebar-focus) !important; outline-offset: 2px !important; }

/* ---------- Page header ---------- */
.ap-topbar {
    display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; flex-wrap: wrap;
    background: var(--ap-card); border: 1px solid var(--ap-border); border-radius: var(--ap-radius-card);
    padding: 14px 20px; margin: 0 0 16px; box-shadow: var(--ap-shadow);
}
.ap-eyebrow { font-size: 11px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--ap-text-muted); }
.ap-eyebrow strong { color: var(--ap-indigo); font-weight: 600; }
.ap-topbar .ap-page-title {
    margin: 2px 0 0 !important; padding: 0 !important; font-size: 24px !important; line-height: 1.25 !important;
    font-weight: 700 !important; color: var(--ap-text) !important;
}
.ap-page-subtitle { margin: 4px 0 0; font-size: 14px; line-height: 1.5; color: var(--ap-text-secondary); max-width: 60rem; }
.ap-topbar-aside { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

/* ---------- Section headings, cards, insights ---------- */
.ap-section-title { color: var(--ap-text); font-size: 16px; font-weight: 600; line-height: 1.4; margin: 4px 0 2px; }
.ap-section-caption { color: var(--ap-text-secondary); font-size: 13px; line-height: 1.4; margin: 0 0 10px; }
.ap-small { color: var(--ap-text-muted); font-size: 12px; line-height: 1.4; }
.ap-card { background: var(--ap-card); border: 1px solid var(--ap-border); border-radius: var(--ap-radius-card); padding: 16px; margin: 8px 0; box-shadow: var(--ap-shadow); }
.ap-card-title { margin: 0 0 6px; font-size: 14px; font-weight: 600; color: var(--ap-text); }
.ap-insight {
    background: var(--ap-card); border: 1px solid var(--ap-border); border-left: 3px solid var(--ap-indigo);
    border-radius: var(--ap-radius-control); padding: 12px 14px; margin: 6px 0; color: var(--ap-text-secondary); font-size: 13px; line-height: 1.5;
}

/* ---------- Badges and notices ---------- */
.ap-badge {
    display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: var(--ap-radius-pill);
    font-size: 12px; font-weight: 600; line-height: 1.5; white-space: nowrap; border: 1px solid transparent;
}
.ap-notice { border-radius: var(--ap-radius-control); border: 1px solid var(--ap-border); border-left-width: 4px; padding: 10px 14px; margin: 8px 0; font-size: 13px; line-height: 1.5; }
.ap-notice-title { font-weight: 600; margin-bottom: 2px; }
%TONE_CSS%

/* ---------- Native Streamlit components ---------- */
[data-testid="stMain"] [data-testid="stMetric"] {
    background: var(--ap-card); border: 1px solid var(--ap-border); border-radius: var(--ap-radius-card); padding: 14px 16px; box-shadow: var(--ap-shadow);
}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * { color: var(--ap-text-secondary); font-size: 13px; }
[data-testid="stMetricValue"] { color: var(--ap-text); font-weight: 700; font-variant-numeric: tabular-nums; font-size: clamp(1.4rem, 2.2vw, 2rem); }
[data-testid="stAlert"] { border-radius: var(--ap-radius-control); }
[data-testid="stMain"] [data-testid="stExpander"] { background: var(--ap-card); border: 1px solid var(--ap-border); border-radius: var(--ap-radius-card); }
[data-testid="stDataFrame"], [data-testid="stTable"] { border: 1px solid var(--ap-border); border-radius: var(--ap-radius-control); overflow: hidden; }
[data-testid="stPlotlyChart"] { max-width: 100%; }
[data-testid="stMain"] [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--ap-border); overflow-x: auto; }
[data-testid="stMain"] [data-baseweb="tab"] { color: var(--ap-text-secondary); font-weight: 500; }
[data-testid="stMain"] [data-baseweb="tab"][aria-selected="true"] { color: var(--ap-indigo); font-weight: 600; }
[data-testid="stMain"] [data-baseweb="tab-highlight"] { background-color: var(--ap-indigo) !important; }

/* Buttons (main area; the sidebar has its own rules above) */
[data-testid="stMain"] [data-testid="stBaseButton-primary"], [data-testid="stMain"] [data-testid="stBaseButton-primaryFormSubmit"] {
    background: var(--ap-indigo); border: 1px solid var(--ap-indigo); color: #ffffff; border-radius: var(--ap-radius-control); font-weight: 600;
}
[data-testid="stMain"] [data-testid="stBaseButton-primary"]:hover, [data-testid="stMain"] [data-testid="stBaseButton-primaryFormSubmit"]:hover {
    background: var(--ap-indigo-hover); border-color: var(--ap-indigo-hover); color: #ffffff;
}
[data-testid="stMain"] :is([data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"], [data-testid="stBaseButton-tertiary"]) {
    background: var(--ap-card); border: 1px solid var(--ap-border); color: var(--ap-text); border-radius: var(--ap-radius-control); font-weight: 500; box-shadow: var(--ap-shadow);
}
[data-testid="stMain"] :is([data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"]):hover {
    background: var(--ap-indigo-light); border-color: var(--ap-indigo); color: var(--ap-indigo);
}
[data-testid="stMain"] [data-testid="stBaseButton-primary"] *, [data-testid="stMain"] [data-testid="stBaseButton-primaryFormSubmit"] * { color: #ffffff; }

/* Inputs */
[data-testid="stMain"] [data-baseweb="input"], [data-testid="stMain"] [data-baseweb="select"] > div, [data-testid="stMain"] [data-baseweb="textarea"] {
    border-radius: var(--ap-radius-control); border-color: var(--ap-border); background-color: var(--ap-card);
}
[data-testid="stMain"] [data-baseweb="input"]:focus-within, [data-testid="stMain"] [data-baseweb="textarea"]:focus-within { border-color: var(--ap-indigo); }
[data-testid="stMain"] label, [data-testid="stWidgetLabel"] { color: var(--ap-text-secondary); font-weight: 500; }

/* Keyboard users: a clearly visible focus ring on every interactive control. */
button:focus-visible, [role="button"]:focus-visible, [role="tab"]:focus-visible, a:focus-visible,
input:focus-visible, textarea:focus-visible, [data-baseweb="select"]:focus-within { outline: 3px solid var(--ap-indigo) !important; outline-offset: 2px !important; }

/* ---------- Stage 2 building blocks ---------- */
.ap-page-intro { margin: -4px 0 14px; font-size: 14px; line-height: 1.5; color: var(--ap-text-secondary); max-width: 62rem; }
/* st.container(border=True, key="apcard_*") -> a white card with the shared border, radius and shadow. */
[class*="st-key-apcard_"] {
    background: var(--ap-card); border: 1px solid var(--ap-border) !important; border-radius: var(--ap-radius-card) !important;
    box-shadow: var(--ap-shadow); padding: 6px 10px;
}
.ap-hero {
    text-align: center; padding: 36px 20px; margin: 4px 0 18px; background: var(--ap-indigo-light);
    border: 1px dashed #a5b4fc; border-radius: var(--ap-radius-card);
}
.ap-hero-icon { width: 56px; height: 56px; margin: 0 auto 10px; border-radius: 50%; background: var(--ap-card); display: flex; align-items: center; justify-content: center; font-size: 26px; box-shadow: var(--ap-shadow); }
.ap-hero-title { margin: 0 0 4px; font-size: 20px; font-weight: 600; color: var(--ap-text); }
.ap-hero-body { margin: 0 auto 12px; max-width: 38rem; font-size: 14px; line-height: 1.5; color: var(--ap-text-secondary); }
.ap-hero-badges { display: flex; gap: 6px; justify-content: center; flex-wrap: wrap; }
.ap-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 12px; margin: 6px 0 14px; }
.ap-grid .ap-insight { margin: 0; }
.ap-kv { margin: 0; padding: 0; }
.ap-kv-row { display: flex; justify-content: space-between; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--ap-border); font-size: 13px; }
.ap-kv-row:last-child { border-bottom: none; }
.ap-kv-key { color: var(--ap-text-secondary); }
.ap-kv-value { color: var(--ap-text); font-weight: 600; text-align: right; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
.ap-meter { margin: 8px 0; }
.ap-meter-head { display: flex; justify-content: space-between; gap: 8px; font-size: 13px; color: var(--ap-text); margin-bottom: 4px; }
.ap-meter-head span:last-child { color: var(--ap-text-secondary); font-variant-numeric: tabular-nums; white-space: nowrap; }
.ap-track { height: 8px; background: var(--ap-border); border-radius: var(--ap-radius-pill); overflow: hidden; }
.ap-fill { height: 100%; border-radius: var(--ap-radius-pill); background: var(--ap-indigo); }
.ap-fill-success { background: var(--ap-teal); } .ap-fill-warning { background: var(--ap-amber); } .ap-fill-danger { background: var(--ap-rose); }
.ap-stack { display: flex; height: 10px; border-radius: var(--ap-radius-pill); overflow: hidden; background: var(--ap-border); margin: 4px 0 6px; }
.ap-stack > span { display: block; height: 100%; }
.ap-legend { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 12px; color: var(--ap-text-secondary); }
.ap-legend i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; }
.ap-share-title { display: flex; justify-content: space-between; gap: 8px; font-size: 13px; font-weight: 600; color: var(--ap-text); margin-top: 10px; }
.ap-share-title span { font-weight: 400; color: var(--ap-text-secondary); }
.ap-history { display: flex; gap: 12px; align-items: baseline; }
.ap-history time { flex: 0 0 auto; font-variant-numeric: tabular-nums; font-weight: 600; color: var(--ap-text); font-size: 12px; }
.ap-callout {
    display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; padding: 14px 18px; margin: 14px 0 4px;
    background: var(--ap-indigo-light); border: 1px solid #c7d2fe; border-radius: var(--ap-radius-card);
}
.ap-callout-title { font-size: 15px; font-weight: 600; color: var(--ap-text); }
.ap-callout-body { font-size: 13px; color: var(--ap-text-secondary); margin-top: 2px; }

/* ---------- Footer ---------- */
.ap-footer {
    width: 100%; margin-top: 35px; padding: 14px 10px; text-align: center; border-top: 1px solid var(--ap-border);
    color: var(--ap-text-muted); font-size: 12px; background: transparent;
}
.ap-footer strong { color: var(--ap-indigo); }

/* ---------- Responsive ---------- */
@media (max-width: 768px) {
    .block-container { padding: .5rem .75rem 2.5rem !important; }
    .ap-topbar { padding: 12px 14px; }
    .ap-topbar .ap-page-title { font-size: 20px !important; }
    [data-testid="stMain"] h1 { font-size: 24px; }
}
/* Touch devices: 44px minimum hit area for buttons, tabs and sidebar navigation. */
@media (pointer: coarse) {
    [data-testid="stMain"] button, [data-testid="stSidebar"] .stButton > button { min-height: 44px !important; }
    [data-testid="stSidebar"] .stButton > button { height: 44px !important; }
    [data-testid="stMain"] [data-baseweb="tab"] { min-height: 44px; }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
"""


def _root_block() -> str:
    return ":root {\n" + "\n".join(f"    --ap-{name}: {value};" for name, value in TOKENS.items()) + "\n}"


def _tone_css() -> str:
    rules = []
    for name, (fg, bg, accent) in _TONES.items():
        rules.append(
            f".ap-badge-{name} {{ color: var(--ap-{fg}); background: var(--ap-{bg}); border-color: var(--ap-{accent}); }}\n"
            f".ap-notice-{name} {{ color: var(--ap-{fg}); background: var(--ap-{bg}); border-left-color: var(--ap-{accent}); }}"
        )
    return "\n".join(rules)


def build_global_css() -> str:
    """The complete shared stylesheet (``<style>`` block), generated from ``TOKENS``."""
    return f"<style>\n{_root_block()}\n{_GLOBAL_CSS.replace('%TONE_CSS%', _tone_css())}\n</style>"


def inject_global_css() -> None:
    """Inject the shared stylesheet. Call once, at the top of every script run."""
    render_html(build_global_css())


# --------------------------------------------------------------------------------------
# Reusable HTML builders. Every text argument is escaped; only ``*_html`` arguments are trusted markup.
# --------------------------------------------------------------------------------------
def badge_html(text: str, tone: str = "neutral", *, dot: bool = False) -> str:
    """A pill badge. ``tone`` is one of neutral, info, success, warning, danger."""
    marker = '<span aria-hidden="true">●</span>' if dot else ""
    return f'<span class="ap-badge ap-badge-{_tone(tone)}">{marker}{escape(text)}</span>'


def notice_html(message: str, tone: str = "info", *, title: str | None = None) -> str:
    """A static notification box (use st.info/st.warning for transient widget feedback)."""
    heading = f'<div class="ap-notice-title">{escape(title)}</div>' if title else ""
    return f'<div class="ap-notice ap-notice-{_tone(tone)}" role="note">{heading}{escape(message)}</div>'


def section_heading_html(title: str, caption: str | None = None) -> str:
    """A section heading with an optional one-line caption."""
    cap = f'<div class="ap-section-caption">{escape(caption)}</div>' if caption else ""
    return f'<div class="ap-section-title">{escape(title)}</div>{cap}'


def card_html(body_html: str, *, title: str | None = None) -> str:
    """A bordered white card. ``body_html`` is trusted markup: escape any user text before passing it in."""
    heading = f'<div class="ap-card-title">{escape(title)}</div>' if title else ""
    return f'<div class="ap-card">{heading}{body_html}</div>'


def page_header_html(title: str, subtitle: str | None = None, *, eyebrow: str = "Workspace", badges_html: str = "") -> str:
    """The shared page header: breadcrumb, H1 title, optional subtitle and right-hand badges (trusted markup)."""
    sub = f'<p class="ap-page-subtitle">{escape(subtitle)}</p>' if subtitle else ""
    aside = f'<div class="ap-topbar-aside">{badges_html}</div>' if badges_html else ""
    return (
        '<div class="ap-topbar"><div>'
        f'<div class="ap-eyebrow">{escape(eyebrow)} &rsaquo; <strong>{escape(title)}</strong></div>'
        f'<h1 class="ap-page-title">{escape(title)}</h1>{sub}</div>{aside}</div>'
    )


def sidebar_brand_html() -> str:
    """Sidebar logo mark, product name, tagline and the navigation group label."""
    return (
        '<div class="ap-brand-block"><div class="ap-brand-mark" aria-hidden="true">A</div>'
        '<div><div class="ap-brand">AnalyticsPro</div><div class="ap-sub">Turn raw data into smart decisions</div></div></div>'
        '<div class="ap-nav-label">Analytics modules</div>'
    )


def footer_html() -> str:
    return '<div class="ap-footer">AnalyticsPro &nbsp;&bull;&nbsp; <strong>Data Exploration &amp; Analytics</strong></div>'


def render_page_header(title: str, subtitle: str | None = None, *, eyebrow: str = "Workspace", badges_html: str = "") -> None:
    render_html(page_header_html(title, subtitle, eyebrow=eyebrow, badges_html=badges_html))


def render_section_heading(title: str, caption: str | None = None) -> None:
    render_html(section_heading_html(title, caption))


# --------------------------------------------------------------------------------------
# Stage 2 helpers: building blocks used by several core screens
# --------------------------------------------------------------------------------------
#: Qualitative palette for charts and share bars (indigo, teal, amber, rose, then softer tints and slate).
CHART_COLORS: list[str] = ["#4f46e5", "#0d9488", "#d97706", "#e11d48", "#818cf8", "#2dd4bf", "#fbbf24", "#64748b"]


def page_intro_html(text: str) -> str:
    """One-paragraph description under the page header (the header itself already shows the page title)."""
    return f'<p class="ap-page-intro">{escape(text)}</p>'


def render_page_intro(text: str) -> None:
    render_html(page_intro_html(text))


def card_container(key: str):
    """A bordered Streamlit container styled as a card. ``key`` must be unique on the page."""
    return st.container(border=True, key=f"apcard_{key}")


def hero_html(icon: str, title: str, body: str, badges: list[str] | None = None) -> str:
    """Large centred call-to-action panel (empty states). Badge texts are escaped."""
    chips = "".join(badge_html(b, "info") for b in badges or [])
    chip_row = f'<div class="ap-hero-badges">{chips}</div>' if chips else ""
    return (
        f'<div class="ap-hero"><div class="ap-hero-icon" aria-hidden="true">{escape(icon)}</div>'
        f'<h2 class="ap-hero-title">{escape(title)}</h2><p class="ap-hero-body">{escape(body)}</p>{chip_row}</div>'
    )


def kv_rows_html(pairs: list[tuple[str, str]]) -> str:
    """Label/value rows (e.g. the active import settings). All text is escaped."""
    rows = "".join(
        f'<div class="ap-kv-row"><span class="ap-kv-key">{escape(str(k))}</span><span class="ap-kv-value">{escape(str(v))}</span></div>'
        for k, v in pairs
    )
    return f'<div class="ap-kv">{rows}</div>'


def progress_html(percent: float, label: str, detail: str = "", tone: str = "info") -> str:
    """A labelled progress meter. The number is printed as text too, so colour is never the only signal."""
    pct = max(0.0, min(100.0, float(percent) if percent == percent else 0.0))  # NaN -> 0
    fill = {"success": " ap-fill-success", "warning": " ap-fill-warning", "danger": " ap-fill-danger"}.get(tone, "")
    return (
        f'<div class="ap-meter"><div class="ap-meter-head"><span>{escape(label)}</span><span>{escape(detail)}</span></div>'
        f'<div class="ap-track" role="progressbar" aria-label="{escape(label, quote=True)}" aria-valuemin="0" aria-valuemax="100" '
        f'aria-valuenow="{pct:.0f}"><div class="ap-fill{fill}" style="width:{pct:.1f}%"></div></div></div>'
    )


def share_bar_html(title: str, subtitle: str, segments: list[tuple[str, float]]) -> str:
    """Stacked share bar plus a text legend ("label: value (share%)"). ``segments`` are (label, non-negative count)."""
    total = float(sum(v for _, v in segments if v > 0))
    if total <= 0:
        return f'<div class="ap-share-title">{escape(title)}<span>{escape(subtitle)}</span></div>'
    bars, legend = [], []
    for i, (label, value) in enumerate(segments):
        if value <= 0:
            continue
        colour = CHART_COLORS[i % len(CHART_COLORS)]
        share = value / total * 100
        bars.append(f'<span style="width:{share:.2f}%;background:{colour}"></span>')
        legend.append(f'<span><i style="background:{colour}"></i>{escape(str(label))}: {value:,.0f} ({share:.0f}%)</span>')
    return (
        f'<div class="ap-share-title">{escape(title)}<span>{escape(subtitle)}</span></div>'
        f'<div class="ap-stack" aria-hidden="true">{"".join(bars)}</div><div class="ap-legend">{"".join(legend)}</div>'
    )


def insight_grid_html(items_html: list[str]) -> str:
    """Responsive grid of already-built insight cards (trusted markup)."""
    return f'<div class="ap-grid">{"".join(items_html)}</div>'


def insight_html(inner_html: str, icon: str = "💡") -> str:
    """One insight card. ``inner_html`` is trusted: escape user text before passing it in."""
    return f'<div class="ap-insight"><span aria-hidden="true">{escape(icon)}</span> {inner_html}</div>'


def callout_html(title: str, body: str) -> str:
    """Text block for a 'suggested next step' strip; put the real buttons beneath it."""
    return f'<div class="ap-callout"><div><div class="ap-callout-title">{escape(title)}</div><div class="ap-callout-body">{escape(body)}</div></div></div>'


def goto_page_button(label: str, route: str, key: str, *, primary: bool = False) -> None:
    """A real navigation button: switches ``current_page`` (the same state the sidebar uses) and reruns."""
    if st.button(label, key=key, type="primary" if primary else "secondary", width="stretch"):
        st.session_state["current_page"] = route
        st.rerun()


def style_figure(fig, height: int | None = None):
    """Apply the shared chart look (fonts, palette, grid, margins) to a Plotly figure and return it."""
    fig.update_layout(
        font=dict(family=TOKENS["font"], size=12, color=TOKENS["text-secondary"]),
        title=dict(font=dict(size=14, color=TOKENS["text"])),
        colorway=CHART_COLORS, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=8, r=8, t=44, b=8), legend=dict(orientation="h", y=-0.2),
    )
    fig.update_xaxes(gridcolor=TOKENS["border"], linecolor=TOKENS["border"], automargin=True)
    fig.update_yaxes(gridcolor=TOKENS["border"], linecolor=TOKENS["border"], automargin=True)
    if height:
        fig.update_layout(height=height)
    return fig
