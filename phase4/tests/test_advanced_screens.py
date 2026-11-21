"""Stage 4: Ask Your Data, Dataset Comparison and Export & Reporting (presentation only; backends unchanged)."""

import re

import numpy as np
import pandas as pd
import pytest

import views.export as export_view
from tests.conftest import csv_bytes, make_app, upload
from tests.test_core_screens import _Balance
from views.analyst import _markup

ADV_PAGES = ["Ask Your Data", "Dataset Comparison", "Export & Reporting"]
EVIL = "<script>alert(1)</script>"

# Words that would claim abilities this rule-based app does not have (see Stage 4 brief).
FORBIDDEN = ["llm", "autonomous", "hallucination", "100%", "language model is", "openai", "gpt", "pdf", "colab", "dax ", "m-query",
             "digital signature", "iso ", "batch export", "asset gallery", "zero telemetry"]


@pytest.fixture(scope="module")
def sales():
    rng = np.random.default_rng(3)
    n = 80
    df = pd.DataFrame({
        "order_id": range(1, n + 1), "region": rng.choice(["N", "S", "E"], n), "sales": rng.uniform(1, 99, n).round(2),
        "when": pd.date_range("2024-01-01", periods=n, freq="D"),
    })
    df.loc[::10, "sales"] = np.nan
    return df


def _page_text(at) -> str:
    parts = [m.value for m in at.markdown if not m.value.lstrip().startswith("<style>")] + [c.value for c in at.caption] + [i.value for i in at.info] + [w.value for w in at.warning]
    parts += [s.value for s in at.success] + [e.value for e in at.error]
    return "\n".join(parts).lower()


def _downloads(at):
    return [el.proto for el in at.get("download_button")]


# ------------------------------------------------------------------ all three pages
@pytest.mark.parametrize("page", ADV_PAGES)
@pytest.mark.parametrize("variant", ["sales", "empty", "categorical", "single_row"])
def test_pages_render_for_normal_and_awkward_data(page, variant, sales):
    frames = {"sales": sales, "empty": pd.DataFrame({"a": pd.Series(dtype=float)}),
              "categorical": pd.DataFrame({"a": list("xyxz") * 5, "b": list("pq") * 10}), "single_row": pd.DataFrame({"a": ["x"], "n": [1.5]})}
    at = make_app(frames[variant], "d.csv", page=page)
    assert not at.exception, f"{page}/{variant}: {at.exception}"


@pytest.mark.parametrize("page", ADV_PAGES)
def test_pages_make_no_unsupported_claims(page, sales):
    text = _page_text(make_app(sales, "d.csv", page=page))
    for word in FORBIDDEN:
        assert word not in text, f"{page} mentions {word!r}"


@pytest.mark.parametrize("page", ADV_PAGES)
def test_generated_html_is_balanced_and_pages_do_not_mutate_data(page, sales):
    at = make_app(sales, "d.csv", page=page)
    pd.testing.assert_frame_equal(at.session_state["df"], sales)
    for md in at.markdown:
        if "<div" in md.value or "<span" in md.value:
            check = _Balance()
            check.parser.feed(md.value)
            assert not check.errors and not check.stack, f"{page}: {check.errors or check.stack} in {md.value[:90]!r}"


# ------------------------------------------------------------------ Ask Your Data
def test_ask_page_keeps_rule_based_statement_and_shows_glance_metrics(sales):
    at = make_app(sales, "d.csv", page="Ask Your Data")
    captions = " ".join(c.value for c in at.caption)
    assert "not an AI model" in captions and "no API key" in captions
    m = {x.label: x.value for x in at.metric}
    assert m["Rows"] == "80" and m["Columns"] == "4" and m["Missing cells"] == "8" and m["Duplicate rows"] == "0"
    assert any("insight" in x.value.lower() for x in at.markdown)


def test_ask_page_empty_state_then_typed_question_shows_answer_card(sales):
    at = make_app(sales, "d.csv", page="Ask Your Data")
    assert any("will appear here" in m.value for m in at.markdown)
    at.text_input(key="ai_query_input").set_value("how many rows are there")
    at.run()
    assert not at.exception
    text = "\n".join(m.value for m in at.markdown)
    assert "Matched rule: Count rows and columns" in text and "80" in "\n".join(s.value for s in [*at.success, *at.info])
    assert not any("will appear here" in m.value for m in at.markdown)


def test_ask_page_suggestion_click_fills_input_and_answers(sales):
    at = make_app(sales, "d.csv", page="Ask Your Data")
    buttons = [b for b in at.button if b.key and b.key.startswith("sug_btn_")]
    assert buttons
    first = buttons[0].label
    at.button(key="sug_btn_0").click().run()
    assert not at.exception and at.text_input(key="ai_query_input").value == first
    assert any("Matched rule" in m.value for m in at.markdown)


def test_ask_page_unsupported_question_is_declined_without_chart_or_badge(sales):
    at = make_app(sales, "d.csv", page="Ask Your Data")
    at.text_input(key="ai_query_input").set_value("tell me a joke")
    at.run()
    assert not at.exception and len(at.get("plotly_chart")) == 0
    assert any("couldn't confidently" in w.value for w in at.warning)
    assert not any("Matched rule" in m.value for m in at.markdown)


def test_ask_page_chart_question_draws_a_chart(sales):
    at = make_app(sales, "d.csv", page="Ask Your Data")
    at.text_input(key="ai_query_input").set_value("show top 3 region by sales")
    at.run()
    assert not at.exception and len(at.get("plotly_chart")) >= 1


def test_ask_page_escapes_user_text_everywhere():
    df = pd.DataFrame({EVIL: [1.0, 2.0, 3.0, 4.0] * 5, "grp": list("abab") * 5, "v": range(20)})
    at = make_app(df, "d.csv", page="Ask Your Data")
    at.text_input(key="ai_query_input").set_value(f"average {EVIL}")
    at.run()
    assert not at.exception
    for md in at.markdown:
        assert "<script" not in md.value, md.value[:120]
    assert "<script" not in _markup(EVIL)


def test_markup_converts_bold_and_code_after_escaping():
    assert _markup("**Missing:** `a<b` has 3") == "<b>Missing:</b> <code>a&lt;b</code> has 3"


def test_ask_page_guide_lists_every_supported_operation_and_roles(sales):
    from data.analyst import SUPPORTED_OPERATIONS

    at = make_app(sales, "d.csv", page="Ask Your Data")
    text = "\n".join(m.value for m in at.markdown)
    for _, description, _ in SUPPORTED_OPERATIONS:
        assert description in text
    assert "order_id · identifier" in text and "sales · measure" in text


def test_ask_page_keeps_widget_keys(sales):
    at = make_app(sales, "d.csv", page="Ask Your Data")
    assert at.text_input(key="ai_query_input") is not None
    assert {b.key for b in at.button if b.key} >= {"sug_btn_0"}


# ------------------------------------------------------------------ Dataset Comparison
def _compare(sales, content: bytes, name="o.csv"):
    at = make_app(sales, "sales.csv", page="Dataset Comparison")
    upload(at, content, name, widget=at.get("file_uploader")[0])
    return at


def test_comparison_without_second_file_shows_upload_card_and_hint(sales):
    at = make_app(sales, "sales.csv", page="Dataset Comparison")
    assert at.get("file_uploader")[0].key == "second_dataset_file"
    assert any("Upload a second dataset above" in i.value for i in at.info) and len(at.metric) == 0


def test_comparison_metrics_and_difference_badges(sales):
    other = "region,sales\nN,\nS,\nE,5\n"  # 3 rows, 2 cols, 2 missing
    at = _compare(sales, csv_bytes(other))
    assert not at.exception
    labels = [(m.label, m.value, m.delta) for m in at.metric]
    assert ("Rows", "80", "") in labels and ("Rows", "3", str(3 - 80)) in labels
    text = "\n".join(m.value for m in at.markdown)
    assert "Rows -77" in text and "Columns -2" in text
    assert "Missing cells" in text  # tone follows the sign of the change: see test_comparison_missing_cells_tone_follows_direction


def test_comparison_missing_cells_tone_follows_direction():
    base = pd.DataFrame({"a": [1, 2, 3, 4], "b": [1, 2, 3, 4]})
    more_missing = _compare(base, csv_bytes("a,b\n1,\n,\n3,4\n,\n"))
    text = "\n".join(m.value for m in more_missing.markdown)
    assert re.search(r"ap-badge-danger[^>]*>Missing cells \+", text)
    fewer = make_app(pd.DataFrame({"a": [1, None, 3, None], "b": [1, 2, None, 4]}), "m.csv", page="Dataset Comparison")
    upload(fewer, csv_bytes("a,b\n1,2\n3,4\n"), "o.csv", widget=fewer.get("file_uploader")[0])
    text = "\n".join(m.value for m in fewer.markdown)
    assert re.search(r"ap-badge-success[^>]*>Missing cells -", text)


def test_comparison_common_columns_and_no_overlap_warning(sales):
    at = _compare(sales, csv_bytes("region,sales,zzz\nx,1,2\n"))
    assert any("Common Columns (2)" in m.value for m in at.markdown) and any(m.value == "`region`, `sales`" for m in at.markdown)
    none = _compare(sales, csv_bytes("p,q\n1,2\n"))
    assert any("No overlapping column names" in w.value for w in none.warning)


def test_comparison_invalid_file_shows_friendly_error(sales):
    at = _compare(sales, b"\x00\x01\x02 not a spreadsheet", "broken.xlsx")
    assert not at.exception and at.error
    assert not any("Traceback" in e.value for e in at.error)


def test_comparison_escapes_file_names(sales):
    at = _compare(sales, csv_bytes("region,sales\nx,1\n"), name="<b>evil</b>.csv")
    assert not at.exception
    joined = "\n".join(m.value for m in at.markdown)
    assert "<b>evil</b>" not in joined and "&lt;b&gt;evil&lt;/b&gt;" in joined


def test_comparison_does_not_replace_the_active_dataset(sales):
    at = _compare(sales, csv_bytes("region,sales\nx,1\n"))
    pd.testing.assert_frame_equal(at.session_state["df"], sales)


# ------------------------------------------------------------------ Export & Reporting
EXPECTED_DOWNLOADS = [
    "📄 Download Executive Report (HTML)", "⬇️ Download Current Processed Dataset (CSV)", "📋 Download Full Column Data Profile (CSV)",
    "📗 Download Excel Workbook", "📊 Download Power BI Starter Pack", "🐍 Download cleaning script (.py)",
]


def test_export_page_has_exactly_the_existing_downloads(sales):
    at = make_app(sales, "d.csv", page="Export & Reporting")
    assert not at.exception
    assert [d.label for d in _downloads(at)] == EXPECTED_DOWNLOADS


def test_export_page_only_the_report_is_primary(sales):
    at = make_app(sales, "d.csv", page="Export & Reporting")
    kinds = {d.label: d.type for d in _downloads(at)}
    assert kinds[EXPECTED_DOWNLOADS[0]] == "primary"
    assert all(v != "primary" for k, v in kinds.items() if k != EXPECTED_DOWNLOADS[0])


def test_export_render_does_not_build_the_files(monkeypatch, sales):
    calls = []
    for name in ("generate_html_report", "dataframe_to_csv_bytes", "dataframe_to_powerbi_workbook_bytes", "powerbi_starter_pack_bytes"):
        real = getattr(export_view, name)
        monkeypatch.setattr(export_view, name, lambda *a, _n=name, _r=real, **k: (calls.append(_n), _r(*a, **k))[1])
    at = make_app(sales, "d.csv", page="Export & Reporting")
    assert not at.exception and calls == [], "downloads must stay deferred (built only when clicked)"


def test_export_page_states_power_bi_is_not_pbix_and_has_no_extra_features(sales):
    at = make_app(sales, "d.csv", page="Export & Reporting")
    text = "\n".join(m.value for m in at.markdown)
    assert "not a native .pbix file" in text
    assert text.lower().count("pbix") >= 1


def test_export_script_section_counts_steps_and_warns_about_unexportable_actions(sales):
    at = make_app(sales, "d.csv", page="Export & Reporting")
    at.session_state["cleaning_history"] = [
        {"time": "t", "action": "Dropped duplicate rows", "step": {"op": "remove_duplicates", "action": "Keep first occurrence"}},
        {"time": "t", "action": "Hand edit with no structured step"},
    ]
    at.run()
    assert not at.exception
    assert any("1 cleaning step(s) included" in c.value for c in at.caption)
    assert any("Hand edit with no structured step" in w.value for w in at.warning)
    assert [e.label for e in at.expander] == ["Preview the script"]


def test_export_without_openpyxl_shows_install_warning(monkeypatch, sales):
    monkeypatch.setattr(export_view, "excel_export_available", lambda: False)
    at = make_app(sales, "d.csv", page="Export & Reporting")
    assert any("requires openpyxl" in w.value for w in at.warning)
    assert "📗 Download Excel Workbook" not in [d.label for d in _downloads(at)]


def test_export_names_and_badges_are_escaped():
    df = pd.DataFrame({"a": [1, 2]})
    at = make_app(df, EVIL + ".csv", page="Export & Reporting")
    assert not at.exception
    assert all("<script" not in m.value for m in at.markdown)
