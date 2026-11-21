"""Outlier detection: the page, the EDA summary and the shared detector must agree
with independently computed results."""
import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_app


@pytest.fixture()
def frame():
    rng = np.random.default_rng(11)
    x = rng.normal(100, 10, 300)
    x[:5] = [400, 390, -200, 10_000, 380]            # planted outliers
    df = pd.DataFrame({"x": x, "k": rng.integers(0, 5, 300)})
    df.loc[[7, 8], "x"] = np.nan
    return df


def _iqr_expected(s, mult):
    c = s.dropna()
    q1, q3 = c.quantile(.25), c.quantile(.75)
    lo, hi = q1 - mult * (q3 - q1), q3 + mult * (q3 - q1)
    return int(((s < lo) | (s > hi)).sum()), lo, hi


def _z_expected(s, thr):
    c = s.dropna()
    m, sd = c.mean(), c.std()
    z = (s - m) / sd
    return int((z.abs() > thr).sum()), m - thr * sd, m + thr * sd


def _page_metrics(at):
    m = {x.label: x.value for x in at.metric}
    return (int(m["Total Outliers"].replace(",", "")), float(m["Lower Bound Limit"].replace(",", "")),
            float(m["Upper Bound Limit"].replace(",", "")))


@pytest.mark.parametrize("mult", [1.5, 2.0, 3.0])
def test_outlier_page_iqr_matches_independent_calculation(frame, mult):
    at = make_app(frame, "o.csv", page="Outlier Detection")
    at.slider(key="iqr_mult").set_value(mult)
    at.run()
    assert not at.exception
    count, lo, hi = _page_metrics(at)
    exp_count, exp_lo, exp_hi = _iqr_expected(frame["x"], mult)
    assert count == exp_count and lo == pytest.approx(exp_lo, abs=0.01) and hi == pytest.approx(exp_hi, abs=0.01)


@pytest.mark.parametrize("thr", [2.0, 3.0, 4.0])
def test_outlier_page_zscore_matches_independent_calculation(frame, thr):
    at = make_app(frame, "o.csv", page="Outlier Detection")
    at.radio(key="outlier_method").set_value("Z-Score Method")
    at.run()
    at.slider(key="z_thresh").set_value(thr)
    at.run()
    assert not at.exception
    count, lo, hi = _page_metrics(at)
    exp_count, exp_lo, exp_hi = _z_expected(frame["x"], thr)
    assert count == exp_count and lo == pytest.approx(exp_lo, abs=0.01) and hi == pytest.approx(exp_hi, abs=0.01)


def test_outlier_page_constant_column_reports_no_outliers():
    df = pd.DataFrame({"x": [5.0] * 30, "y": np.arange(30.0)})
    at = make_app(df, "c.csv", page="Outlier Detection")
    at.radio(key="outlier_method").set_value("Z-Score Method")
    at.run()
    assert not at.exception and _page_metrics(at)[0] == 0
