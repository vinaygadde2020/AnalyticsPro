"""Shared UI foundation (views/common.py): tokens, global stylesheet and HTML builders."""

import re

import pytest

from views import common
from views.common import (
    TOKENS,
    badge_html,
    build_global_css,
    card_html,
    footer_html,
    notice_html,
    page_header_html,
    section_heading_html,
    sidebar_brand_html,
)

EVIL = "<script>alert(1)</script>"


def _luminance(hex_colour: str) -> float:
    rgb = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_stylesheet_is_complete_and_balanced():
    css = build_global_css()
    assert css.startswith("<style>") and css.endswith("</style>")
    assert "%TONE_CSS%" not in css
    assert css.count("{") == css.count("}")
    for name in TOKENS:
        assert f"--ap-{name}:" in css


def test_every_var_reference_is_a_defined_token():
    css = build_global_css()
    for name in set(re.findall(r"var\(--ap-([a-z-]+)\)", css)):
        assert name in TOKENS, name


def test_stylesheet_loads_nothing_from_the_network():
    assert "http://" not in build_global_css() and "https://" not in build_global_css() and "@import" not in build_global_css()


def test_stylesheet_keeps_streamlit_controls_available():
    """Only chrome that is not needed for operation may be display:none; the sidebar toggle must stay reachable."""
    css = build_global_css()
    hidden_selectors = re.findall(r"([^{}]+)\{[^{}]*display: none !important", css)
    hidden = " ".join(hidden_selectors)
    for needed in ("stHeader", "stToolbar\"", "stSidebar", "stExpandSidebarButton", "stSidebarCollapseButton"):
        assert needed not in hidden, needed
    assert "stExpandSidebarButton" in css and "pointer-events: auto" in css


@pytest.mark.parametrize("fg,bg", [
    ("text", "surface"), ("text", "card"), ("text-secondary", "card"), ("text-muted", "card"), ("text-muted", "surface"),
    ("sidebar-text", "sidebar-bg"), ("sidebar-text-strong", "sidebar-bg"), ("sidebar-muted", "sidebar-bg"),
    ("sidebar-text", "sidebar-surface"), ("sidebar-text-strong", "sidebar-active"), ("sidebar-text-strong", "sidebar-hover"),
    ("indigo", "card"), ("indigo", "indigo-light"), ("teal-text", "teal-light"), ("amber-text", "amber-light"),
    ("rose-text", "rose-light"), ("text-secondary", "surface"),
])
def test_token_pairs_meet_wcag_aa(fg, bg):
    assert _contrast(TOKENS[fg], TOKENS[bg]) >= 4.5, f"{fg} on {bg}: {_contrast(TOKENS[fg], TOKENS[bg]):.2f}"


def test_white_text_on_primary_button_meets_aa():
    assert _contrast("#ffffff", TOKENS["indigo"]) >= 4.5 and _contrast("#ffffff", TOKENS["indigo-hover"]) >= 4.5


def test_builders_escape_text():
    for markup in (
        badge_html(EVIL), notice_html(EVIL, title=EVIL), section_heading_html(EVIL, EVIL), card_html("", title=EVIL),
        page_header_html(EVIL, EVIL, eyebrow=EVIL),
    ):
        assert "<script" not in markup and "&lt;script&gt;" in markup


def test_unknown_tone_falls_back_to_neutral():
    assert "ap-badge-neutral" in badge_html("x", "no-such-tone")
    assert "ap-notice-neutral" in notice_html("x", "no-such-tone")


def test_tones_and_optional_parts():
    assert "ap-badge-success" in badge_html("ok", "success") and "●" in badge_html("ok", dot=True) and "●" not in badge_html("ok")
    assert 'role="note"' in notice_html("m") and "ap-notice-title" not in notice_html("m") and "ap-notice-title" in notice_html("m", title="t")
    assert "ap-section-caption" not in section_heading_html("t") and "ap-section-caption" in section_heading_html("t", "c")
    assert "ap-card-title" not in card_html("<p>b</p>") and "<p>b</p>" in card_html("<p>b</p>")


def test_page_header_structure():
    markup = page_header_html("KPI Dashboard", "Sub", badges_html=badge_html("1 rows"))
    assert 'class="ap-topbar"' in markup and "<h1" in markup and markup.count("KPI Dashboard") == 2
    assert "ap-page-subtitle" in markup and "ap-topbar-aside" in markup
    bare = page_header_html("X")
    assert "ap-page-subtitle" not in bare and "ap-topbar-aside" not in bare


def test_brand_and_footer_markup():
    assert "AnalyticsPro" in sidebar_brand_html() and "ap-nav-label" in sidebar_brand_html()
    assert "AnalyticsPro" in footer_html()


def test_render_wrappers_call_streamlit(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(common.st, "markdown", lambda html, unsafe_allow_html=False: calls.append(html))
    common.inject_global_css()
    common.render_page_header("T", "S")
    common.render_section_heading("H", "C")
    assert len(calls) == 3 and calls[0].startswith("<style>") and "ap-page-title" in calls[1] and "ap-section-title" in calls[2]


# ------------------------------------------------------------------ Stage 2 helpers
def test_progress_clamps_and_exposes_value_as_text_and_aria():
    from views.common import progress_html

    full = progress_html(150, "Done", "150%", "success")
    assert 'aria-valuenow="100"' in full and "width:100.0%" in full and "ap-fill-success" in full and "150%" in full
    assert 'aria-valuenow="0"' in progress_html(-5, "x") and 'aria-valuenow="0"' in progress_html(float("nan"), "x")
    assert "&lt;script&gt;" in progress_html(5, EVIL, EVIL) and "<script" not in progress_html(5, EVIL, EVIL)


def test_share_bar_legend_is_text_and_escaped():
    from views.common import share_bar_html

    markup = share_bar_html("cat", "3 distinct", [("A", 50), (EVIL, 25), ("Zero", 0), ("B", 25)])
    assert "A: 50 (50%)" in markup and "&lt;script&gt;" in markup and "<script" not in markup and "Zero" not in markup
    empty = share_bar_html("cat", "none", [("A", 0)])
    assert "ap-stack" not in empty and "cat" in empty


def test_kv_hero_insight_callout_are_escaped():
    from views.common import callout_html, hero_html, insight_grid_html, insight_html, kv_rows_html

    for markup in (kv_rows_html([(EVIL, EVIL)]), hero_html(EVIL, EVIL, EVIL, [EVIL]), callout_html(EVIL, EVIL)):
        assert "<script" not in markup and "&lt;script&gt;" in markup
    assert 'class="ap-insight"' in insight_html("<b>ok</b>") and "ap-grid" in insight_grid_html([insight_html("x")])
    assert "ap-hero-badges" not in hero_html("i", "t", "b")


def test_style_figure_applies_shared_look():
    import plotly.graph_objects as go

    fig = common.style_figure(go.Figure(go.Bar(x=[1], y=[1])), 300)
    assert fig.layout.height == 300 and fig.layout.paper_bgcolor == "rgba(0,0,0,0)" and fig.layout.colorway[0] == TOKENS["indigo"]
