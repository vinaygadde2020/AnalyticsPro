"""Stage 2: the four core screens (Upload, Data Preparation, Automatic EDA, KPI Dashboard).

Behaviour is checked through Streamlit AppTest: pages render for realistic and awkward datasets, show values derived from
the data, never mutate the dataset just by being viewed, and keep their widget keys.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tests.conftest import csv_bytes, make_app, upload
from views.eda import _dispersion_table, _share_segments
from views.kpi import _share_frame

CORE_PAGES = ["Data Upload & Preview", "Data Preparation", "Automatic EDA", "KPI Dashboard"]
SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample_data"


def _datasets() -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(7)
    n = 60
    base = pd.DataFrame({
        "region": rng.choice(["N", "S", "E"], n), "units": rng.integers(1, 30, n), "revenue": rng.gamma(2, 100, n).round(2),
        "when": pd.date_range("2024-01-01", periods=n, freq="D"),
    })
    with_gaps = base.copy()
    with_gaps.loc[::7, "revenue"] = np.nan
    with_gaps.loc[::9, "region"] = None
    with_gaps = pd.concat([with_gaps, with_gaps.head(3)], ignore_index=True)  # duplicates too
    return {
        "clean": base,
        "missing_and_duplicates": with_gaps,
        "categorical_only": pd.DataFrame({"a": ["x", "y", "x", "z"] * 5, "b": ["p", "q"] * 10}),
        "numeric_only": pd.DataFrame({"u": rng.normal(size=40), "v": rng.integers(0, 9, 40)}),
        "single_row": pd.DataFrame({"a": ["x"], "n": [1.5]}),
        "no_dates": base.drop(columns="when"),
        "all_missing_metric": pd.DataFrame({"g": ["a", "b", "a"], "m": [np.nan, np.nan, np.nan]}),
        "negative_values": pd.DataFrame({"g": ["a", "b", "a", "c"], "m": [-1.0, -2.0, -3.0, -4.0]}),
        "empty": pd.DataFrame({"a": pd.Series(dtype=float)}),
    }


DATASETS = _datasets()


@pytest.mark.parametrize("page", CORE_PAGES)
@pytest.mark.parametrize("name", list(DATASETS))
def test_core_pages_render_for_awkward_datasets(page, name):
    at = make_app(DATASETS[name], f"{name}.csv", page=page)
    assert not at.exception, f"{page} / {name}: {at.exception}"


@pytest.mark.parametrize("page", CORE_PAGES)
def test_core_pages_do_not_modify_the_dataset_or_session_data(page):
    df = DATASETS["missing_and_duplicates"]
    at = make_app(df, "x.csv", page=page)
    pd.testing.assert_frame_equal(at.session_state["df"], df)
    pd.testing.assert_frame_equal(at.session_state["original_df"], df)
    assert not at.session_state["cleaning_history"]


@pytest.mark.parametrize("filename", ["retail_sales_messy.csv", "employees_semicolon.csv", "weather_stations_numeric.csv"])
def test_sample_files_upload_and_all_core_pages_render(filename):
    at = make_app()
    upload(at, (SAMPLE_DIR / filename).read_bytes(), filename)
    assert not at.exception
    for page in CORE_PAGES:
        at.session_state["current_page"] = page
        at.run()
        assert not at.exception, f"{page} on {filename}: {at.exception}"
    assert at.session_state["dataset_name"] == filename


# ------------------------------------------------------------------------------ Upload
def test_upload_page_empty_state_points_to_the_sidebar():
    at = make_app(page="Data Upload & Preview")
    assert not at.exception
    assert any("Upload a dataset to begin" in m.value for m in at.markdown)


def test_upload_page_shows_real_parser_state_for_a_semicolon_csv():
    at = make_app()
    upload(at, csv_bytes("item;price\nA;12,50\nB;3,25\n"), "eu.csv")
    text = "\n".join(m.value for m in at.markdown)
    assert "Semicolon" in text and "utf-8" in text.lower() and "Decimal separator" in text and "Preserved" in text
    labels = {m.label: m.value for m in at.metric}
    assert labels["Rows"] == "2" and labels["Columns"] == "2"


def test_upload_page_offers_data_prep_only_when_issues_exist():
    messy = make_app(DATASETS["missing_and_duplicates"], page="Data Upload & Preview")
    assert any(b.key == "upload_goto_prep" for b in messy.button) and messy.warning
    clean = make_app(pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]}), page="Data Upload & Preview")
    assert not any(b.key == "upload_goto_prep" for b in clean.button) and clean.success


# ------------------------------------------------------------------------ Data Preparation
def _btn(at, key):
    return [b for b in at.button if b.key == key][0]


def test_prep_auto_clean_records_history_and_reset_restores():
    df = DATASETS["missing_and_duplicates"]
    at = make_app(df, "x.csv", page="Data Preparation")
    assert len(at.tabs) == 10
    _btn(at, "quick_auto_clean_btn").click().run()
    assert not at.exception
    cleaned = at.session_state["df"]
    assert int(cleaned.isna().sum().sum()) == 0 and not cleaned.duplicated().any()
    history = at.session_state["cleaning_history"]
    assert len(history) == 1 and "Quick Auto-Clean" in history[0]["action"]
    assert any("ap-history" in m.value for m in at.markdown)
    _btn(at, "reset_prep_changes_btn").click().run()
    assert at.session_state["cleaning_history"] == []
    pd.testing.assert_frame_equal(at.session_state["df"], df)


def test_prep_restore_original_clears_history():
    df = DATASETS["clean"]
    at = make_app(df, "x.csv", page="Data Preparation")
    at.selectbox(key="cm_rename_col").set_value("region")
    at.text_input(key="cm_new_name").set_value("area")
    at.run()
    _btn(at, "apply_rename_btn").click().run()
    assert "area" in at.session_state["df"].columns and at.session_state["cleaning_history"]
    _btn(at, "restore_original_prep_btn").click().run()
    assert "region" in at.session_state["df"].columns and at.session_state["cleaning_history"] == []


# -------------------------------------------------------------------------------- EDA
def test_eda_values_are_derived_from_the_dataset():
    df = DATASETS["missing_and_duplicates"]
    at = make_app(df, "x.csv", page="Automatic EDA")
    labels = {m.label: m.value for m in at.metric}
    assert labels["Rows"] == f"{len(df):,}" and labels["Missing"] == f"{int(df.isna().sum().sum()):,}"
    text = "\n".join(m.value for m in at.markdown)
    assert "IQR" in text and "Missingness" in text and "revenue" in text and 'role="progressbar"' in text
    assert "duplicate rows were detected" in text


def test_eda_dispersion_table_matches_pandas():
    df = DATASETS["clean"]
    from data.profiler import numeric_statistics

    table = _dispersion_table(numeric_statistics(df)).set_index("Column")
    q1, q3 = df["revenue"].quantile(0.25), df["revenue"].quantile(0.75)
    assert table.loc["revenue", "IQR (Q3 - Q1)"] == pytest.approx(q3 - q1, abs=1e-3)
    assert table.loc["revenue", "Range (max - min)"] == pytest.approx(df["revenue"].max() - df["revenue"].min(), abs=1e-3)
    assert _dispersion_table(pd.DataFrame()).empty


def test_eda_share_segments_group_the_tail_as_other_and_ignore_missing():
    series = pd.Series(list("aaaaabbbbcccdde") + [None, None])
    segments = _share_segments(series)
    assert [s[0] for s in segments] == ["a", "b", "c", "d", "Other"] and segments[-1][1] == 1.0
    assert sum(v for _, v in segments) == 15


def test_eda_navigation_buttons_switch_page_without_touching_data():
    df = DATASETS["missing_and_duplicates"]
    at = make_app(df, "x.csv", page="Automatic EDA")
    _btn(at, "eda_goto_prep").click().run()
    assert at.session_state["current_page"] == "Data Preparation" and not at.exception
    pd.testing.assert_frame_equal(at.session_state["df"], df)


# -------------------------------------------------------------------------------- KPI
def test_kpi_trend_and_share_use_real_data():
    df = DATASETS["clean"]
    at = make_app(df, "x.csv", page="KPI Dashboard")
    assert not at.exception
    assert len(at.get("plotly_chart")) >= 3  # trend + donut + bar
    at.selectbox(key="kpi_primary_metric").set_value("revenue")
    at.selectbox(key="kpi_aggregation").set_value("Average")
    at.selectbox(key="kpi_trend_grain").set_value("Weekly")
    at.run()
    assert not at.exception
    text = "\n".join(m.value for m in at.markdown)
    assert "Average of revenue" in text and "weekly" in text


def test_kpi_share_frame_sums_to_positive_total_with_other_bucket():
    df = pd.DataFrame({"g": list("abcdefgh") * 2 + [None], "m": list(range(1, 17)) + [100]})
    frame = _share_frame(df, "m", "g")
    assert len(frame) == 6 and frame.iloc[-1]["Category"] == "Other"
    assert frame["Total"].sum() == pytest.approx(sum(range(1, 17)) + 100)
    assert frame.iloc[0]["Category"] == "Missing" and frame.iloc[0]["Total"] == 100  # NaN category kept, labelled, ranked first
    assert _share_frame(DATASETS["negative_values"], "m", "g").empty


def test_kpi_without_dates_or_categories_degrades_gracefully():
    no_dates = make_app(DATASETS["no_dates"], page="KPI Dashboard")
    assert not no_dates.exception and any("no trend" in i.value.lower() for i in no_dates.info)
    numeric = make_app(DATASETS["numeric_only"], page="KPI Dashboard")
    assert not numeric.exception and any("categorical" in i.value.lower() for i in numeric.info)
    assert not any(s.key == "kpi_breakdown_cat" for s in numeric.selectbox)


def test_kpi_all_missing_metric_shows_message():
    at = make_app(DATASETS["all_missing_metric"], page="KPI Dashboard")
    assert not at.exception and any("no numeric values" in i.value for i in at.info)


def test_kpi_goto_interactive_dashboard():
    at = make_app(DATASETS["clean"], page="KPI Dashboard")
    _btn(at, "kpi_goto_interactive").click().run()
    assert at.session_state["current_page"] == "Interactive Dashboard" and not at.exception


# ------------------------------------------------------------- markup and stale state
class _Balance:
    """Counts unclosed/unexpected tags in generated HTML (void elements ignored)."""

    VOID = {"br", "hr", "img", "input", "meta", "link"}

    def __init__(self):
        from html.parser import HTMLParser

        outer = self
        outer.stack, outer.errors = [], []

        class P(HTMLParser):
            def handle_starttag(self, tag, attrs):
                if tag not in outer.VOID:
                    outer.stack.append(tag)

            def handle_endtag(self, tag):
                if tag in outer.VOID:
                    return
                if outer.stack and outer.stack[-1] == tag:
                    outer.stack.pop()
                else:
                    outer.errors.append(tag)

        self.parser = P()


@pytest.mark.parametrize("page", CORE_PAGES)
def test_generated_html_is_balanced(page):
    at = make_app(DATASETS["missing_and_duplicates"], "x.csv", page=page)
    for md in at.markdown:
        if "<div" not in md.value and "<span" not in md.value:
            continue
        check = _Balance()
        check.parser.feed(md.value)
        assert not check.errors and not check.stack, f"{page}: unbalanced markup {check.errors or check.stack} in {md.value[:80]!r}"


def test_switching_between_two_uploaded_files_does_not_leave_stale_widget_state():
    at = make_app()
    upload(at, (SAMPLE_DIR / "retail_sales_messy.csv").read_bytes(), "retail_sales_messy.csv")
    first_cols = set(at.session_state["df"].columns)
    at.session_state["current_page"] = "KPI Dashboard"
    at.run()
    assert not at.exception
    upload(at, (SAMPLE_DIR / "weather_stations_numeric.csv").read_bytes(), "weather_stations_numeric.csv")
    assert set(at.session_state["df"].columns) != first_cols
    for page in CORE_PAGES:
        at.session_state["current_page"] = page
        at.run()
        assert not at.exception, f"{page}: {at.exception}"
    options = at.selectbox(key="kpi_primary_metric").options if at.session_state["current_page"] == "KPI Dashboard" else []
    assert all(o in at.session_state["df"].columns for o in options)
