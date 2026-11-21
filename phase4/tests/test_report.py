"""Tests for data/report.py: the downloadable HTML report must escape user text."""
import re

import pandas as pd
import pytest

from data.report import generate_html_report, insight_to_html

PAYLOAD = "<script>alert('x')</script>"


@pytest.fixture()
def frame():
    return pd.DataFrame({"a": [1, 2, 3, 4, 5, 6], "b": [3, 4, 5, 6, 7, 99]})


def test_dataset_name_is_escaped(frame):
    html = generate_html_report(frame, PAYLOAD + ".csv")
    assert PAYLOAD not in html and "&lt;script&gt;" in html


def test_column_names_and_cell_values_are_escaped():
    df = pd.DataFrame({"<b onmouseover=1>": [1, 2, 3, 4, 5, 6], "cat": ["<i>X</i>"] * 6, "n": [1, 2, 3, 4, 5, 60]})
    html = generate_html_report(df, "ok.csv")
    assert "<b onmouseover=1>" not in html and "<i>X</i>" not in html


def test_bold_markers_become_balanced_tags(frame):
    html = generate_html_report(frame, "ok.csv")
    items = re.findall(r"<li>(.*?)</li>", html)
    assert items
    for item in items:
        assert item.count("<b>") == item.count("</b>"), item
    assert "**" not in html


def test_report_contains_the_key_numbers(frame):
    html = generate_html_report(frame, "my data.csv")
    assert "my data.csv" in html and ">6<" in html            # 6 rows
    assert "Health Score" in html and "Summary Statistics" in html
    assert html.count("<html") == 1 and html.rstrip().endswith("</html>")


def test_report_handles_data_without_numeric_columns_and_empty_frames():
    assert "Summary Statistics" in generate_html_report(pd.DataFrame({"t": ["a", "b"]}), "t.csv")
    assert "<html" in generate_html_report(pd.DataFrame(), "empty.csv")


def test_insight_to_html_escapes_before_converting_bold():
    assert insight_to_html("**a<b>** is high") == "<b>a&lt;b&gt;</b> is high"
    assert insight_to_html("no markup & <x>") == "no markup &amp; &lt;x&gt;"
    assert insight_to_html(None) == "None" and insight_to_html("**unclosed") == "**unclosed"
