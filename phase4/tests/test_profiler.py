"""Unit tests for data/profiler.py, checked against independent pandas/numpy results."""
import numpy as np
import pandas as pd
import pytest

from data import profiler as pr


@pytest.fixture()
def df():
    rng = np.random.default_rng(7)
    n = 500
    frame = pd.DataFrame({
        "g": rng.choice(list("ABCD"), n),
        "x": rng.normal(100, 15, n),
        "y": rng.gamma(2, 10, n),
        "d": pd.date_range("2024-01-01", periods=n, freq="D"),
    })
    frame.loc[rng.choice(n, 40, replace=False), "x"] = np.nan
    return pd.concat([frame, frame.iloc[:10]], ignore_index=True)


def test_dataset_metrics_match_pandas(df):
    m = pr.dataset_metrics(df)
    assert m["rows"] == len(df) and m["columns"] == 4
    assert m["missing"] == int(df.isna().sum().sum()) and m["duplicates"] == int(df.duplicated().sum())
    assert m["numeric"] == 2 and m["categorical"] == 1


def test_dataset_metrics_empty():
    assert pr.dataset_metrics(pd.DataFrame()) == {
        "rows": 0, "columns": 0, "numeric": 0, "categorical": 0, "missing": 0, "duplicates": 0}


def test_health_score_formula_and_status(df):
    h = pr.calculate_dataset_health(df)
    completeness = round((df.size - df.isna().sum().sum()) / df.size * 100, 1)
    uniqueness = round((1 - df.duplicated().sum() / len(df)) * 100, 1)
    assert h["completeness"] == pytest.approx(completeness) and h["uniqueness"] == pytest.approx(uniqueness)
    assert h["overall"] == int(completeness * 0.6 + uniqueness * 0.4)
    assert h["status"] in {"Excellent", "Good", "Fair", "Poor"}
    assert pr.calculate_dataset_health(pd.DataFrame())["status"] == "Empty"


def test_perfect_data_scores_100():
    h = pr.calculate_dataset_health(pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]}))
    assert h["overall"] == 100 and h["status"] == "Excellent"


def test_numeric_statistics_match_pandas(df):
    ns = pr.numeric_statistics(df).set_index("Column")
    x = df["x"]
    assert ns.loc["x", "mean"] == pytest.approx(x.mean())
    assert ns.loc["x", "median"] == pytest.approx(x.median())
    assert ns.loc["x", "std"] == pytest.approx(x.std())
    assert ns.loc["x", "min"] == pytest.approx(x.min()) and ns.loc["x", "max"] == pytest.approx(x.max())
    assert ns.loc["x", "missing"] == int(x.isna().sum())
    assert ns.loc["x", "skewness"] == pytest.approx(x.skew())


def test_categorical_statistics_match_pandas(df):
    cs = pr.categorical_statistics(df).set_index("Column")
    counts = df["g"].value_counts()
    assert cs.loc["g", "Unique"] == df["g"].nunique()
    assert cs.loc["g", "Most Common"] == counts.index[0] and cs.loc["g", "Frequency"] == counts.iloc[0]


def test_outlier_summary_matches_iqr_definition(df):
    row = pr.outlier_summary(df).set_index("Column").loc["x"]
    s = df["x"].dropna()
    q1, q3 = s.quantile(.25), s.quantile(.75)
    lo, hi = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    assert row["Lower Bound"] == pytest.approx(lo) and row["Upper Bound"] == pytest.approx(hi)
    assert row["Outliers"] == int(((df["x"] < lo) | (df["x"] > hi)).sum())


def test_outlier_summary_detects_a_planted_outlier():
    frame = pd.DataFrame({"v": [10, 11, 9, 10, 12, 10, 11, 9, 10, 500]})
    assert pr.outlier_summary(frame).iloc[0]["Outliers"] == 1


def test_column_profile_and_roles(df):
    prof = pr.get_column_profile(df).set_index("Column")
    assert prof.loc["x", "Missing"] == int(df["x"].isna().sum())
    assert prof.loc["g", "Unique"] == 4
    assert prof.loc["g", "Role"] == "Categorical" and prof.loc["x", "Role"] == "Numeric"
    assert pr.infer_column_role(df["d"]) == "Date/Time"
    assert pr.infer_column_role(pd.Series([True, False])) == "Categorical"   # booleans are labels, not numbers


def test_insights_mention_real_facts(df):
    text = " ".join(pr.generate_eda_insights(df))
    assert "missing" in text and "duplicate" in text.lower()
    assert pr.generate_eda_insights(pd.DataFrame()) == []


def test_profile_functions_survive_degenerate_frames():
    for frame in (pd.DataFrame(), pd.DataFrame({"a": [1]}), pd.DataFrame({"a": [None, None]}),
                  pd.DataFrame({"a": ["x"] * 5})):
        pr.dataset_metrics(frame)
        pr.calculate_dataset_health(frame)
        pr.numeric_statistics(frame)
        pr.categorical_statistics(frame)
        pr.outlier_summary(frame)
        pr.get_column_profile(frame)
        pr.generate_eda_insights(frame)


# --- the two metric helpers must tell the same story about the same data
@pytest.mark.parametrize("frame", [
    pd.DataFrame({"flag": [True, False, True], "n": [1, 2, 3], "c": ["a", "b", "c"]}),
    pd.DataFrame({"d": pd.date_range("2024-01-01", periods=3), "n": [1, 2, 3], "c": list("xyz")}),
    pd.DataFrame({"a": [1.0, 2.0], "b": [3, 4]}),
], ids=["with_bool", "with_datetime", "numeric_only"])
def test_dataset_metrics_and_profile_dataset_agree(frame):
    m, p = pr.dataset_metrics(frame), pr.profile_dataset(frame)
    for key in ("rows", "columns", "numeric", "categorical", "missing", "duplicates"):
        assert m[key] == p[key], f"{key}: dataset_metrics={m[key]} profile_dataset={p[key]}"


def test_column_kinds_add_up_to_the_column_count():
    frame = pd.DataFrame({"flag": [True, False], "n": [1, 2], "c": ["a", "b"], "d": pd.date_range("2024-01-01", periods=2)})
    m = pr.dataset_metrics(frame)
    assert m["numeric"] + m["categorical"] + 1 == m["columns"]        # + the one datetime column


# ---------------------------------------------------------------- correlation helpers (extracted from the page)
import pandas as _pd  # noqa: E402
import pytest as _pytest  # noqa: E402

from data.profiler import correlated_pairs, correlation_strength  # noqa: E402


@_pytest.mark.parametrize("value,label", [
    (0.95, "Strong Positive"), (0.71, "Strong Positive"), (0.5, "Moderate Positive"), (0.31, "Moderate Positive"),
    (0.2, "Weak Positive"), (0.0, "Weak Positive"), (-0.2, "Weak Negative"), (-0.5, "Moderate Negative"),
    (-0.9, "Strong Negative"),
])
def test_correlation_strength_labels_regression(value, label):
    """Regression: a weak +0.2 used to be labelled 'Moderate Negative' when the threshold was low."""
    assert correlation_strength(value) == label


def test_correlated_pairs_filters_by_absolute_value_and_lists_each_pair_once():
    df = _pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": [2, 4, 6, 8, 11], "c": [5, 4, 3, 2, 1], "d": [1, 0, 1, 0, 1]})
    pairs = correlated_pairs(df.corr(), 0.9)
    names = {(p["Feature A"], p["Feature B"]) for p in pairs}
    assert ("a", "b") in names and ("a", "c") in names and ("b", "a") not in names
    assert all(abs(p["Correlation"]) >= 0.9 for p in pairs)
    assert next(p for p in pairs if (p["Feature A"], p["Feature B"]) == ("a", "c"))["Strength"] == "Strong Negative"
    assert correlated_pairs(df.corr(), 1.01) == []


def test_correlated_pairs_skips_missing_coefficients():
    df = _pd.DataFrame({"a": [1, 2, 3], "const": [1, 1, 1], "b": [3, 2, 1]})
    pairs = correlated_pairs(df.corr(), 0.0)
    assert {(p["Feature A"], p["Feature B"]) for p in pairs} == {("a", "b")}
