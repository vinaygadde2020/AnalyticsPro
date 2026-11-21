"""Column role classification (measure / category / identifier / date / ...)."""
import numpy as np
import pandas as pd
import pytest

from data.columns import ROLES, classify_columns, columns_by_role, measure_first, rank_measures


@pytest.fixture(scope="module")
def frame():
    rng = np.random.default_rng(0)
    n = 120
    return pd.DataFrame({
        "order_id": range(1000, 1000 + n),
        "row_no": range(n),
        "region": rng.choice(list("ABCD"), n),
        "revenue": rng.uniform(10, 900, n).round(2),
        "salary": rng.integers(30000, 90000, n),          # whole numbers, almost unique, NOT an id
        "humidity": rng.integers(20, 95, n),               # name contains "id" letters only
        "sku": [f"SKU{i:05d}" for i in range(n)],
        "note": [f"customer wrote comment number {i} here" for i in range(n)],
        "day": pd.date_range("2024-01-01", periods=n),
        "active": rng.choice([True, False], n),
        "version": 1,
        "blank": np.nan,
        "zip": rng.choice(["00123", "01234", "90210"], n),
        "many": [f"v{i % 70}" for i in range(n)],
    })


@pytest.mark.parametrize("col,role", [
    ("order_id", "identifier"), ("row_no", "identifier"), ("region", "category"), ("revenue", "measure"),
    ("salary", "measure"), ("humidity", "measure"), ("sku", "identifier"), ("note", "text"),
    ("day", "date"), ("active", "boolean"), ("version", "constant"), ("blank", "empty"),
    ("zip", "category"), ("many", "high_cardinality"),
])
def test_roles(frame, col, role):
    assert classify_columns(frame)[col] == role


def test_every_role_is_known_and_every_column_classified(frame):
    roles = classify_columns(frame)
    assert set(roles) == set(frame.columns) and set(roles.values()) <= set(ROLES)
    assert set(columns_by_role(frame)) == set(ROLES)


def test_empty_inputs():
    assert classify_columns(None) == {} and classify_columns(pd.DataFrame()) == {}
    assert set(classify_columns(pd.DataFrame(columns=["a", "b"])).values()) == {"empty"}


def test_numeric_text_dates_are_dates_and_digit_ids_are_not():
    df = pd.DataFrame({"d": ["2024-01-01", "2024-02-01", "2024-03-01"] * 10, "n": [str(1000 + i) for i in range(30)]})
    assert classify_columns(df)["d"] == "date" and classify_columns(df)["n"] != "date"


def test_rank_and_measure_first(frame):
    assert rank_measures(["units", "price", "revenue"])[0] == "revenue"
    ordered = measure_first(frame, ["order_id", "humidity", "revenue", "row_no"])
    assert ordered[0] == "revenue" and ordered[-2:] == ["order_id", "row_no"] and len(ordered) == 4
