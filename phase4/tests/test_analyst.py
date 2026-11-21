"""Ask Your Data engine: routing, answers, suggestions (IDs are never metrics)."""
import numpy as np
import pandas as pd
import pytest

from data.analyst import SUPPORTED_OPERATIONS, answer_question, automatic_insights, route_question, suggest_prompts
from data.intent import parse_chart_intent


@pytest.fixture(scope="module")
def sales():
    rng = np.random.default_rng(3)
    n = 90
    return pd.DataFrame({
        "order_id": range(5000, 5000 + n), "region": rng.choice(["North", "South", "East"], n),
        "channel": rng.choice(["web", "store"], n), "revenue": rng.uniform(10, 500, n).round(2),
        "units": rng.integers(1, 40, n), "day": pd.date_range("2024-01-01", periods=n),
    })


@pytest.fixture(scope="module")
def id_heavy():
    n = 60
    return pd.DataFrame({"order_id": range(1, n + 1), "customer_id": [f"C{i:04d}" for i in range(n)],
                         "station_id": range(100, 100 + n), "group": ["x", "y", "z"] * 20})


# ---------------------------------------------------------------- routing
@pytest.mark.parametrize("question,handler", [
    ("How many rows are there?", "row_count"), ("how many columns", "row_count"),
    ("Are there missing values?", "missing"), ("any duplicate rows", "duplicates"),
    ("Which columns are correlated?", "correlation"), ("unique values per column", "unique"),
    ("What are the column types?", "column_types"), ("What is the average revenue?", "column_stat"),
    ("total units", "column_stat"), ("How many records per region?", "value_counts"),
    ("show summary statistics", "summary"), ("Show top 3 region by revenue", "chart"),
    ("Show distribution of revenue", "chart"), ("Show revenue trend over day", "chart"),
    ("scatter plot of revenue vs units", "chart"),
])
def test_routing(sales, question, handler):
    assert route_question(question, sales).handler == handler


@pytest.mark.parametrize("question", ["tell me a joke", "", "   ", "what is the meaning of life"])
def test_unsupported_questions_route_nowhere_and_answer_honestly(sales, question):
    assert route_question(question, sales) is None
    answer = answer_question(question, sales)
    assert answer.handler == "unsupported" and answer.level in ("warning", "info")
    if question.strip():
        assert "no external AI" in answer.message


def test_column_stat_values_are_correct(sales):
    avg = answer_question("what is the average revenue", sales)
    assert f"{sales['revenue'].mean():,.2f}" in avg.message
    total = answer_question("total units", sales)
    assert f"{sales['units'].sum():,.2f}" in total.message
    assert f"{sales['units'].max():,.2f}" in answer_question("maximum units", sales).message


def test_value_counts_answer_matches_pandas(sales):
    ans = answer_question("how many records per region", sales)
    assert ans.table.set_index("region")["Records"].to_dict() == sales["region"].value_counts().to_dict()


def test_dataset_level_answers(sales):
    assert "90 rows" in answer_question("how many rows", sales).message
    assert "no missing" in answer_question("missing values?", sales).message
    with_nulls = sales.copy(); with_nulls.loc[0, "revenue"] = np.nan
    miss = answer_question("missing values", with_nulls)
    assert "1 missing" in miss.message and miss.bar_from_table
    assert answer_question("duplicates", pd.concat([sales, sales.head(2)])).message.count("2") >= 1
    assert answer_question("correlation", sales).table is not None
    types = answer_question("column types", sales).table.set_index("Column")["Used as"]
    assert types["order_id"] == "identifier" and types["revenue"] == "measure"


def test_empty_and_none_datasets():
    for empty in (None, pd.DataFrame(), pd.DataFrame({"a": []})):
        assert answer_question("how many rows", empty).level == "info"
        assert suggest_prompts(empty) == []
        assert route_question("how many rows", empty) is None
        assert automatic_insights(empty) == []


# ---------------------------------------------------------------- IDs are not metrics
def test_default_chart_metric_is_a_measure_not_the_first_numeric_id(sales):
    intent = parse_chart_intent("show top 5 region", sales)
    assert intent["y"] == "revenue"


def test_naming_an_id_column_explicitly_is_still_honoured(sales):
    assert parse_chart_intent("show top 5 region by order_id", sales)["y"] == "order_id"


def test_suggestions_never_use_identifier_columns(sales, id_heavy):
    for text in suggest_prompts(sales, limit=10):
        assert "order_id" not in text
    for text in suggest_prompts(id_heavy, limit=10):
        assert "_id" not in text.replace("column types", "")


def test_every_suggestion_is_answerable_with_a_meaningful_result(sales, id_heavy):
    frames = [sales, id_heavy, sales.assign(revenue=np.nan),
              pd.read_csv("../sample_data/retail_sales_messy.csv"),
              pd.read_csv("../sample_data/weather_stations_numeric.csv"),
              pd.read_csv("../sample_data/employees_semicolon.csv", sep=";")]
    for frame in frames:
        suggestions = suggest_prompts(frame, limit=10)
        assert suggestions, "every dataset should get at least a few suggestions"
        for text in suggestions:
            answer = answer_question(text, frame)
            assert answer.handler != "unsupported", text
            assert answer.message and (answer.table is not None or answer.chart_intent or len(answer.message) > 10)


def test_id_heavy_dataset_still_gets_useful_non_metric_suggestions(id_heavy):
    suggestions = suggest_prompts(id_heavy)
    assert "How many records per group?" in suggestions
    assert any("column types" in s.lower() for s in suggestions)
    assert not any(s.startswith("Show top") for s in suggestions)


def test_suggestions_adapt_to_the_schema(sales):
    suggestions = suggest_prompts(sales, limit=10)
    assert "Show top 10 region by revenue" in suggestions       # first category, best measure
    assert "Show revenue trend over day" in suggestions
    assert any("scatter" in s for s in suggestions)
    assert len(suggest_prompts(sales, limit=3)) == 3
    assert not any("trend" in s for s in suggest_prompts(sales.drop(columns="day"), limit=10))


def test_duplicate_and_missing_prompts_appear_only_when_relevant(sales):
    assert "Are there duplicate rows?" not in suggest_prompts(sales, limit=10)
    assert "Are there duplicate rows?" in suggest_prompts(pd.concat([sales, sales.head(1)]), limit=10)
    assert "Are there missing values?" not in suggest_prompts(sales, limit=10)


def test_automatic_insights_ignore_identifier_columns(id_heavy, sales):
    text = " ".join(automatic_insights(id_heavy))
    assert "order_id" not in text and "station_id" not in text
    assert any("Strongest numeric correlation" in f for f in automatic_insights(sales))


def test_supported_operations_documentation_matches_router(sales):
    from data.analyst import _HANDLERS
    assert {name for name, _, _ in SUPPORTED_OPERATIONS} == set(_HANDLERS)
