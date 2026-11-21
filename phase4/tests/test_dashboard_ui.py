"""Dashboard HTML/CSS: escaping, structure, palette contrast, sidebar styling, and the page itself."""
import re

import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_app
from views import dashboard_ui as ui

EVIL = '<script>alert(1)</script>"><img src=x onerror=alert(2)>'


def _luminance(hex_colour):
    channels = [int(hex_colour.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a, b):
    high, low = sorted([_luminance(a), _luminance(b)], reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("name,fg,bg", ui.TEXT_PAIRS)
def test_every_text_background_pair_meets_wcag_aa(name, fg, bg):
    assert _contrast(fg, bg) >= 4.5, f"{name}: {_contrast(fg, bg):.2f}"


def test_css_is_fully_filled_in_and_uses_the_palette():
    css = ui.dashboard_css()
    assert not re.findall(r"%[A-Z_]+%", css)
    for colour in (ui.PAGE_BG, ui.CARD_BG, ui.TITLE, ui.MUTED, ui.TONES["good"][0]):
        assert colour in css
    assert "st-key-dashcard_" in css


def test_sidebar_css_uses_the_navy_palette_and_highlights_the_active_page():
    # The shared stylesheet moved to views/common.py (Stage 1 UI foundation): navy sidebar, indigo active page.
    from views.common import TOKENS, build_global_css

    css = build_global_css()
    assert TOKENS["sidebar-bg"] == ui.NAVY
    assert "background: var(--ap-sidebar-bg)" in css and "--ap-sidebar-active: #4f46e5" in css
    assert "stBaseButton-primary" in css


def test_every_user_controlled_string_is_escaped():
    card = {"key": "records", "label": EVIL, "value": EVIL, "caption": EVIL, "delta_text": EVIL, "delta_note": EVIL,
            "direction": "up", "tone": "good"}
    pieces = [
        ui.kpi_card_html(card), ui.kpi_row_html([card]), ui.card_title_html(EVIL, EVIL),
        ui.legend_html([{"label": EVIL, "value": 1, "share": 1.0}], lambda v: EVIL),
        ui.status_list_html([{"name": EVIL, "detail": EVIL, "status": "ok"}]),
        ui.ring_html(50, EVIL, EVIL, [(EVIL, EVIL)]), ui.header_html(EVIL, EVIL),
    ]
    for markup in pieces:
        assert "<script" not in markup and "<img" not in markup and 'onerror=alert(2)>' not in markup
        assert "&lt;script&gt;" in markup


def test_kpi_card_has_icon_label_value_caption_delta_and_arrow():
    card = {"key": "metric", "label": "Sum rev", "value": "210", "caption": "rev", "delta_text": "-4.5%",
            "delta_note": "vs full dataset", "direction": "down", "tone": "neutral"}
    markup = ui.kpi_card_html(card)
    for needle in ("Sum rev", "210", "-4.5%", "vs full dataset", "▼", "<svg", ui.ICON_COLORS["metric"], 'aria-label="Sum rev"'):
        assert needle in markup


def test_status_pills_use_words_and_symbols_not_colour_alone():
    markup = ui.status_list_html([{"name": "a", "detail": "d", "status": s} for s in ("ok", "warn", "bad", "unknown")])
    for text in ("✓ Good", "! Review", "✕ Fix"):
        assert text in markup
    assert markup.count("dash-pill") == 4


@pytest.mark.parametrize("percent,expected", [(0, "0.00"), (50, "163.36"), (100, "326.73"), (250, "326.73"), (-5, "0.00")])
def test_ring_arc_length_is_clamped(percent, expected):
    assert f'stroke-dasharray="{expected} ' in ui.ring_html(percent, "x", "y", [])


def test_legend_colours_follow_the_donut_palette():
    items = [{"label": str(i), "value": i, "share": 0.1} for i in range(8)]
    markup = ui.legend_html(items, str)
    for colour in ui.DONUT_PALETTE:
        assert colour in markup
    assert markup.count("dash-dot") == 8


# ---------------------------------------------------------------- the page
@pytest.fixture
def data():
    rng = np.random.default_rng(2)
    n = 120
    df = pd.DataFrame({"region": rng.choice(list("NSEW"), n), "rev": rng.gamma(2, 400, n).round(2),
                       "units": rng.integers(1, 50, n), "day": pd.date_range("2024-01-01", periods=n)})
    df.loc[:5, "rev"] = np.nan
    return df


def _html(at):
    return " ".join(m.value for m in at.markdown)


def test_dashboard_shows_the_reference_layout(data):
    at = make_app(data, "sales.csv", page="Interactive Dashboard")
    assert not at.exception
    html_text = _html(at)
    assert html_text.count('class="dash-kpi"') == 4
    for title in ("Composition", "Data Quality Checks", "Completeness", "Latest Records"):
        assert f">{title}" in html_text, title
    assert "dash-ring" in html_text and "dash-status" in html_text and "dash-legend" in html_text
    assert any(c.id for c in at.get("plotly_chart"))


def test_filters_update_the_kpi_cards(data):
    at = make_app(data, "sales.csv", page="Interactive Dashboard")
    at.selectbox(key="linked_dash_category").set_value("region")
    at.run()
    at.multiselect(key="linked_dash_values_region").set_value(["N"])
    at.run()
    html_text = _html(at)
    expected = int((data["region"] == "N").sum())
    assert f'<div class="dash-kpi-value">{expected}</div>' in html_text
    assert "Distinct region" in html_text


def test_dashboard_still_has_every_previous_control(data):
    at = make_app(data, "sales.csv", page="Interactive Dashboard")
    for key in ("linked_dash_metric", "linked_dash_aggregation", "linked_dash_category", "linked_dash_date_col",
                "linked_dash_trend_grain", "linked_dash_custom_x", "linked_dash_custom_y", "linked_dash_custom_color"):
        assert at.selectbox(key=key) is not None
    assert at.button(key="linked_dash_build_smart") is not None and at.button(key="linked_dash_reset") is not None
    assert at.multiselect(key="linked_dash_custom_kpi_columns") is not None


def test_hostile_column_names_and_values_cannot_inject_markup():
    df = pd.DataFrame({EVIL: ["a", "b", "a", "b"] * 5, "value": np.arange(20.0), "when": pd.date_range("2024-01-01", periods=20)})
    at = make_app(df, EVIL + ".csv", page="Interactive Dashboard")
    assert not at.exception
    at.selectbox(key="linked_dash_category").set_value(EVIL)
    at.run()
    assert not at.exception
    html_text = _html(at)
    assert "<script>alert(1)" not in html_text and "<img src=x" not in html_text


def test_dashboard_degrades_gracefully_without_numbers_or_categories():
    only_text = pd.DataFrame({"a": ["x", "y", "z"], "b": ["p", "q", "r"]})
    only_nums = pd.DataFrame({"a": np.arange(10.0), "b": np.arange(10.0) ** 2})
    for df in (only_text, only_nums):
        at = make_app(df, "x.csv", page="Interactive Dashboard")
        assert not at.exception
        assert _html(at).count('class="dash-kpi"') == 4


def test_current_page_is_highlighted_in_the_sidebar(data):
    at = make_app(data, "sales.csv", page="Interactive Dashboard")
    primary = [b.label for b in at.sidebar.button if b.proto.type == "primary"]
    assert len(primary) == 1 and "Interactive Dashboard" in primary[0]
