"""Tests for data/intent.py (rule-based chart prompts)."""
import pandas as pd
import pytest

from data.intent import build_chart_data, parse_chart_intent


@pytest.fixture()
def sales():
    return pd.DataFrame({
        "region": ["A", "B", "A", "B", "C", "C"], "sales": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        "profit": [1, 1, 2, 2, 3, 3], "d": pd.date_range("2024-01-01", periods=6),
    })


def _shape(i):
    return None if i is None else (i["chart_type"], i["x"], i["y"], i.get("agg"))


@pytest.mark.parametrize("question,expected", [
    ("show top 5 region by sales", ("Bar Chart", "region", "sales", "sum")),
    ("average sales by region", ("Bar Chart", "region", "sales", "mean")),
    ("count of sales by region", ("Bar Chart", "region", "sales", "count")),
    ("sales trend over date", ("Line Chart", "d", "sales", "sum")),
    ("monthly average sales", ("Line Chart", "d", "sales", "mean")),
    ("distribution of profit", ("Histogram", "profit", None, None)),
    ("scatter of sales vs profit", ("Scatter Plot", "sales", "profit", None)),
    ("tell me a joke", None), ("show pie chart of region", None), ("", None),
])
def test_supported_and_unsupported_prompts(sales, question, expected):
    assert _shape(parse_chart_intent(question, sales)) == expected


def test_bottom_and_limits(sales):
    low = parse_chart_intent("show bottom 3 region by sales", sales)
    assert low["ascending"] is True and low["limit"] == 3 and "Bottom 3" in low["title"]
    assert parse_chart_intent("top 0 region by sales", sales)["limit"] == 1
    assert parse_chart_intent("top 999 region by sales", sales)["limit"] == 50
    assert parse_chart_intent("top region by sales", sales)["limit"] == 10
    assert parse_chart_intent("lowest region by sales", sales)["ascending"] is True


def test_empty_or_missing_data_gives_no_intent():
    assert parse_chart_intent("top 5 by x", None) is None
    assert parse_chart_intent("top 5 by x", pd.DataFrame()) is None


# --- regression: single-letter column names used to match inside unrelated words
def test_short_column_names_do_not_match_inside_other_words():
    df = pd.DataFrame({"a": [1, 2, 3, 4], "sales": [10, 20, 30, 40], "region": list("wxyz")})
    intent = parse_chart_intent("show top 3 region by sales", df)
    assert intent["y"] == "sales", "column 'a' must not be selected just because 'a' occurs in 'sales'"


def test_keywords_match_whole_words_only():
    df = pd.DataFrame({"weight": [1.0, 2.0, 3.0], "kind": list("abc")})
    # 'by' occurs inside 'baby' but is not the word 'by' -> this is a distribution request
    assert parse_chart_intent("distribution of baby weight", df)["chart_type"] == "Histogram"


def test_column_names_with_regex_characters_are_safe():
    df = pd.DataFrame({"price ($)": [1.0, 2.0], "grp": ["a", "b"]})
    assert parse_chart_intent("top grp by price ($)", df)["y"] == "price ($)"


# ----------------------------------------------------------------- chart data
def test_bar_data_matches_independent_aggregation(sales):
    intent = parse_chart_intent("average sales by region", sales)
    data, col = build_chart_data(sales, intent)
    expected = sales.groupby("region")["sales"].mean().sort_values(ascending=False)
    assert col == "sales" and dict(zip(data["region"], data["sales"])) == pytest.approx(expected.to_dict())
    assert list(data["sales"]) == sorted(data["sales"], reverse=True)


def test_bar_data_respects_limit_and_ascending(sales):
    data, _ = build_chart_data(sales, parse_chart_intent("bottom 2 region by sales", sales))
    assert list(data["region"]) == ["A", "B"] and len(data) == 2


@pytest.mark.parametrize("agg,expected", [("sum", [4.0, 6.0, 11.0]), ("mean", [2.0, 3.0, 5.5]), ("count", [2, 2, 2])])
def test_line_data_supports_sum_mean_and_count(agg, expected):
    df = pd.DataFrame({"d": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-02", "2024-01-03", "2024-01-03"]),
                       "v": [1.0, 3.0, 2.0, 4.0, 5.0, 6.0]})
    intent = {"chart_type": "Line Chart", "x": "d", "y": "v", "agg": agg, "title": "t"}
    data, col = build_chart_data(df, intent)
    assert list(data[col]) == expected and data["d"].is_monotonic_increasing


def test_same_column_for_x_and_y_does_not_crash(sales):
    for chart in ("Bar Chart", "Line Chart"):
        data, col = build_chart_data(sales, {"chart_type": chart, "x": "profit", "y": "profit", "agg": "count"})
        assert col == "profit (count)" and col in data.columns and "profit" in data.columns


def test_unknown_aggregation_falls_back_to_sum(sales):
    data, _ = build_chart_data(sales, {"chart_type": "Bar Chart", "x": "region", "y": "sales", "agg": "nonsense"})
    assert data["sales"].sum() == pytest.approx(sales["sales"].sum())


def test_histogram_intent_has_no_chart_data(sales):
    with pytest.raises(ValueError):
        build_chart_data(sales, parse_chart_intent("distribution of profit", sales))
