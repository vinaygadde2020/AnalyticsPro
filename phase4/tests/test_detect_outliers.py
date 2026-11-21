"""Unit tests for the shared outlier detector (data.profiler.detect_outliers)."""
import numpy as np
import pandas as pd
import pytest

from data import profiler as pr
from tests.test_outliers import _iqr_expected, _z_expected


@pytest.fixture()
def series():
    rng = np.random.default_rng(5)
    s = pd.Series(rng.normal(50, 5, 200))
    s.iloc[:3] = [300, -150, 250]
    s.iloc[10] = np.nan
    return s


@pytest.mark.parametrize("mult", [1.0, 1.5, 3.0])
def test_iqr_detector(series, mult):
    r = pr.detect_outliers(series, "iqr", mult)
    exp_n, exp_lo, exp_hi = _iqr_expected(series, mult)
    assert int(r.mask.sum()) == exp_n and r.lower == pytest.approx(exp_lo) and r.upper == pytest.approx(exp_hi)
    assert r.q1 == pytest.approx(series.quantile(.25)) and r.q3 == pytest.approx(series.quantile(.75))
    assert not r.mask.iloc[10], "missing values are not outliers"


@pytest.mark.parametrize("thr", [2.0, 3.0])
def test_zscore_detector(series, thr):
    r = pr.detect_outliers(series, "zscore", thr)
    exp_n, exp_lo, exp_hi = _z_expected(series, thr)
    assert int(r.mask.sum()) == exp_n and r.lower == pytest.approx(exp_lo) and r.upper == pytest.approx(exp_hi)


def test_defaults_and_degenerate_inputs():
    s = pd.Series([1.0, 2.0, 3.0, 100.0])
    assert pr.detect_outliers(s).mask.tolist() == pr.detect_outliers(s, "iqr", 1.5).mask.tolist()
    flat = pr.detect_outliers(pd.Series([4.0] * 10), "zscore", 3.0)
    assert not flat.mask.any() and flat.lower == flat.upper == 4.0
    empty = pr.detect_outliers(pd.Series([], dtype=float))
    assert len(empty.mask) == 0 and np.isnan(empty.lower)
    with pytest.raises(ValueError):
        pr.detect_outliers(s, "magic")


def test_mask_keeps_the_input_index():
    s = pd.Series([1.0, 2.0, 2.0, 2.0, 99.0], index=list("abcde"))
    assert pr.detect_outliers(s).mask.index.tolist() == list("abcde")
    assert pr.detect_outliers(s).mask["e"]


def test_outlier_summary_agrees_with_the_detector():
    rng = np.random.default_rng(2)
    df = pd.DataFrame({"a": np.r_[rng.normal(0, 1, 100), [50]], "b": np.r_[rng.normal(5, 1, 100), [-40]]})
    summary = pr.outlier_summary(df).set_index("Column")
    for col in ("a", "b"):
        r = pr.detect_outliers(df[col], "iqr", 1.5)
        assert summary.loc[col, "Outliers"] == int(r.mask.sum())
        assert summary.loc[col, "Lower Bound"] == pytest.approx(r.lower)
