"""Shared pytest fixtures and helpers for AnalyticsPro tests.

Run from the repository root or from phase4/:
    python -m pytest
"""
import io
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

PHASE4 = Path(__file__).resolve().parents[1]
APP_PATH = str(PHASE4 / "app.py")
if str(PHASE4) not in sys.path:
    sys.path.insert(0, str(PHASE4))

warnings.filterwarnings("ignore", category=UserWarning)

PAGES = [
    "Data Upload & Preview", "Data Preparation", "Automatic EDA", "KPI Dashboard",
    "Interactive Dashboard", "Visualizations", "Correlation & Relationships", "Outlier Detection",
    "Ask Your Data", "Dataset Comparison", "Export & Reporting",
]

# AppTest's built-in 3 s default is too short on cold start / under coverage.
APPTEST_TIMEOUT = 120


def csv_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def named_buffer(data: bytes, name: str) -> io.BytesIO:
    buf = io.BytesIO(data)
    buf.name = name
    return buf


def make_app(df=None, name="test.csv", page=None) -> AppTest:
    """Start the app; optionally inject an already-loaded dataset."""
    at = AppTest.from_file(APP_PATH, default_timeout=APPTEST_TIMEOUT)
    at.run()
    assert not at.exception, f"app failed to start: {at.exception}"
    if df is not None:
        at.session_state["df"] = df
        at.session_state["original_df"] = df.copy()
        at.session_state["dataset_name"] = name
        at.session_state["uploaded_file_name"] = name
    if page:
        at.session_state["current_page"] = page
        at.run()
    return at


def upload(at: AppTest, content: bytes, name: str, widget=None):
    """Upload through the sidebar file_uploader (or a given uploader widget)."""
    w = widget if widget is not None else at.sidebar.file_uploader[0]
    w.set_value([(name, content, "text/csv")])
    at.run()
    return at


@pytest.fixture(scope="session")
def sales_df() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    n = 120
    df = pd.DataFrame({
        "region": rng.choice(["North", "South", "East", "West"], n),
        "product": rng.choice(["Widget", "Gadget", "Gizmo"], n),
        "sales": rng.gamma(2.0, 500.0, n).round(2),
        "units": rng.integers(1, 60, n),
        "date": pd.date_range("2024-01-01", periods=n, freq="D"),
    })
    df.loc[rng.choice(n, 10, replace=False), "sales"] = np.nan
    return df


def edge_datasets() -> dict:
    """Unusual-but-valid datasets, loaded through the real loader."""
    from data.loader import load_dataset

    def ld(text, name="t.csv"):
        return load_dataset(named_buffer(csv_bytes(text), name))

    rng = np.random.default_rng(1)
    n = 60
    return {
        "zero_rows": ld("a,b,c\n"),
        "single_row": ld("a,b\n1,x\n"),
        "single_numeric_col": ld("v\n" + "\n".join(map(str, rng.integers(0, 9, n)))),
        "all_numeric": ld("a,b,c\n" + "\n".join(f"{i},{i * 2},{i % 5}" for i in range(n))),
        "all_nan_col": ld("a,b\n" + "\n".join(f"{i}," for i in range(n))),
        "all_duplicate": ld("a,b\n" + "1,x\n" * n),
        "mixed_types": ld("a,m\n" + "\n".join(f"{i},{'x' if i % 3 == 0 else i}" for i in range(n))),
        "weird_names": ld('"<b>x</b>",a b,ñandú,1,2,dup,dup\n'
                          + "\n".join(f"{i},{i*2},{i%3},{i},{i},{i},{i}" for i in range(n))),
        "inf_values": ld("a,b\n" + "\n".join(f"{i},{'inf' if i == 5 else i}" for i in range(n))),
        "dates_bool": ld("d,flag,v,c\n" + "\n".join(
            f"2024-01-{(i % 28) + 1:02d},{i % 2 == 0},{i},{'A' if i % 2 else 'B'}" for i in range(n))),
        "constant_cols": ld("k,v\n" + "\n".join(f"same,{i}" for i in range(n))),
        "high_cardinality_text": ld("id,txt,v\n" + "\n".join(f"{i},word{i},{i * 1.5}" for i in range(n))),
        "numeric_header_names": ld("2023,2024\n" + "\n".join(f"{i},{i + 1}" for i in range(n))),
    }
