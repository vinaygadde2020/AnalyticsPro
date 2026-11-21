"""
Capture the README screenshots from a running app and the bundled sample data.

    pip install -r requirements-dev.txt && playwright install chromium
    python scripts/make_screenshots.py            # writes docs/screenshots/*.png

The script starts Streamlit itself on a free port and stops it afterwards.
"""
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "phase4"
OUT = ROOT / "docs" / "screenshots"
SAMPLE = ROOT / "sample_data" / "retail_sales_messy.csv"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def settle(page, extra=1.5):
    time.sleep(1.0)
    try:
        page.wait_for_selector('[data-testid="stStatusWidget"]', state="detached", timeout=60000)
    except Exception:
        pass
    time.sleep(extra)


def go(page, label):
    page.locator('[data-testid="stSidebar"]').get_by_role("button", name=re.compile(label)).first.click()
    settle(page, 2.5)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    port = free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless", "true",
         "--server.port", str(port), "--browser.gatherUsageStats", "false"],
        cwd=APP_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                if urllib.request.urlopen(f"{url}/_stcore/health", timeout=1).read() == b"ok":
                    break
            except Exception:
                time.sleep(1)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(url)
            page.wait_for_selector("text=AnalyticsPro", timeout=30000)
            time.sleep(2)
            page.locator('input[type="file"]').first.set_input_files(str(SAMPLE))
            page.wait_for_selector("text=Active:", timeout=30000)
            settle(page)
            page.screenshot(path=str(OUT / "01_upload_preview.png"))

            go(page, "Data Preparation")
            page.screenshot(path=str(OUT / "02_data_preparation.png"))
            go(page, "Automatic EDA")
            page.screenshot(path=str(OUT / "03_automatic_eda.png"))
            go(page, "KPI Dashboard")
            page.screenshot(path=str(OUT / "04_kpi_dashboard.png"))
            go(page, "Interactive Dashboard")
            page.screenshot(path=str(OUT / "09_interactive_dashboard.png"), full_page=True)
            go(page, "Visualizations")
            page.screenshot(path=str(OUT / "05_visualizations.png"))
            go(page, "Outlier")
            page.screenshot(path=str(OUT / "06_outlier_detection.png"))
            go(page, "Export")
            page.screenshot(path=str(OUT / "07_export.png"))

            phone = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                                        has_touch=True, device_scale_factor=2).new_page()
            phone.goto(url)
            phone.wait_for_selector("text=AnalyticsPro", timeout=30000)
            time.sleep(3)
            phone.screenshot(path=str(OUT / "08_mobile.png"))
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(10)
        except Exception:
            server.kill()
    for f in sorted(OUT.glob("*.png")):
        print(f.name, f"{f.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
