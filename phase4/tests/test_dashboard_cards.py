"""Numbers behind the dashboard cards (pure pandas)."""
import numpy as np
import pandas as pd
import pytest

from data.charts import ChartConfigError, build_donut
from data.dashboard_cards import compact_number, completeness_summary, composition, delta_percent, kpi_cards, latest_records, quality_checks


@pytest.fixture
def sales():
    return pd.DataFrame({
        "region": ["N", "N", "S", "S", "E", "W", "W", "W"],
        "rev": [10.0, 20.0, 30.0, np.nan, 50.0, 60.0, 70.0, 80.0],
        "day": pd.date_range("2024-01-01", periods=8),
    })


@pytest.mark.parametrize("value,text", [(0, "0"), (12, "12"), (12.5, "12.50"), (1234, "1.23K"), (4.38e7, "43.80M"),
                                        (2.5e9, "2.50B"), (3e12, "3.00T"), (-5000, "-5.00K"), (None, "—"),
                                        (float("nan"), "—"), (float("inf"), "—")])
def test_compact_number(value, text):
    assert compact_number(value) == text


def test_delta_percent():
    assert delta_percent(110, 100) == pytest.approx(10.0)
    assert delta_percent(50, 100) == pytest.approx(-50.0)
    assert delta_percent(5, 0) is None and delta_percent(None, 5) is None and delta_percent(5, float("nan")) is None


def test_completeness_summary_counts(sales):
    s = completeness_summary(sales)
    assert s["total_rows"] == 8 and s["missing_cells"] == 1 and s["complete_rows"] == 7 and s["rows_with_gaps"] == 1
    assert s["complete_pct"] == pytest.approx((1 - 1 / 24) * 100) and s["duplicate_rows"] == 0
    assert completeness_summary(pd.DataFrame())["complete_pct"] == 100.0


def test_kpi_cards_compare_the_view_with_the_full_dataset(sales):
    view = sales[sales.region == "W"]
    cards = {c["key"]: c for c in kpi_cards(sales, view, "rev", "Sum", "region")}
    assert cards["records"]["value"] == "3" and cards["records"]["delta_text"] == "-5"
    assert cards["metric"]["label"] == "Sum rev" and cards["metric"]["value"] == "210"
    assert cards["metric"]["delta_text"] == f"{(210 - 320) / 320 * 100:+.1f}%"   # full sum ignores the missing value: 320
    assert cards["segments"]["value"] == "1" and cards["segments"]["label"] == "Distinct region"
    assert cards["completeness"]["value"] == "100.0%" and cards["completeness"]["direction"] == "up"


def test_only_completeness_is_judged_good_or_bad(sales):
    cards = {c["key"]: c for c in kpi_cards(sales, sales[sales.region == "W"], "rev", "Sum", "region")}
    assert cards["records"]["tone"] == cards["metric"]["tone"] == cards["segments"]["tone"] == "neutral"
    assert cards["completeness"]["tone"] == "good"
    worse = kpi_cards(sales, sales[sales.region == "S"], "rev", "Sum", "region")[2]
    assert worse["tone"] == "bad" and worse["direction"] == "down"


def test_kpi_cards_without_metric_or_category(sales):
    cards = kpi_cards(sales, sales, None, "Sum", None)
    assert [c["key"] for c in cards] == ["records", "metric", "completeness", "segments"]
    assert cards[1]["label"] == "Numeric Columns" and cards[3]["label"] == "Columns"
    assert all(c["tone"] == "neutral" for c in cards[:2] + cards[3:])


def test_composition_shares_add_up_and_group_the_tail(sales):
    result = composition(sales, "region", "rev", "Average", top_n=2)
    assert result["basis"] == "Total rev" and result["note"] is None
    # totals ignore the missing value: W=210, E=50, N=30, S=30
    assert [i["label"] for i in result["items"]] == ["W", "E", "Other"]
    assert result["items"][2]["value"] == pytest.approx(60)
    assert sum(i["share"] for i in result["items"]) == pytest.approx(1.0)
    assert result["total"] == pytest.approx(sales["rev"].sum())
    assert result["items"][0]["value"] == pytest.approx(210)


def test_composition_uses_record_counts_for_count_or_no_metric(sales):
    counts = composition(sales, "region", None, "Sum")
    assert counts["basis"] == "Records" and counts["total"] == 8
    assert composition(sales, "region", "rev", "Count")["basis"] == "Records"


@pytest.mark.parametrize("frame,category", [
    (pd.DataFrame({"g": ["a", "b"], "v": [-1.0, 5.0]}), "g"),
    (pd.DataFrame({"g": ["a", "b"], "v": [0.0, 0.0]}), "g"),
    (pd.DataFrame({"g": ["a", "b"], "v": [np.nan, np.nan]}), "g"),
    (pd.DataFrame(), "g"), (pd.DataFrame({"g": ["a"]}), None), (pd.DataFrame({"g": ["a"]}), "missing"),
])
def test_composition_explains_why_it_cannot_be_drawn(frame, category):
    result = composition(frame, category, "v", "Sum")
    assert result["items"] == [] and result["note"]


def test_composition_labels_missing_categories():
    df = pd.DataFrame({"g": ["a", None, None], "v": [1.0, 2.0, 3.0]})
    labels = [i["label"] for i in composition(df, "g", "v", "Sum")["items"]]
    assert labels == ["(missing)", "a"]


def test_quality_checks_clean_and_dirty(sales):
    clean = quality_checks(sales.dropna())
    assert all(c["status"] == "ok" for c in clean) and any(c["name"] == "Date validity" for c in clean)
    dirty = sales.copy()
    dirty.loc[0, "rev"] = np.inf
    dirty = pd.concat([dirty, dirty.head(2)])
    by_name = {c["name"]: c for c in quality_checks(dirty, max_checks=9)}
    assert by_name["Numeric validity"]["status"] == "bad" and by_name["Duplicate rows"]["status"] == "warn"
    assert quality_checks(pd.DataFrame()) == []
    assert len(quality_checks(sales, max_checks=3)) == 3


def test_quality_completeness_thresholds():
    low = pd.DataFrame({"a": [1, None, None, None], "b": [1, 2, 3, 4]})
    check = quality_checks(low)[0]
    assert check["status"] == "bad" and "62.5%" in check["detail"]


def test_latest_records_sorts_by_date_and_limits_columns(sales):
    latest = latest_records(sales, "day", n=3)
    assert list(latest["region"]) == ["W", "W", "W"] and latest.index.tolist() == [7, 6, 5]
    assert len(latest_records(sales, None, n=2)) == 2
    wide = pd.DataFrame(np.arange(20).reshape(2, 10))
    assert latest_records(wide, None, max_columns=4).shape[1] == 4
    bad_dates = sales.assign(day="not a date")
    assert len(latest_records(bad_dates, "day", n=2)) == 2


def test_build_donut_structure_and_validation():
    fig = build_donut(["a", "b"], [3, 1], "4", "Total", ["#111111", "#222222"])
    assert fig.data[0].type == "pie" and fig.data[0].hole == pytest.approx(0.66)
    assert list(fig.data[0].marker.colors) == ["#111111", "#222222"] and fig.layout.showlegend is False
    assert "Total" in fig.layout.annotations[0].text
    with pytest.raises(ChartConfigError):
        build_donut([], [], "0", "x", ["#000000"])
    with pytest.raises(ChartConfigError):
        build_donut(["a"], [1, 2], "0", "x", ["#000000"])
