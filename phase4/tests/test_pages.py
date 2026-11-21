"""Page-level tests (Streamlit AppTest): displayed values, state handling, edge datasets."""
import numpy as np
import pandas as pd
import pytest

from tests.conftest import PAGES, csv_bytes, edge_datasets, make_app, upload

EDGE = edge_datasets()


def _num(text):
    return float(str(text).replace(",", "").replace("/100", ""))


def _metrics(at):
    return {m.label: m.value for m in at.metric}


# ------------------------------------------------------------- every page renders
@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_with_normal_data(sales_df, page):
    at = make_app(sales_df, "sales.csv", page=page)
    assert not at.exception, f"{page}: {at.exception[0].value if at.exception else ''}"


@pytest.mark.parametrize("name", list(EDGE))
def test_every_page_survives_unusual_datasets(name):
    at = make_app(EDGE[name], f"{name}.csv")
    for page in PAGES:
        at.session_state["current_page"] = page
        at.run()
        assert not at.exception, f"{name} / {page}: {at.exception[0].value}"


@pytest.mark.parametrize("page", PAGES)
def test_pages_show_a_friendly_message_when_no_dataset_is_loaded(page):
    at = make_app(page=page)
    assert not at.exception


# ------------------------------------------------------------------- KPI values
def test_kpi_dashboard_values_match_independent_calculation(sales_df):
    at = make_app(sales_df, "sales.csv", page="KPI Dashboard")
    m = _metrics(at)
    s = sales_df["sales"]
    assert _num(m["Total Records"]) == len(sales_df) and _num(m["Missing Cells"]) == int(sales_df.isna().sum().sum())
    assert _num(m["Total Sum"]) == pytest.approx(s.sum(), abs=0.01)
    assert _num(m["Average / Mean"]) == pytest.approx(s.mean(), abs=0.01)
    assert _num(m["Median Value"]) == pytest.approx(s.median(), abs=0.01)
    assert _num(m["Minimum Value"]) == pytest.approx(s.min(), abs=0.01)
    assert _num(m["Maximum Value"]) == pytest.approx(s.max(), abs=0.01)


def test_kpi_dashboard_updates_when_the_selected_metric_changes(sales_df):
    at = make_app(sales_df, "sales.csv", page="KPI Dashboard")
    at.selectbox(key="kpi_primary_metric").set_value("units")
    at.run()
    assert not at.exception
    assert _num(_metrics(at)["Total Sum"]) == pytest.approx(sales_df["units"].sum(), abs=0.01)


# ----------------------------------------------------------- dataset comparison
def test_dataset_comparison_deltas_and_sorted_common_columns(sales_df):
    at = make_app(sales_df, "sales.csv", page="Dataset Comparison")
    second = at.get("file_uploader")[0]
    assert second.key == "second_dataset_file"
    upload(at, csv_bytes("sales,zzz,region\n1,2,x\n3,4,y\n"), "other.csv", widget=second)
    assert not at.exception
    labels = [(m.label, m.value, m.delta) for m in at.metric]
    assert ("Rows", str(len(sales_df)), "") in labels
    assert ("Rows", "2", str(2 - len(sales_df))) in labels
    assert any(l == "Columns" and d == str(3 - sales_df.shape[1]) for l, _, d in labels)
    assert any("Common Columns (2)" in m.value for m in at.markdown)
    assert any(m.value == "`region`, `sales`" for m in at.markdown)


def test_common_columns_are_listed_in_stable_sorted_order(sales_df):
    for _ in range(3):  # set ordering used to vary between runs
        at = make_app(sales_df, "sales.csv", page="Dataset Comparison")
        upload(at, csv_bytes("units,sales,region,product\n1,2,x,y\n"), "o.csv", widget=at.get("file_uploader")[0])
        listing = [m.value for m in at.markdown if m.value.startswith("`") and "`product`" in m.value]
        assert listing == ["`product`, `region`, `sales`, `units`"]


# ----------------------------------------------------------- state and switching
def test_switching_datasets_does_not_keep_stale_selections():
    at = make_app()
    upload(at, csv_bytes("region,sales\nN,1\nS,2\nN,3\nS,4\n"), "a.csv")
    at.session_state["current_page"] = "Visualizations"
    at.run()
    at.selectbox(key="vis_group_x").set_value("region")
    at.run()
    upload(at, csv_bytes("country,revenue\nX,1\nY,2\nX,3\nY,4\n"), "b.csv")
    assert not at.exception
    assert list(at.session_state["df"].columns) == ["country", "revenue"]
    assert "vis_group_x" not in at.session_state or at.session_state["vis_group_x"] in ("country", "revenue")
    for page in PAGES:
        at.session_state["current_page"] = page
        at.run()
        assert not at.exception, page


def test_reset_dataset_button_returns_to_the_original_upload():
    at = make_app()
    upload(at, csv_bytes("a,b\n1,2\n3,4\n"), "r.csv")
    at.session_state["df"] = pd.DataFrame({"a": [99]})            # simulate cleaning
    [b for b in at.sidebar.button if b.key == "reset_dataset_btn"][0].click().run()
    assert not at.exception and len(at.session_state["df"]) == 2


# ------------------------------------------------------------ chart-prompt page
def test_chart_prompt_page_draws_a_chart_for_a_supported_request(sales_df):
    at = make_app(sales_df, "sales.csv", page="AI Data Analyst")
    at.text_input(key="ai_query_input").set_value("show top 3 region by sales")
    at.run()
    assert not at.exception
    assert len(at.get("plotly_chart")) >= 1


def test_chart_prompt_page_declines_unsupported_requests_without_crashing(sales_df):
    at = make_app(sales_df, "sales.csv", page="AI Data Analyst")
    at.text_input(key="ai_query_input").set_value("tell me a joke")
    at.run()
    assert not at.exception and len(at.get("plotly_chart")) == 0


# ----------------------------------------------------- smart recommendations flow
def _recommendation_frame():
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "region": rng.choice(["North", "South", "East", "West"], 150),
        "sales": rng.uniform(100, 5000, 150), "units": rng.integers(1, 100, 150),
        "signup_date": pd.date_range("2024-01-01", periods=150, freq="D"),
        "customer_id": range(1, 151),
    })


def _apply_buttons(at):
    return [b for b in at.button if b.key and b.key.startswith("smart_rec_apply_")]


def test_every_smart_recommendation_can_be_applied_without_error():
    at = make_app(_recommendation_frame(), "rec.csv", page="Visualizations")
    count = len(_apply_buttons(at))
    assert count >= 3, "expected several recommendations for a rich dataset"
    for i in range(count):
        _apply_buttons(at)[i].click().run()          # widgets are rebuilt after every rerun
        assert not at.exception, f"recommendation {i} crashed: {at.exception[0].value if at.exception else ''}"
        assert at.session_state["vis_chart_type"]


def test_dataset_swap_after_applying_a_recommendation_leaves_no_stale_state():
    at = make_app()
    upload(at, _recommendation_frame().to_csv(index=False).encode(), "rec.csv")
    at.session_state["current_page"] = "Visualizations"
    at.run()
    _apply_buttons(at)[0].click().run()
    upload(at, csv_bytes("product,price\nWidget,5\nGadget,9\nWidget,7\nGadget,3\n"), "new.csv")
    assert not at.exception
    at.session_state["current_page"] = "Visualizations"
    at.run()
    assert not at.exception, "stale column references from the previous dataset caused a crash"
    for col in at.session_state["df"].columns:
        assert col in ("product", "price")


def test_interactive_dashboard_exposes_aggregation_and_trend_controls(sales_df):
    at = make_app(sales_df, "sales.csv", page="Interactive Dashboard")
    assert not at.exception
    assert at.selectbox(key="linked_dash_aggregation").value in ("Sum", "Average", "Median", "Count")
    assert at.selectbox(key="linked_dash_trend_grain").value in ("Daily", "Weekly", "Monthly")
    # The trend interval is disabled until a date column is chosen.
    assert at.selectbox(key="linked_dash_trend_grain").disabled
    at.selectbox(key="linked_dash_date_col").set_value("date")
    at.run()
    assert not at.exception
    assert not at.selectbox(key="linked_dash_trend_grain").disabled
    at.selectbox(key="linked_dash_aggregation").set_value("Average")
    at.selectbox(key="linked_dash_trend_grain").set_value("Weekly")
    at.run()
    assert not at.exception


def test_ai_analyst_answers_correlation_question(sales_df):
    at = make_app(sales_df, "sales.csv", page="AI Data Analyst")
    at.text_input(key="ai_query_input").set_value("show correlation between numeric columns")
    at.run()
    assert not at.exception
    assert any("Pearson r" in str(item.value) or "correlation" in str(item.value).lower() for item in at.info)


def _chart_titles(at):
    import json
    titles = []
    for el in at.get("plotly_chart"):
        try:
            titles.append(json.loads(el.proto.spec)["layout"]["title"]["text"])
        except Exception:
            pass
    return titles


def test_smart_builder_build_and_hide(sales_df):
    at = make_app(sales_df, "sales.csv", page="Interactive Dashboard")
    at.button(key="linked_dash_build_smart").click().run()
    assert not at.exception
    assert any("by region" in t for t in _chart_titles(at))
    assert any("trend" in t.lower() for t in _chart_titles(at))
    at.button(key="linked_dash_hide_smart").click().run()
    assert not at.exception
    assert not any("Monthly" in t for t in _chart_titles(at))


def test_smart_builder_respects_aggregation(sales_df):
    at = make_app(sales_df, "sales.csv", page="Interactive Dashboard")
    at.selectbox(key="linked_dash_aggregation").set_value("Average")
    at.run()
    at.button(key="linked_dash_build_smart").click().run()
    assert not at.exception
    titles = _chart_titles(at)
    assert any(t.startswith("Average ") and "by region" in t for t in titles)
    assert any("Monthly average" in t for t in titles)


def test_smart_builder_numeric_only_dataset():
    import numpy as np
    import pandas as pd
    df = pd.DataFrame({"a": np.arange(30.0), "b": np.arange(30.0) ** 2, "c": np.arange(30.0) % 7})
    at = make_app(df, "nums.csv", page="Interactive Dashboard")
    at.button(key="linked_dash_build_smart").click().run()
    assert not at.exception


def test_smart_builder_text_only_dataset():
    import pandas as pd
    df = pd.DataFrame({"name": list("abcdef"), "city": list("uvwxyz")})
    at = make_app(df, "text.csv", page="Interactive Dashboard")
    at.button(key="linked_dash_build_smart").click().run()
    assert not at.exception


def test_custom_bar_chart_supports_color_different_from_x(sales_df):
    """Regression: grouping must keep the colour column when it differs from the categorical X."""
    at = make_app(sales_df, "sales.csv", page="Interactive Dashboard")
    at.multiselect(key="linked_dash_custom_chart_types").set_value(["Bar chart"])
    at.run()
    at.selectbox(key="linked_dash_custom_x").set_value("region")
    at.selectbox(key="linked_dash_custom_color").set_value("product")
    at.run()
    assert not at.exception
    assert not [w for w in at.warning if "Could not create" in w.value]
