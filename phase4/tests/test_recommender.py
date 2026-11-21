"""Tests for data/recommender.py: structural invariants (ported from the old
script test) plus independently computed values for every compute_* helper."""
import numpy as np
import pandas as pd
import pytest

from data.recommender import (
    compute_category_aggregation,
    compute_correlation_matrix,
    compute_kpi_summary,
    compute_time_trend,
    generate_visual_recommendations,
)
from tests.conftest import edge_datasets


def _frames():
    rng = np.random.default_rng(42)
    a = pd.DataFrame({"region": rng.choice(["North", "South", "East", "West"], 200),
                      "sales": rng.uniform(100, 5000, 200), "units": rng.integers(1, 100, 200)})
    b = pd.DataFrame({"a": rng.normal(0, 1, 150), "c": rng.normal(-3, 0.5, 150), "d": rng.uniform(0, 100, 150)})
    b["b"] = b["a"] * 2 + rng.normal(0, 0.1, 150)
    g = a.copy()
    g.loc[::5, "sales"] = np.nan
    g.loc[::7, "region"] = None
    frames = {
        "numeric_plus_categorical": a, "many_numeric": b,
        "datetime_numeric": pd.DataFrame({"date": pd.date_range("2024-01-01", periods=100, freq="D"),
                                          "revenue": rng.uniform(1000, 5000, 100)}),
        "mostly_categorical": pd.DataFrame({"color": rng.choice(["red", "blue", "green"], 80),
                                            "size": rng.choice(["S", "M", "L", "XL"], 80),
                                            "brand": rng.choice(["A", "B"], 80)}),
        "single_numeric": pd.DataFrame({"value": rng.normal(50, 10, 120)}),
        "small": pd.DataFrame({"cat": ["x", "y", "x"], "num": [1, 2, 3]}),
        "with_missing": g,
        "id_like": pd.DataFrame({"customer_id": range(1, 201), "order_code": [f"ORD-{i}" for i in range(1, 201)],
                                 "category": rng.choice(list("ABC"), 200), "amount": rng.uniform(10, 1000, 200)}),
        "empty": pd.DataFrame(), "single_row": pd.DataFrame({"a": [1], "b": ["x"]}),
        # realistic names that previously looked like identifiers
        "humidity_dataset": pd.DataFrame({"humidity": rng.uniform(20, 90, 100), "width": rng.uniform(1, 9, 100),
                                          "site": rng.choice(["A", "B", "C"], 100)}),
    }
    frames.update({f"edge_{k}": v for k, v in edge_datasets().items()})
    return frames


FRAMES = _frames()


@pytest.mark.parametrize("name", list(FRAMES))
def test_recommendations_are_valid_unique_and_buildable(name):
    df = FRAMES[name]
    recs = generate_visual_recommendations(df)
    seen = set()
    for r in recs:
        key = (r["chart_type"], r.get("x_column"), r.get("y_column"), r.get("aggregation"),
               tuple(r.get("columns") or []))
        assert key not in seen, f"duplicate recommendation {key}"
        seen.add(key)
        for field in ("x_column", "y_column"):
            if r.get(field) is not None:
                assert r[field] in df.columns
        assert all(c in df.columns for c in (r.get("columns") or []))
        if r["chart_type"] == "KPI Summary":
            assert isinstance(compute_kpi_summary(df, r["columns"]), list)
        elif r["chart_type"] == "Bottom Categories":
            assert isinstance(compute_category_aggregation(
                df, r["x_column"], r["y_column"], r["aggregation"], ascending=True), pd.DataFrame)
        elif r["chart_type"] == "Time Trend":
            assert isinstance(compute_time_trend(df, r["x_column"], r["y_column"], r["aggregation"]), pd.DataFrame)
        elif r["chart_type"] == "Correlation Heatmap":
            assert isinstance(compute_correlation_matrix(df, r["columns"]), pd.DataFrame)


def test_empty_frames_give_no_recommendations():
    assert generate_visual_recommendations(pd.DataFrame()) == []
    assert generate_visual_recommendations(None) == []


def test_id_columns_are_never_recommended_as_metrics_or_groups():
    recs = generate_visual_recommendations(FRAMES["id_like"])
    used = {r.get(f) for r in recs for f in ("x_column", "y_column")} | {c for r in recs for c in r.get("columns") or []}
    assert "customer_id" not in used and "order_code" not in used


def test_real_metrics_with_id_letters_are_recommended():
    recs = generate_visual_recommendations(FRAMES["humidity_dataset"])
    used = {r.get(f) for r in recs for f in ("x_column", "y_column")} | {c for r in recs for c in r.get("columns") or []}
    assert "humidity" in used or "width" in used


def test_recommendations_are_ordered_by_priority_and_capped():
    recs = generate_visual_recommendations(FRAMES["many_numeric"], max_recommendations=3)
    assert len(recs) <= 3
    assert [r["priority"] for r in recs] == sorted((r["priority"] for r in recs), reverse=True)


# ------------------------------------------------------- compute_* correctness
@pytest.fixture()
def sales():
    return pd.DataFrame({
        "g": ["A", "A", "B", "B", "C"],
        "v": [10.0, 20.0, 5.0, None, 40.0],
        "d": pd.to_datetime(["2024-01-01", "2024-01-15", "2024-02-01", "2024-02-20", "2024-03-05"]),
    })


@pytest.mark.parametrize("agg,expected", [
    ("Sum", {"A": 30.0, "B": 5.0, "C": 40.0}),
    ("Mean", {"A": 15.0, "B": 5.0, "C": 40.0}),          # NaN ignored, not counted as 0
    ("Median", {"A": 15.0, "B": 5.0, "C": 40.0}),
    ("Count", {"A": 2, "B": 1, "C": 1}),                 # counts non-missing values
    ("Max", {"A": 20.0, "B": 5.0, "C": 40.0}),
    ("Min", {"A": 10.0, "B": 5.0, "C": 40.0}),
])
def test_category_aggregation_values(sales, agg, expected):
    out = compute_category_aggregation(sales, "g", "v", agg, ascending=False, top_n=10)
    got = dict(zip(out.iloc[:, 0], out.iloc[:, 1]))
    assert got == pytest.approx(expected)
    assert list(out.iloc[:, 1]) == sorted(out.iloc[:, 1], reverse=True)


def test_category_aggregation_top_n_and_ascending(sales):
    top = compute_category_aggregation(sales, "g", "v", "Sum", ascending=False, top_n=2)
    assert list(top.iloc[:, 0]) == ["C", "A"]
    bottom = compute_category_aggregation(sales, "g", "v", "Sum", ascending=True, top_n=1)
    assert list(bottom.iloc[:, 0]) == ["B"]


def test_category_aggregation_same_column_for_x_and_y_does_not_crash():
    df = pd.DataFrame({"a": [1, 1, 2, 3]})
    assert isinstance(compute_category_aggregation(df, "a", "a", "Count"), pd.DataFrame)


def test_time_trend_aggregates_per_period_in_order(sales):
    out = compute_time_trend(sales, "d", "v", "Sum")
    assert out.iloc[:, 0].is_monotonic_increasing
    assert out.iloc[:, 1].sum() == pytest.approx(75.0)    # no value lost or double counted


def test_kpi_summary_matches_pandas(sales):
    (row,) = compute_kpi_summary(sales, ["v"])
    assert row["column"] == "v" and row["sum"] == pytest.approx(75.0)
    assert row["mean"] == pytest.approx(18.75) and row["count"] == 4 and row["missing"] == 1


def test_correlation_matrix_matches_pandas():
    rng = np.random.default_rng(3)
    df = pd.DataFrame({"x": rng.normal(size=80)})
    df["y"] = df["x"] * 3 + rng.normal(size=80) * 0.2
    df["z"] = rng.normal(size=80)
    cm = compute_correlation_matrix(df, ["x", "y", "z"])
    assert cm.loc["x", "y"] == pytest.approx(df["x"].corr(df["y"]))
    assert cm.loc["x", "z"] == pytest.approx(df["x"].corr(df["z"]))
    assert (np.diag(cm.values) == 1).all() and np.allclose(cm, cm.T)


def test_recommendation_output_is_pinned_for_the_shipped_samples():
    """Golden test: the helper-based generator must keep producing exactly these recommendations."""
    from pathlib import Path

    import pandas as pd

    from data.recommender import generate_visual_recommendations
    root = Path(__file__).resolve().parents[2] / "sample_data"
    retail = generate_visual_recommendations(pd.read_csv(root / "retail_sales_messy.csv"))
    assert [(r["title"], r["priority"]) for r in retail] == [
        ("revenue Trend Over Time", 90), ("KPI Summary Overview", 85), ("Average revenue by region", 80),
        ("Top region by Total revenue", 78), ("Correlation Heatmap", 75), ("unit_price vs revenue Relationship", 69),
        ("Outlier Check: unit_price", 65), ("Distribution of region", 60)]
    weather = generate_visual_recommendations(pd.read_csv(root / "weather_stations_numeric.csv"))
    assert [(r["title"], r["priority"]) for r in weather] == [
        ("KPI Summary Overview", 85), ("temperature_c vs humidity Relationship", 82), ("Correlation Heatmap", 75),
        ("Outlier Check: rain_mm", 65), ("Distribution of humidity", 50), ("Distribution of wind_speed_kmh", 50)]
