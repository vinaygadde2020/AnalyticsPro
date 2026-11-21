"""Shared aggregation helpers: one definition of Sum/Average/Median/Count/Min/Max."""
import numpy as np
import pandas as pd
import pytest

from data.aggregation import (
    AGGREGATION_LABELS,
    aggregate_grouped,
    aggregate_values,
    group_aggregate,
    normalize_aggregation,
    to_numeric_clean,
)


@pytest.mark.parametrize("label,expected", [("sum", "Sum"), ("Total", "Sum"), ("mean", "Average"), ("AVG", "Average"),
                                            ("Average", "Average"), ("minimum", "Min"), ("Maximum", "Max"),
                                            ("Median", "Median"), (" count ", "Count")])
def test_labels_are_normalised(label, expected):
    assert normalize_aggregation(label) == expected


def test_unknown_label_raises_instead_of_silently_falling_back():
    with pytest.raises(ValueError, match="Unknown aggregation"):
        normalize_aggregation("mode")


def test_aggregate_values_ignores_text_and_infinity():
    s = pd.Series([1, 2, "x", np.inf, -np.inf, None, 3])
    got = {label: aggregate_values(s, label) for label in AGGREGATION_LABELS}
    assert got == {"Sum": 6.0, "Average": 2.0, "Median": 2.0, "Count": 3.0, "Min": 1.0, "Max": 3.0}


def test_aggregate_values_on_empty_input():
    empty = pd.Series([], dtype=float)
    assert aggregate_values(empty, "Sum") is None and aggregate_values(empty, "Count") == 0.0


def test_sum_of_an_all_missing_group_stays_missing_not_zero():
    df = pd.DataFrame({"g": ["a", "a", "b"], "v": [1.0, 2.0, np.nan]})
    out, name = group_aggregate(df, ["g"], "v", "Sum")
    assert name == "v" and out.set_index("g")["v"].isna()["b"] and out.set_index("g")["v"]["a"] == 3.0
    assert aggregate_grouped(df.groupby("g")["v"], "Sum").isna()["b"]


def test_group_aggregate_renames_when_value_is_also_a_key():
    df = pd.DataFrame({"g": list("aab")})
    out, name = group_aggregate(df, ["g"], "g", "Count")
    assert name == "g (count)" and out.set_index("g")[name].to_dict() == {"a": 2, "b": 1}


def test_group_aggregate_with_two_keys_and_text_values():
    df = pd.DataFrame({"a": list("xxyy"), "b": list("pqpq"), "v": ["1", "2", "x", "4"]})
    out, _ = group_aggregate(df, ["a", "b"], "v", "Sum")
    assert len(out) == 4 and out["v"].sum() == 7.0


def test_to_numeric_clean():
    assert to_numeric_clean(pd.Series(["1", "a", np.inf])).isna().tolist() == [False, True, True]
