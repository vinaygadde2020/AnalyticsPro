"""Page-level checks (Streamlit AppTest) for Ask Your Data, import options and friendly errors."""
import io

import numpy as np
import pandas as pd
import pytest

from tests.conftest import csv_bytes, make_app, upload


@pytest.fixture(scope="module")
def id_df():
    rng = np.random.default_rng(5)
    n = 80
    return pd.DataFrame({"order_id": range(1, n + 1), "station_id": range(500, 500 + n),
                         "region": rng.choice(["N", "S", "E"], n), "sales": rng.uniform(1, 99, n).round(2)})


def _buttons(at):
    return [b for b in at.button if b.key and b.key.startswith("sug_btn_")]


def test_new_page_name_and_legacy_alias_both_work(id_df):
    new = make_app(id_df, page="Ask Your Data")
    old = make_app(id_df, page="AI Data Analyst")
    assert not new.exception and not old.exception
    assert new.session_state["current_page"] == old.session_state["current_page"] == "Ask Your Data"
    assert "Ask Your Data" in " ".join(b.label for b in new.sidebar.button)


def test_page_states_it_is_rule_based_and_not_ai(id_df):
    at = make_app(id_df, page="Ask Your Data")
    captions = " ".join(c.value for c in at.caption)
    assert "not an AI model" in captions and "no API key" in captions


def test_suggestion_buttons_do_not_offer_id_metrics_and_each_works(id_df):
    at = make_app(id_df, page="Ask Your Data")
    labels = [b.label for b in _buttons(at)]
    assert labels and not any("order_id" in l or "station_id" in l for l in labels)
    for i in range(len(labels)):
        fresh = make_app(id_df, page="Ask Your Data")
        fresh.button(key=f"sug_btn_{i}").click()
        fresh.run()
        assert not fresh.exception
        assert not [w for w in fresh.warning if "couldn't confidently" in w.value], labels[i]


def test_id_only_question_without_naming_the_id_uses_a_real_measure(id_df):
    at = make_app(id_df, page="Ask Your Data")
    at.text_input(key="ai_query_input").set_value("show top 3 region")
    at.run()
    assert not at.exception and any("sales" in t for t in _titles(at))


def _titles(at):
    import json
    out = []
    for el in at.get("plotly_chart"):
        try:
            out.append(json.loads(el.proto.spec)["layout"]["title"]["text"])
        except Exception:
            pass
    return out


def test_column_stat_question_on_the_page(id_df):
    at = make_app(id_df, page="Ask Your Data")
    at.text_input(key="ai_query_input").set_value("what is the average sales")
    at.run()
    assert any(f"{id_df['sales'].mean():,.2f}" in s.value for s in at.success)


# ---------------------------------------------------------------- upload + import options
def test_leading_zero_upload_shows_import_note_and_keeps_text():
    at = make_app()
    upload(at, csv_bytes("zip,amount\n00123,1.5\n01234,2.5\n"), "codes.csv")
    assert not at.exception
    assert at.session_state["df"]["zip"].tolist() == ["00123", "01234"]
    assert any("Import notes" in e.label for e in at.expander)


def test_turning_off_leading_zero_option_reloads_as_numbers():
    at = make_app()
    upload(at, csv_bytes("zip,amount\n00123,1.5\n01234,2.5\n"), "codes.csv")
    at.checkbox(key="import_keep_zeros").set_value(False)
    at.run()
    assert not at.exception and at.session_state["df"]["zip"].tolist() == [123, 1234]


def test_decimal_comma_upload_and_forced_locale():
    at = make_app()
    upload(at, csv_bytes("item;price\nA;12,50\nB;3,25\n"), "eu.csv")
    assert at.session_state["df"]["price"].tolist() == [12.5, 3.25]
    amb = make_app()
    upload(amb, csv_bytes("item;price\nA;1,234\nB;2,500\n"), "amb.csv")
    assert amb.session_state["df"]["price"].tolist() == ["1,234", "2,500"]
    amb.selectbox(key="import_decimal").select("Decimal comma  (1.234,50)")
    amb.run()
    assert amb.session_state["df"]["price"].tolist() == [1.234, 2.5]


def test_excel_worksheet_selector_loads_the_chosen_sheet():
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame({"a": [1, 2]}).to_excel(writer, sheet_name="First", index=False)
        pd.DataFrame({"b": [7, 8, 9]}).to_excel(writer, sheet_name="Second", index=False)
    at = make_app()
    upload(at, buf.getvalue(), "wb.xlsx")
    assert list(at.session_state["df"].columns) == ["a"]
    sheet_box = [s for s in at.sidebar.selectbox if s.label == "Worksheet"][0]
    sheet_box.select("Second")
    at.run()
    assert not at.exception and list(at.session_state["df"].columns) == ["b"]


@pytest.mark.parametrize("name,payload", [("bad.csv", b""), ("bad.xlsx", b"not a workbook"),
                                          ("ragged.csv", b"a,b\n1,2\n3,4,5,6\n"), ("header_only.csv", b"a,b\n")])
def test_bad_uploads_show_a_friendly_error_and_keep_the_app_alive(name, payload):
    at = make_app()
    upload(at, payload, name)
    assert not at.exception
    errors = " ".join(e.value for e in at.sidebar.error)
    assert "Could not load this file" in errors
    assert "Traceback" not in errors and "/home" not in errors and "pandas" not in errors.lower()
    assert at.session_state["df"] is None


def test_new_upload_clears_dashboard_selections_from_the_previous_dataset(id_df):
    at = make_app(id_df, page="Interactive Dashboard")
    at.selectbox(key="linked_dash_custom_x").set_value("region")
    at.run()
    upload(at, csv_bytes("p,q\n1,2\n3,4\n"), "other.csv")
    assert not at.exception
    assert "linked_dash_custom_x" not in at.session_state


# ---------------------------------------------------------------- dashboard + shared charts
def test_dashboard_defaults_to_a_measure_not_an_id(id_df):
    at = make_app(id_df, page="Interactive Dashboard")
    assert at.selectbox(key="linked_dash_metric").value == "sales"
    assert "order_id" in at.selectbox(key="linked_dash_metric").options     # still selectable on purpose


def test_dashboard_unsupported_chart_choices_show_friendly_notes_not_errors(id_df):
    at = make_app(id_df, page="Interactive Dashboard")
    at.multiselect(key="linked_dash_custom_chart_types").set_value(
        ["Bar Chart", "Pie Chart", "Donut Chart", "Heatmap", "Violin Plot", "Scatter Plot", "Histogram"])
    at.selectbox(key="linked_dash_custom_x").set_value("sales")
    at.selectbox(key="linked_dash_custom_y").set_value("sales")
    at.run()
    assert not at.exception
    infos = " ".join(i.value for i in at.info)
    assert "different column" in infos or "different columns" in infos
    assert "Traceback" not in infos


@pytest.mark.parametrize("chart", ["Bar Chart", "Line Chart", "Area Chart", "Scatter Plot", "Histogram",
                                   "Box Plot", "Violin Plot", "Pie Chart", "Donut Chart", "Heatmap"])
def test_each_dashboard_chart_type_renders_with_and_without_color(id_df, chart):
    at = make_app(id_df, page="Interactive Dashboard")
    at.multiselect(key="linked_dash_custom_chart_types").set_value([chart])
    at.selectbox(key="linked_dash_custom_x").set_value("region")
    at.selectbox(key="linked_dash_custom_y").set_value("sales")
    at.run()
    assert not at.exception
    plain = len([c for c in at.get("plotly_chart") if (c.id or "")])
    at.selectbox(key="linked_dash_custom_color").set_value("region")
    at.run()
    assert not at.exception and plain >= 1


def test_smart_dashboard_never_uses_identifier_columns(id_df):
    at = make_app(id_df, page="Interactive Dashboard")
    at.button(key="linked_dash_build_smart").click()
    at.run()
    assert not at.exception
    labels = " ".join(m.label for m in at.metric)
    assert "order_id" not in labels and "station_id" not in labels and "Average sales" in labels


def test_visualizations_page_friendly_message_when_x_equals_y():
    df = pd.DataFrame({"a": np.arange(10.0), "b": np.arange(10.0) * 2})
    at = make_app(df, page="Visualizations")
    at.selectbox(key="vis_group_x").set_value("a")
    at.selectbox(key="vis_metric_y").set_value("a")
    at.run()
    assert not at.exception and any("different column" in i.value for i in at.info)


def test_import_notes_render_user_text_literally():
    at = make_app()
    upload(at, csv_bytes("**bold**,v\n00123,1\n01234,2\n"), "c.csv")
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert r"\*\*bold\*\*" in text and "'**bold**'" not in text


# ---------------------------------------------------------------- shipped sample files x every page
SAMPLES = [("retail_sales_messy.csv", ","), ("weather_stations_numeric.csv", ","), ("employees_semicolon.csv", ";")]


@pytest.mark.parametrize("filename,sep", SAMPLES)
def test_every_page_renders_for_each_shipped_sample_file(filename, sep):
    from pathlib import Path

    from data.loader import load_dataset
    from tests.conftest import PAGES, named_buffer
    path = Path(__file__).resolve().parents[2] / "sample_data" / filename
    df = load_dataset(named_buffer(path.read_bytes(), filename))
    assert len(df) > 0
    for page in PAGES:
        at = make_app(df, filename, page=page)
        assert not at.exception, f"{filename} / {page}"
