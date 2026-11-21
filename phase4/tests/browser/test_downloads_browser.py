"""Real-browser tests: deferred downloads still deliver correct files."""
import io
import re
import time

import pandas as pd
import pytest

pytestmark = pytest.mark.browser

CSV_TEXT = "region,sales,units\n" + "\n".join(
    f"{r},{100 + i}.5,{i % 7}" for i, r in enumerate(["North", "South", "East", "West"] * 15))


@pytest.fixture()
def loaded_page(browser, server_url, tmp_path):
    src = tmp_path / "my data.csv"
    src.write_text(CSV_TEXT)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    page = ctx.new_page()
    page.goto(server_url)
    page.wait_for_selector("text=AnalyticsPro", timeout=30000)
    time.sleep(2)
    page.locator('input[type="file"]').first.set_input_files(str(src))
    page.wait_for_selector("text=Active:", timeout=30000)
    time.sleep(2)
    yield page
    ctx.close()


def _settle(page, extra=1.0):
    """Wait until Streamlit has finished running the script (no 'running' indicator)."""
    time.sleep(1.0)
    try:
        page.wait_for_selector('[data-testid="stStatusWidget"]', state="detached", timeout=60000)
    except Exception:
        pass
    time.sleep(extra)


def _go(page, label):
    page.locator('[data-testid="stSidebar"]').get_by_role("button", name=re.compile(label)).first.click()
    _settle(page, 2.0)


def _download(page, button_label):
    """Click a download button and return (filename, bytes).

    A download click makes Streamlit rerun the script, so wait for it to go idle
    before and after; otherwise the next click can land on a re-rendering page."""
    _settle(page)
    with page.expect_download(timeout=60000) as info:
        page.get_by_role("button", name=re.compile(button_label)).first.click()
    dl = info.value
    result = (dl.suggested_filename, open(dl.path(), "rb").read())
    _settle(page)
    return result


def test_prep_preview_tab_is_preview_only(loaded_page):
    page = loaded_page
    _go(page, "Data Preparation")
    page.get_by_role("tab", name=re.compile("Preview")).click()
    _settle(page)
    assert page.get_by_text("Cleaned Dataset Preview").is_visible()
    assert page.get_by_text(re.compile("To download processed data.*Export & Reporting")).is_visible()


def test_export_page_downloads(loaded_page):
    page = loaded_page
    _go(page, "Export")
    name, data = _download(page, "Download Executive Report")
    html = data.decode("utf-8")
    assert name == "my data_Executive_Report.html"
    assert "<html" in html.lower() and "my data.csv" in html

    name, data = _download(page, "Download Current Processed Dataset")
    assert name == "my data_cleaned.csv" and pd.read_csv(io.BytesIO(data)).shape == (60, 3)

    name, data = _download(page, "Download Full Column Data Profile")
    prof = pd.read_csv(io.BytesIO(data))
    assert name == "my data_column_profile.csv" and len(prof) == 3
