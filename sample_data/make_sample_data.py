"""
Generate the synthetic sample datasets used for demos and screenshots.

All values are randomly generated with a fixed seed: no real people, companies or
measurements. Re-run to reproduce the files exactly:

    python sample_data/make_sample_data.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
rng = np.random.default_rng(2024)


def retail_sales_messy():
    """Sales table with the kinds of problems the Data Preparation page is for."""
    n = 1200
    products = {
        "Widget": ("Hardware", 12.5), "Gadget": ("Hardware", 29.0), "Gizmo": ("Hardware", 54.0),
        "Notebook": ("Stationery", 3.2), "Pen Set": ("Stationery", 7.8), "Planner": ("Stationery", 15.0),
        "Headset": ("Electronics", 79.0), "Charger": ("Electronics", 19.5),
    }
    names = rng.choice(list(products), n)
    units = rng.integers(1, 25, n)
    price = np.array([products[p][1] for p in names]) * rng.normal(1.0, 0.04, n)
    df = pd.DataFrame({
        "order_id": np.arange(10001, 10001 + n),
        "order_date": pd.Timestamp("2024-01-01") + pd.to_timedelta(rng.integers(0, 365, n), unit="D"),
        "region": rng.choice(["North", "South", "East", "West"], n, p=[.3, .25, .25, .2]),
        "product": names,
        "category": [products[p][0] for p in names],
        "units": units,
        "unit_price": price.round(2),
    })
    df["revenue"] = (df["units"] * df["unit_price"]).round(2)
    df = df.sort_values("order_date").reset_index(drop=True)
    df["order_date"] = df["order_date"].dt.strftime("%Y-%m-%d")

    # --- deliberately introduce problems ---------------------------------
    df.loc[rng.choice(n, 45, replace=False), "unit_price"] = np.nan          # missing numbers
    df.loc[rng.choice(n, 30, replace=False), "region"] = None                 # missing text
    messy = rng.choice(n, 60, replace=False)
    df.loc[messy, "region"] = df.loc[messy, "region"].map(
        lambda r: r if pd.isna(r) else rng.choice([f" {r}", f"{r} ", r.lower(), r.upper()]))   # spacing / case
    df.loc[rng.choice(n, 6, replace=False), "revenue"] *= 25                  # a few big outliers
    df = pd.concat([df, df.iloc[rng.choice(n, 25, replace=False)]], ignore_index=True)   # duplicate rows
    return df


def weather_stations_numeric():
    """Numeric-only data (no text column). Column names such as 'humidity' contain the
    letters 'id' and must still be treated as measurements."""
    n = 400
    temp = rng.normal(17, 8, n)
    df = pd.DataFrame({
        "station_id": rng.integers(1, 13, n),
        "temperature_c": temp.round(1),
        "humidity": np.clip(78 - 0.9 * (temp - 17) + rng.normal(0, 7, n), 15, 100).round(1),
        "pressure_hpa": rng.normal(1013, 8, n).round(1),
        "wind_speed_kmh": rng.gamma(2.2, 6.0, n).round(1),
        "rain_mm": np.where(rng.random(n) < .7, 0, rng.gamma(1.5, 4.0, n)).round(1),
    })
    df.loc[rng.choice(n, 12, replace=False), "humidity"] = np.nan
    return df


def employees_semicolon():
    """Semicolon-delimited file, as produced by many European spreadsheet exports."""
    n = 150
    dept = rng.choice(["Engineering", "Sales", "Support", "Finance", "Operations"], n)
    base = {"Engineering": 68000, "Sales": 52000, "Support": 41000, "Finance": 58000, "Operations": 47000}
    years = rng.integers(0, 15, n)
    df = pd.DataFrame({
        "employee_code": [f"E{i:04d}" for i in range(1, n + 1)],
        "department": dept,
        "years_service": years,
        "salary": (np.array([base[d] for d in dept]) * (1 + 0.025 * years) * rng.normal(1, .06, n)).round(0).astype(int),
        "remote_days": rng.integers(0, 6, n),
        "hire_date": (pd.Timestamp("2025-01-01") - pd.to_timedelta(years * 365 + rng.integers(0, 300, n), unit="D")).strftime("%Y-%m-%d"),
    })
    return df


if __name__ == "__main__":
    retail_sales_messy().to_csv(OUT / "retail_sales_messy.csv", index=False)
    weather_stations_numeric().to_csv(OUT / "weather_stations_numeric.csv", index=False)
    employees_semicolon().to_csv(OUT / "employees_semicolon.csv", index=False, sep=";")
    for f in sorted(OUT.glob("*.csv")):
        print(f"{f.name:<30} {f.stat().st_size / 1024:6.1f} KB")
