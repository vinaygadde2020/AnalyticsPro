"""Stage 3: the four analytics screens (Interactive Dashboard, Visualizations, Correlation, Outlier Detection).

Checks, through Streamlit AppTest, that the redesigned pages render for awkward data, keep every widget key and
metric label, use the shared design tokens, never modify the dataset, and that the new navigation buttons work.
"""

import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_app
from tests.test_core_screens import _Balance
from views import dashboard_ui as ui
from views.common import CHART_COLORS, TOKENS

PAGES = ["Interactive Dashboard", "Visualizations", "Correlation & Relationships", "Outlier Detection"]


def _datasets() -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(11)
    n = 80
    base = pd.DataFrame({
        "region": rng.choice(["N", "S", "E"], n), "units": rng.integers(1, 30, n), "revenue": rng.gamma(2, 100, n).round(2),
        "price": rng.normal(20, 4, n).round(2), "when": pd.date_range("2024-01-01", periods=n, freq="D"),
    })
    base.loc[:3, "revenue"] = [5000.0, 6000.0, 7000.0, 9000.0]     # planted outliers
    gaps = base.copy()
    gaps.loc[::6, "price"] = np.nan
    gaps = pd.concat([gaps, gaps.head(3)], ignore_index=True)
    return {
        "clean": base, "gaps_and_duplicates": gaps,
        "categorical_only": pd.DataFrame({"a": ["x", "y", "x", "z"] * 5, "b": ["p", "q"] * 10}),
        "numeric_only": pd.DataFrame({"u": rng.normal(size=40), "v": rng.integers(0, 9, 40)}),
        "single_numeric": pd.DataFrame({"g": ["a", "b"] * 5, "m": np.arange(10.0)}),
        "single_row": pd.DataFrame({"a": ["x"], "n": [1.5]}),
        "constant_numeric": pd.DataFrame({"k": [3.0] * 20, "j": np.arange(20.0)}),
        "empty": pd.DataFrame({"a": pd.Series(dtype=float)}),
    }


DATASETS = _datasets()


def _html(at) -> str:
    return " ".join(m.value for m in at.markdown)


@pytest.mark.parametrize("page", PAGES)
@pytest.mark.parametrize("name", list(DATASETS))
def test_pages_render_for_awkward_datasets(page, name):
    at = make_app(DATASETS[name], f"{name}.csv", page=page)
    assert not at.exception, f"{page} / {name}: {at.exception}"


@pytest.mark.parametrize("page", PAGES)
def test_pages_do_not_modify_the_dataset(page):
    df = DATASETS["gaps_and_duplicates"]
    at = make_app(df, "x.csv", page=page)
    pd.testing.assert_frame_equal(at.session_state["df"], df)
    pd.testing.assert_frame_equal(at.session_state["original_df"], df)


@pytest.mark.parametrize("page", PAGES)
def test_pages_use_the_shared_intro_not_a_duplicate_title(page):
    at = make_app(DATASETS["clean"], "x.csv", page=page)
    assert "ap-page-intro" in _html(at)
    assert not at.subheader                       # the title already lives in the global page header
    assert 'class="dash-title"' not in _html(at)


@pytest.mark.parametrize("page", PAGES)
def test_generated_html_is_balanced(page):
    at = make_app(DATASETS["gaps_and_duplicates"], "x.csv", page=page)
    for md in at.markdown:
        if "<div" not in md.value and "<span" not in md.value:
            continue
        check = _Balance()
        check.parser.feed(md.value)
        assert not check.errors and not check.stack, f"{page}: unbalanced {check.errors or check.stack} in {md.value[:80]!r}"


# ----------------------------------------------------------------- keys and labels kept
def test_visualizations_keeps_every_control_key():
    at = make_app(DATASETS["clean"], page="Visualizations")
    for key in ("vis_chart_type", "vis_palette", "vis_group_x", "vis_metric_y", "vis_agg"):
        assert at.selectbox(key=key) is not None
    assert at.slider(key="vis_height") is not None and at.slider(key="vis_top_n") is not None
    assert at.checkbox(key="vis_grid") is not None
    for chart, keys in {"Histogram": ["vis_single_num", "vis_color_by"], "Scatter Plot": ["vis_scat_x", "vis_scat_y", "vis_scat_cat"]}.items():
        at.selectbox(key="vis_chart_type").set_value(chart).run()
        assert not at.exception
        for key in keys:
            assert at.selectbox(key=key) is not None


def test_visualizations_studio_and_recommendation_cards_present():
    html_text = _html(make_app(DATASETS["clean"], page="Visualizations"))
    assert "Chart studio" in html_text
    assert any(b.key and b.key.startswith("smart_rec_apply_") for b in make_app(DATASETS["clean"], page="Visualizations").button)


def test_correlation_keeps_keys_and_summarises_real_values():
    df = DATASETS["clean"].assign(double_units=lambda d: d["units"] * 2 + np.linspace(0, 1, len(d)))
    at = make_app(df, page="Correlation & Relationships")
    for key in ("corr_method", "corr_colorscale", "corr_pair_select", "corr_scat_cat"):
        assert at.selectbox(key=key) is not None
    assert at.slider(key="corr_threshold") is not None
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Features Compared"] == str(len(df.select_dtypes("number").columns))
    corr = df.select_dtypes("number").corr()
    upper = corr.where(np.triu(np.ones(corr.shape), 1).astype(bool)).abs().stack()
    assert upper.max() > 0.9
    assert metrics["Strongest |r|"] == f"{round(float(upper.max()), 3):.3f}"


def test_correlation_high_threshold_shows_no_pairs():
    at = make_app(DATASETS["clean"], page="Correlation & Relationships")
    at.slider(key="corr_threshold").set_value(1.0).run()
    assert not at.exception
    assert {m.label: m.value for m in at.metric}["Pairs Above Threshold"] == "0"
    assert any("threshold" in i.value.lower() for i in at.info)


def test_outlier_metric_labels_and_flag_badge():
    at = make_app(DATASETS["clean"], page="Outlier Detection")
    at.selectbox(key="outlier_col").set_value("revenue").run()
    metrics = {m.label: m.value for m in at.metric}
    assert set(metrics) == {"Total Outliers", "Outlier Percentage", "Lower Bound Limit", "Upper Bound Limit"}
    flagged = int(metrics["Total Outliers"])
    assert flagged >= 4
    html_text = _html(at)
    assert f"{flagged:,} records flagged" in html_text and "IQR rule" in html_text
    at.radio(key="outlier_method").set_value("Z-Score Method").run()
    assert "Z-score rule" in _html(at)


def test_outlier_none_flagged_shows_success_state():
    at = make_app(DATASETS["constant_numeric"], page="Outlier Detection")
    at.selectbox(key="outlier_col").set_value("k").run()
    assert "No outliers flagged" in _html(at) and at.success


# ----------------------------------------------------------------- navigation buttons
def _btn(at, key):
    return next(b for b in at.button if b.key == key)


def test_correlation_goto_outliers():
    at = make_app(DATASETS["clean"], page="Correlation & Relationships")
    _btn(at, "corr_goto_outliers").click().run()
    assert at.session_state["current_page"] == "Outlier Detection" and not at.exception


def test_outlier_goto_data_preparation_only_when_flagged():
    at = make_app(DATASETS["clean"], page="Outlier Detection")
    at.selectbox(key="outlier_col").set_value("revenue").run()
    _btn(at, "outlier_goto_prep").click().run()
    assert at.session_state["current_page"] == "Data Preparation" and not at.exception
    none = make_app(DATASETS["constant_numeric"], page="Outlier Detection")
    none.selectbox(key="outlier_col").set_value("k").run()
    assert not any(b.key == "outlier_goto_prep" for b in none.button)


# ----------------------------------------------------------------- interactive dashboard
def test_dashboard_palette_comes_from_the_shared_tokens():
    assert ui.PAGE_BG == TOKENS["surface"] and ui.CARD_BG == TOKENS["card"] and ui.CARD_BORDER == TOKENS["border"]
    assert ui.TITLE == TOKENS["text"] and ui.NAVY == TOKENS["sidebar-bg"] and ui.NAVY_ACTIVE == TOKENS["sidebar-active"]
    assert ui.DONUT_PALETTE == CHART_COLORS[:6]


def test_dashboard_slice_badge_follows_the_filters():
    df = DATASETS["clean"]
    at = make_app(df, "sales.csv", page="Interactive Dashboard")
    assert f"Active slice · {len(df):,} of {len(df):,} records (100.0%)" in _html(at)
    at.selectbox(key="linked_dash_category").set_value("region").run()
    at.multiselect(key="linked_dash_values_region").set_value(["N"]).run()
    n = int((df["region"] == "N").sum())
    assert f"Active slice · {n:,} of {len(df):,} records" in _html(at)


def test_dashboard_smart_builder_and_reset_still_work():
    at = make_app(DATASETS["clean"], "sales.csv", page="Interactive Dashboard")
    at.button(key="linked_dash_build_smart").click().run()
    assert at.session_state["linked_dash_smart_built"] is True and not at.exception
    at.selectbox(key="linked_dash_aggregation").set_value("Average").run()
    at.button(key="linked_dash_reset").click().run()
    assert at.selectbox(key="linked_dash_aggregation").value == "Sum" and not at.exception


def test_dashboard_kpi_card_layout_keeps_test_hooks():
    card = {"key": "metric", "label": "Sum rev", "value": "210", "caption": "rev", "delta_text": "-4.5%",
            "delta_note": "vs full dataset", "direction": "down", "tone": "bad"}
    markup = ui.kpi_card_html(card)
    assert markup.count('class="dash-kpi"') == 1 and '<div class="dash-kpi-value">210</div>' in markup
    assert ui.ICON_COLORS["metric"] in markup and "dash-tone-bad" in markup
