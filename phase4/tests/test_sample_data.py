"""The bundled sample datasets must load and show the features they exist to demonstrate."""
import io
from pathlib import Path

import pandas as pd
import pytest

from data.loader import load_dataset
from data.profiler import dataset_metrics
from tests.conftest import PAGES, make_app
from utils.helpers import numeric_columns

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample_data"


def _load(name):
    buf = io.BytesIO((SAMPLE_DIR / name).read_bytes())
    buf.name = name
    return load_dataset(buf)


def test_retail_sales_is_messy_in_the_documented_ways():
    df = _load("retail_sales_messy.csv")
    m = dataset_metrics(df)
    assert m["rows"] == 1225 and m["duplicates"] == 25 and m["missing"] > 50
    assert pd.api.types.is_datetime64_any_dtype(df["order_date"]), "ISO dates must be detected"
    assert df["region"].str.strip().str.lower().nunique() == 4  # 4 real regions hide behind spacing/case noise
    assert df["region"].nunique() > 4


def test_weather_stations_is_numeric_only_and_keeps_humidity():
    df = _load("weather_stations_numeric.csv")
    assert dataset_metrics(df)["categorical"] == 0
    assert "humidity" in numeric_columns(df) and "station_id" not in numeric_columns(df)


def test_employees_semicolon_file_is_split_into_columns():
    df = _load("employees_semicolon.csv")
    assert list(df.columns) == ["employee_code", "department", "years_service", "salary", "remote_days", "hire_date"]
    assert len(df) == 150 and pd.api.types.is_datetime64_any_dtype(df["hire_date"])


@pytest.mark.parametrize("name", ["retail_sales_messy.csv", "weather_stations_numeric.csv", "employees_semicolon.csv"])
def test_every_page_renders_for_every_sample_dataset(name):
    at = make_app(_load(name), name)
    for page in PAGES:
        at.session_state["current_page"] = page
        at.run()
        assert not at.exception, f"{name} / {page}: {at.exception[0].value}"
