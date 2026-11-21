"""Chart builder tests: every chart type x column kind x option, plus edge datasets.

The invariant tested over the full matrix: a configuration either produces a
Plotly figure or a ChartConfigError whose message is non-empty and user-safe;
nothing else may escape. A hand-written table pins down the expected outcome of
the combinations users hit most.
"""
import itertools

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from data.aggregation import AGGREGATION_LABELS
from data.charts import (
    CHART_SPECS,
    CHART_TYPES,
    MAX_COLOR_GROUPS,
    ChartConfigError,
    build_chart,
    build_trend_chart,
    safe_build_chart,
    trend_frame,
)


@pytest.fixture(scope="module")
def rich() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    n = 80
    return pd.DataFrame({
        "region": rng.choice(["North", "South", "East", "West"], n),
        "product": rng.choice(["Widget", "Gadget", "Gizmo"], n),
        "city": [f"city_{i % 50}" for i in range(n)],            # 50 values: too many to colour by
        "sales": rng.gamma(2.0, 500.0, n).round(2),
        "units": rng.integers(1, 60, n),
        "day": pd.date_range("2024-01-01", periods=n, freq="D"),
        "day_text": [d.strftime("%Y-%m-%d") for d in pd.date_range("2024-01-01", periods=n, freq="D")],
        "flag": rng.choice([True, False], n),
    })


COLUMNS = ["region", "product", "city", "sales", "units", "day", "day_text", "flag"]
AGG_TYPES = ["Bar Chart", "Line Chart", "Area Chart"]


def _outcome(df, chart_type, **kw):
    try:
        fig = build_chart(df, chart_type, **kw)
    except ChartConfigError as exc:
        assert str(exc).strip(), "validation messages must not be empty"
        return "message"
    assert isinstance(fig, go.Figure) and len(fig.data) >= 1
    return "figure"


# --------------------------------------------------------------------------- full matrix
@pytest.mark.parametrize("chart_type", AGG_TYPES)
@pytest.mark.parametrize("agg", AGGREGATION_LABELS)
def test_aggregated_charts_x_y_agg_matrix(rich, chart_type, agg):
    for x, y in itertools.product(["region", "city", "day", "day_text", "units", "flag"], ["sales", "units", "region", "day"]):
        _outcome(rich, chart_type, x=x, y=y, agg=agg)


@pytest.mark.parametrize("chart_type", AGG_TYPES)
@pytest.mark.parametrize("color", [None, "region", "product", "city", "sales", "flag"])
def test_aggregated_charts_color_matrix(rich, chart_type, color):
    for x in ["region", "product", "day", "units", "day_text"]:
        _outcome(rich, chart_type, x=x, y="sales", color=color, agg="Sum")


@pytest.mark.parametrize("chart_type", ["Scatter Plot", "Histogram", "Box Plot", "Violin Plot"])
@pytest.mark.parametrize("color", [None, "region", "city"])
def test_other_charts_x_y_color_matrix(rich, chart_type, color):
    for x, y in itertools.product([None, "region", "city", "sales", "day"], ["sales", "region", "units"]):
        _outcome(rich, chart_type, x=x, y=y, color=color)


@pytest.mark.parametrize("chart_type", ["Pie Chart", "Donut Chart"])
def test_pie_matrix(rich, chart_type):
    for x, y, agg in itertools.product(["region", "flag", "day"], [None, "sales", "region"], AGGREGATION_LABELS):
        _outcome(rich, chart_type, x=x, y=y, agg=agg)


def test_heatmap_with_and_without_columns(rich):
    assert _outcome(rich, "Heatmap") == "figure"
    assert _outcome(rich, "Heatmap", columns=["sales", "units"]) == "figure"
    assert _outcome(rich, "Heatmap", columns=["sales"]) == "message"
    assert _outcome(rich, "Heatmap", columns=["region", "product"]) == "message"


@pytest.mark.parametrize("chart_type", CHART_TYPES)
def test_safe_build_never_raises_on_garbage(rich, chart_type):
    for kw in [{}, {"x": "nope", "y": "nope2"}, {"x": None, "y": 5}, {"x": "(None)", "y": "(None)"},
               {"x": "region", "y": "sales", "color": "missing"}, {"x": "region", "y": "sales", "agg": "bogus"}]:
        fig, msg = safe_build_chart(rich, chart_type, **kw)
        assert (fig is None) != (msg is None)


# --------------------------------------------------------------------------- expected outcomes
EXPECTED = [
    # chart,            x,        y,       color,    agg,      result
    ("Bar Chart",       "region", "sales", None,     "Sum",    "figure"),
    ("Bar Chart",       "region", "sales", "product", "Average", "figure"),    # the original regression
    ("Bar Chart",       "product", "sales", "region", "Sum",    "figure"),
    ("Bar Chart",       "day",    "sales", None,     "Sum",    "figure"),
    ("Bar Chart",       "day_text", "sales", None,   "Sum",    "figure"),
    ("Bar Chart",       "units",  "sales", None,     "Sum",    "figure"),
    ("Bar Chart",       "region", "region", None,    "Count",  "figure"),      # Count works on any column
    ("Bar Chart",       "region", "region", None,    "Sum",    "message"),
    ("Bar Chart",       "region", "product", None,   "Sum",    "message"),      # text Y cannot be summed
    ("Bar Chart",       "region", "sales", "city",   "Sum",    "message"),      # 50 colour groups
    ("Bar Chart",       None,     "sales", None,     "Sum",    "message"),
    ("Line Chart",      "day",    "sales", "region", "Average", "figure"),
    ("Area Chart",      "day",    "sales", None,     "Median", "figure"),
    ("Scatter Plot",    "units",  "sales", "region", "Sum",    "figure"),
    ("Scatter Plot",    "sales",  "sales", None,     "Sum",    "message"),
    ("Scatter Plot",    "units",  "region", None,    "Sum",    "message"),
    ("Histogram",       None,     "sales", "region", "Sum",    "figure"),
    ("Histogram",       None,     "region", None,    "Sum",    "message"),
    ("Box Plot",        "region", "sales", "product", "Sum",   "figure"),
    ("Box Plot",        "city",   "sales", None,     "Sum",    "message"),      # 50 boxes
    ("Violin Plot",     "region", "sales", None,     "Sum",    "figure"),
    ("Pie Chart",       "region", None,    None,     "Sum",    "figure"),       # counts rows
    ("Pie Chart",       "region", "sales", None,     "Sum",    "figure"),
    ("Donut Chart",     "product", "sales", None,    "Average", "figure"),
    ("Pie Chart",       None,     "sales", None,     "Sum",    "message"),
    ("Heatmap",         None,     None,    None,     "Sum",    "figure"),
]


@pytest.mark.parametrize("chart,x,y,color,agg,expected", EXPECTED)
def test_expected_outcomes(rich, chart, x, y, color, agg, expected):
    assert _outcome(rich, chart, x=x, y=y, color=color, agg=agg) == expected


def test_every_chart_type_has_a_spec_and_is_covered():
    assert set(CHART_SPECS) == set(CHART_TYPES)
    assert {row[0] for row in EXPECTED} == set(CHART_TYPES)


def test_chart_type_matching_is_case_insensitive(rich):
    assert isinstance(build_chart(rich, "bar chart", x="region", y="sales"), go.Figure)
    with pytest.raises(ChartConfigError):
        build_chart(rich, "3D Hologram", x="region", y="sales")


# --------------------------------------------------------------------------- correctness of what is drawn
def test_regression_bar_with_categorical_x_and_different_color_keeps_the_color_column(rich):
    fig = build_chart(rich, "Bar Chart", x="region", y="sales", color="product", agg="Sum")
    assert {t.name for t in fig.data} == set(rich["product"].unique())


def test_bar_values_equal_the_pandas_groupby(rich):
    fig = build_chart(rich, "Bar Chart", x="region", y="sales", agg="Sum")
    expected = rich.groupby("region")["sales"].sum()
    drawn = dict(zip(fig.data[0].x, fig.data[0].y))
    for region, total in expected.items():
        assert drawn[region] == pytest.approx(total)


def test_changing_aggregation_changes_the_drawn_values(rich):
    total = build_chart(rich, "Bar Chart", x="region", y="sales", agg="Sum").data[0].y
    mean = build_chart(rich, "Bar Chart", x="region", y="sales", agg="Average").data[0].y
    assert sorted(total) != sorted(mean)
    counts = build_chart(rich, "Bar Chart", x="region", y="sales", agg="Count").data[0].y
    assert sum(counts) == len(rich)


def test_color_option_changes_the_number_of_traces(rich):
    plain = build_chart(rich, "Scatter Plot", x="units", y="sales")
    coloured = build_chart(rich, "Scatter Plot", x="units", y="sales", color="region")
    assert len(plain.data) == 1 and len(coloured.data) == 4


def test_changing_chart_type_changes_the_trace_type(rich):
    kinds = {t: build_chart(rich, t, x="region", y="sales", agg="Sum").data[0].type
             for t in ["Bar Chart", "Line Chart", "Area Chart", "Pie Chart"]}
    assert kinds == {"Bar Chart": "bar", "Line Chart": "scatter", "Area Chart": "scatter", "Pie Chart": "pie"}
    assert build_chart(rich, "Donut Chart", x="region", y="sales").data[0].hole == pytest.approx(0.48)


def test_top_n_limits_categories_and_keeps_the_largest(rich):
    fig = build_chart(rich, "Bar Chart", x="city", y="sales", agg="Sum", top_n=5)
    assert len(fig.data[0].x) == 5
    totals = rich.groupby("city")["sales"].sum().nlargest(5)
    assert set(fig.data[0].x) == set(totals.index)


def test_grouped_color_bars_use_group_mode_and_respect_top_n(rich):
    fig = build_chart(rich, "Bar Chart", x="city", y="sales", color="region", agg="Sum", top_n=4)
    assert fig.layout.barmode == "group"
    assert len({x for t in fig.data for x in t.x}) == 4


def test_missing_category_values_are_labelled_not_dropped():
    df = pd.DataFrame({"g": ["a", None, "a", None], "v": [1.0, 2.0, 3.0, 4.0]})
    fig = build_chart(df, "Bar Chart", x="g", y="v", agg="Sum")
    assert dict(zip(fig.data[0].x, fig.data[0].y)) == {"a": 4.0, "(missing)": 6.0}


def test_date_x_is_aggregated_per_date_and_sorted():
    df = pd.DataFrame({"d": pd.to_datetime(["2024-01-02", "2024-01-01", "2024-01-02"]), "v": [1, 2, 3]})
    fig = build_chart(df, "Line Chart", x="d", y="v", agg="Sum")
    assert list(fig.data[0].y) == [2, 4]


# --------------------------------------------------------------------------- edge datasets
def _frame(name):
    n = 30
    base = {"cat": list("ab") * (n // 2), "val": np.arange(n, dtype=float)}
    if name == "empty":
        return pd.DataFrame({"cat": [], "val": []})
    if name == "no_columns":
        return pd.DataFrame()
    if name == "all_null_y":
        return pd.DataFrame({**base, "val": [np.nan] * n})
    if name == "constant_y":
        return pd.DataFrame({**base, "val": [5.0] * n})
    if name == "inf_y":
        vals = np.arange(n, dtype=float); vals[::5] = np.inf; vals[1::7] = -np.inf
        return pd.DataFrame({**base, "val": vals})
    if name == "mixed_y":
        return pd.DataFrame({**base, "val": ["1", "2", "three", None] * 7 + ["5", "6"]})
    if name == "high_cardinality":
        return pd.DataFrame({"cat": [f"k{i}" for i in range(n)], "val": np.arange(n, dtype=float)})
    if name == "single_row":
        return pd.DataFrame({"cat": ["a"], "val": [1.0]})
    raise KeyError(name)


EDGE = ["empty", "no_columns", "all_null_y", "constant_y", "inf_y", "mixed_y", "high_cardinality", "single_row"]


@pytest.mark.parametrize("name", EDGE)
@pytest.mark.parametrize("chart_type", CHART_TYPES)
def test_edge_datasets_never_crash(name, chart_type):
    df = _frame(name)
    for kw in [dict(x="cat", y="val", agg="Sum"), dict(x="cat", y="val", color="cat"), dict(y="val"), dict(x="val", y="val")]:
        fig, msg = safe_build_chart(df, chart_type, **kw)
        assert (fig is None) != (msg is None)


@pytest.mark.parametrize("name,expected", [("empty", "message"), ("no_columns", "message"), ("all_null_y", "message"),
                                           ("constant_y", "figure"), ("inf_y", "figure"), ("single_row", "figure")])
def test_edge_dataset_bar_outcomes(name, expected):
    assert _outcome(_frame(name), "Bar Chart", x="cat", y="val", agg="Sum") == expected


def test_infinite_values_never_reach_the_figure():
    fig = build_chart(_frame("inf_y"), "Histogram", y="val")
    xs = np.asarray(fig.data[0].x, dtype=float)
    assert np.isfinite(xs[~np.isnan(xs)]).all()



def test_color_with_too_many_groups_is_refused_with_a_clear_message():
    df = pd.DataFrame({"cat": [f"k{i}" for i in range(MAX_COLOR_GROUPS + 10)], "val": 1.0, "n": 2.0})
    with pytest.raises(ChartConfigError, match=str(MAX_COLOR_GROUPS)):
        build_chart(df, "Scatter Plot", x="n", y="val", color="cat")


def test_messages_do_not_leak_internals(rich):
    for chart_type in CHART_TYPES:
        for kw in [dict(x="region", y="region", agg="Sum"), dict(x="nope", y="sales"), dict(x="city", y="sales", color="city")]:
            _, msg = safe_build_chart(rich, chart_type, **kw)
            if msg:
                assert "Traceback" not in msg and "/home/" not in msg and "File \"" not in msg


# --------------------------------------------------------------------------- trend helpers
def test_trend_frame_grains_and_aggregations():
    df = pd.DataFrame({"d": pd.date_range("2024-01-01", periods=60, freq="D"), "v": 1.0})
    monthly = trend_frame(df, "d", "v", "Sum", "Monthly")
    assert list(monthly["v"]) == [31.0, 29.0]
    assert len(trend_frame(df, "d", "v", "Average", "Weekly")) >= 8
    assert trend_frame(df, "d", "v", "Count", "Daily")["v"].sum() == 60


def test_trend_with_no_valid_dates_is_empty_and_chart_raises_friendly_error():
    df = pd.DataFrame({"d": ["x", "y"], "v": [1, 2]})
    assert trend_frame(df, "d", "v", "Sum", "Daily").empty
    with pytest.raises(ChartConfigError):
        build_trend_chart(df, "d", "v", "Sum", "Daily")
    with pytest.raises(ChartConfigError):
        trend_frame(df, "d", "v", "Sum", "Hourly")


def test_text_numbers_are_coerced_for_numeric_axes():
    df = pd.DataFrame({"g": ["a", "a", "b"], "v": ["1", "2", "oops"]})
    fig = build_chart(df, "Bar Chart", x="g", y="v", agg="Sum")
    assert dict(zip(fig.data[0].x, fig.data[0].y))["a"] == 3.0
