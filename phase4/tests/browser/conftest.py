"""Fixtures for real-browser tests (Playwright + Chromium).

Skipped automatically when Playwright or a Chromium build is unavailable.
Run with:  python -m pytest tests/browser -m browser
"""
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

PHASE4 = Path(__file__).resolve().parents[2]

try:
    from playwright.sync_api import sync_playwright
    _HAVE_PLAYWRIGHT = True
except Exception:  # pragma: no cover
    _HAVE_PLAYWRIGHT = False


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server_url():
    if not _HAVE_PLAYWRIGHT:
        pytest.skip("playwright not installed")
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless", "true",
         "--server.port", str(port), "--browser.gatherUsageStats", "false"],
        cwd=PHASE4, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            if urllib.request.urlopen(f"{url}/_stcore/health", timeout=1).read() == b"ok":
                break
        except Exception:
            time.sleep(1)
    else:
        proc.terminate()
        pytest.skip("streamlit server did not start")
    yield url
    proc.terminate()
    try:
        proc.wait(10)
    except Exception:
        proc.kill()


@pytest.fixture(scope="session")
def browser():
    if not _HAVE_PLAYWRIGHT:
        pytest.skip("playwright not installed")
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"chromium unavailable: {exc}")
        yield b
        b.close()


@pytest.fixture()
def sample_csv(tmp_path):
    path = tmp_path / "sales.csv"
    rows = ["region,sales,units"] + [f"{r},{100 + i},{i % 9}" for i, r in
                                      enumerate(["North", "South", "East", "West"] * 10)]
    path.write_text("\n".join(rows))
    return str(path)
