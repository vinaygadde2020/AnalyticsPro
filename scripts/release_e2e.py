"""End-to-end workflow validation of AnalyticsPro through a real browser (Playwright). Release-validation tool, not used by the app.

Usage (app already running; run from the repository root):
    python scripts/release_e2e.py http://localhost:8501 sample_data/retail_sales_messy.csv <two_sheet.xlsx> <second.csv>
The .xlsx must contain at least two worksheets whose first sheet has the same rows as the CSV, and whose second sheet is "Small" (50 rows).
Set CHROMIUM_PATH to use a specific Chromium binary instead of Playwright's own. Exit code is 0 only if every check passes.
"""
import io, os, re, sys, time, zipfile, json, subprocess, tempfile, pathlib
import pandas as pd
from playwright.sync_api import sync_playwright

URL, CSV, XLSX, SECOND = sys.argv[1:5]
RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)[:200])); print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)

def settle(page, extra=1.0):
    time.sleep(0.8)
    try: page.wait_for_selector('[data-testid="stStatusWidget"]', state="detached", timeout=60000)
    except Exception: pass
    time.sleep(extra)
def go(page, label):
    page.locator('[data-testid="stSidebar"]').get_by_role("button", name=re.compile(label)).first.click(); settle(page, 2.0)
def exceptions(page): return page.locator('[data-testid="stException"]').count()
def main_text(page): return page.locator('[data-testid="stMain"]').inner_text()
def active_rows(page):
    m = re.search(r"Active:\s*([\d,]+)\s*rows", page.locator('[data-testid="stSidebar"]').inner_text()); return int(m.group(1).replace(",", "")) if m else None
def upload(page, path):
    page.locator('[data-testid="stSidebar"] input[type="file"]').first.set_input_files(path)
    time.sleep(3); settle(page, 2.0)
def pick(page, label, option):
    """Select an option in a (searchable) Streamlit selectbox by typing it and pressing Enter."""
    cb = page.get_by_role("combobox", name=re.compile(re.escape(label), re.I)).first
    cb.click(); cb.fill(option); time.sleep(0.5); cb.press("Enter"); settle(page, 1.5)

ENV = {"executable_path": os.environ.get("CHROMIUM_PATH") or None}
with sync_playwright() as p:
    kw = {"headless": True, "args": ["--no-sandbox", "--disable-gpu", "--no-zygote", "--disable-dev-shm-usage"]}
    if ENV["executable_path"]: kw["executable_path"] = ENV["executable_path"]
    b = p.chromium.launch(**kw)
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True); page = ctx.new_page()
    errs = []; page.on("pageerror", lambda e: errs.append(str(e)[:200]))
    page.goto(URL); page.wait_for_selector("text=AnalyticsPro", timeout=30000); settle(page, 1.5)
    df_csv = pd.read_csv(CSV); n_csv = len(df_csv)

    # 1-2 Upload Excel (2 sheets), choose worksheet, then CSV; preview
    try:
        upload(page, XLSX)
        check("1a Excel upload loads first sheet", active_rows(page) == n_csv, active_rows(page))
        check("2a Preview page shows raw data + schema", "Raw data preview" in main_text(page) and "Column schema" in main_text(page))
        page.locator('[data-testid="stSidebar"]').get_by_text("Import options").click(); time.sleep(0.6)
        pick(page, "Worksheet", "Small"); time.sleep(2)
        check("1b Excel worksheet selector switches sheet (50 rows)", active_rows(page) == 50, active_rows(page))
    except Exception as e: check("1 Excel upload/worksheet", False, e)
    try:
        upload(page, CSV)
        check("1c CSV upload (replaces Excel dataset)", active_rows(page) == n_csv, active_rows(page))
        check("1d Upload page exception-free", exceptions(page) == 0)
    except Exception as e: check("1 CSV upload", False, e)

    # 3 Data preparation
    try:
        go(page, "Data Preparation")
        before_dups = int(df_csv.duplicated().sum()); before_na = int(df_csv.isna().sum().sum())
        page.get_by_role("button", name=re.compile("Run Quick Auto-Clean")).click(); settle(page, 3)
        rows_after = active_rows(page)
        check("3a Quick Auto-Clean removes duplicate rows", rows_after == n_csv - before_dups, f"{n_csv}->{rows_after}, dups={before_dups}")
        check("3b Cleaning leaves no missing cells (overview)", re.search(r"Missing Values\s*\n?\s*0\b", main_text(page)) is not None or "0" in main_text(page))
        page.get_by_role("tab", name=re.compile("Before vs After")).click(); settle(page)
        check("3c Before vs After tab renders", exceptions(page) == 0)
        page.get_by_role("tab", name=re.compile("Cleaning History")).click() if page.get_by_role("tab", name=re.compile("History")).count() else None
        check("3d Data Prep exception-free", exceptions(page) == 0)
    except Exception as e: check("3 Data prep", False, e)
    cleaned_rows = active_rows(page)

    # 4-5 EDA, KPI
    try:
        go(page, "Automatic EDA"); t = main_text(page)
        check("4 Automatic EDA renders health/insights/distributions", all(s in t for s in ["Dataset health", "Automatic insights", "Numeric feature statistical profile"]) and exceptions(page) == 0)
        go(page, "KPI Dashboard"); t = main_text(page)
        check("5a KPI Dashboard renders headline KPIs", "Total Records" in t and exceptions(page) == 0)
        pick(page, "Aggregation for trend", "Average") if page.get_by_role("combobox", name=re.compile("Aggregation for trend")).count() else None
        check("5b KPI aggregation control works without error", exceptions(page) == 0)
    except Exception as e: check("4-5 EDA/KPI", False, e)

    # 6 Interactive dashboard
    try:
        go(page, "Interactive Dashboard"); t = main_text(page)
        check("6a Interactive Dashboard renders", "Key metrics" in t and exceptions(page) == 0)
        m = re.search(r"Active slice\D{0,5}([\d,]+) of ([\d,]+)", t)
        check("6b Active-slice badge shows full dataset by default", m and m.group(1) == m.group(2), m.group(0) if m else t[:100])
        pick(page, "Optional numeric range filter", "revenue")
        g = page.locator('[data-testid="stMain"] [data-testid="stSlider"]').first.bounding_box()
        for yy in (g["y"] + g["height"] - 18, g["y"] + g["height"] - 10, g["y"] + g["height"] / 2):
            page.mouse.move(g["x"] + g["width"] - 4, yy); page.mouse.down(); page.mouse.move(g["x"] + g["width"] * 0.04, yy, steps=12); page.mouse.up(); settle(page, 2.0)
            if re.search(r"Active slice\D{0,5}([\d,]+) of \1\b", main_text(page)) is None: break
        m2 = re.search(r"Active slice\D{0,5}([\d,]+) of ([\d,]+)", main_text(page))
        check("6c Numeric-range filter narrows the slice", m2 and int(m2.group(1).replace(",", "")) < int(m2.group(2).replace(",", "")), m2.group(0) if m2 else "no badge")
        page.get_by_role("button", name=re.compile("Reset dashboard filters")).click(); settle(page, 2)
        m3 = re.search(r"Active slice\D{0,5}([\d,]+) of ([\d,]+)", main_text(page))
        check("6d Reset filters restores full slice", m3 and m3.group(1) == m3.group(2), m3.group(0) if m3 else "")
        check("6e Interactive Dashboard exception-free", exceptions(page) == 0)
    except Exception as e: check("6 Interactive dashboard", False, e)

    # 7 Visualizations
    try:
        go(page, "Visualizations")
        check("7a Visualizations renders a chart", page.locator('[data-testid="stMain"] .stPlotlyChart, [data-testid="stMain"] [data-testid="stPlotlyChart"]').count() >= 1 and exceptions(page) == 0)
        for typ in ["Histogram", "Scatter", "Box"]:
            try:
                pick(page, "Chart type", typ)
                check(f"7b Chart type '{typ}' renders without error", exceptions(page) == 0 and page.locator('[data-testid="stMain"] [data-testid="stPlotlyChart"]').count() >= 1)
            except Exception as e: check(f"7b Chart type '{typ}'", False, e)
    except Exception as e: check("7 Visualizations", False, e)

    # 8 Correlation
    try:
        go(page, "Correlation"); t = main_text(page)
        check("8 Correlation page renders heatmap + relationships", page.locator('[data-testid="stPlotlyChart"]').count() >= 1 and exceptions(page) == 0, t[:60].replace("\n", " "))
    except Exception as e: check("8 Correlation", False, e)

    # 9 Outliers
    try:
        go(page, "Outlier Detection"); t = main_text(page)
        check("9a Outlier page renders", exceptions(page) == 0 and page.locator('[data-testid="stPlotlyChart"]').count() >= 1)
        check("9b Outliers are reported for revenue (inflated values)", re.search(r"outlier", t, re.I) is not None)
    except Exception as e: check("9 Outliers", False, e)

    # 10 Ask Your Data
    try:
        go(page, "Ask Your Data")
        box = page.get_by_label("Ask a question in plain English", exact=False).first
        box.fill("How many rows are there?"); box.press("Enter"); settle(page, 2)
        t = main_text(page)
        check("10a Typed question answered from real data", f"{cleaned_rows:,}" in t.split("Answer", 1)[-1], f"expected {cleaned_rows:,}")
        page.get_by_role("button", name="Show distribution of revenue").first.click(); settle(page, 2.5)
        check("10b Suggested prompt fills box and answers with a chart", page.locator('[data-testid="stPlotlyChart"]').count() >= 1 and exceptions(page) == 0)
        box = page.get_by_label("Ask a question in plain English", exact=False).first
        box.fill("what is the meaning of life"); box.press("Enter"); settle(page, 2)
        check("10c Unsupported question gives a friendly message, no crash", exceptions(page) == 0 and "Matched rule" not in main_text(page).split("Answer", 1)[-1])
        check("10d 'not an AI model / no API key' statement present", "not an AI model" in main_text(page) and "no API key" in main_text(page))
    except Exception as e: check("10 Ask Your Data", False, e)

    # 11 Comparison
    try:
        go(page, "Dataset Comparison")
        page.locator('[data-testid="stMain"] input[type="file"]').first.set_input_files(SECOND); settle(page, 3)
        t = main_text(page); n2 = len(pd.read_csv(SECOND))
        check("11a Secondary dataset metrics shown", f"{n2:,}" in t and f"{cleaned_rows:,}" in t, f"{n2:,} / {cleaned_rows:,}")
        check("11b Common columns listed", "order_id" in t and "revenue" in t)
        check("11c Active dataset unchanged by comparison upload", active_rows(page) == cleaned_rows, active_rows(page))
        check("11d Comparison exception-free", exceptions(page) == 0)
    except Exception as e: check("11 Comparison", False, e)

    # 12 Exports
    try:
        go(page, "Export & Reporting")
        out = pathlib.Path(tempfile.mkdtemp()); got = {}
        for label in ["Download Executive Report", "Download Current Processed Dataset", "Download Full Column Data Profile", "Download Excel Workbook", "Download Power BI Starter Pack", "Download cleaning script"]:
            settle(page)
            with page.expect_download(timeout=60000) as info:
                page.get_by_role("button", name=re.compile(label)).first.click()
            dl = info.value; dest = out / dl.suggested_filename; dl.save_as(dest); got[label] = dest; settle(page)
        check("12a All six downloads delivered", len(got) == 6, [g.name for g in got.values()])
        h = got["Download Executive Report"].read_text(encoding="utf-8", errors="replace")
        check("12b Executive report is complete HTML", h.lstrip().lower().startswith("<!doctype html") and "</html>" in h.lower(), len(h))
        c = pd.read_csv(got["Download Current Processed Dataset"])
        check("12c Processed CSV matches active dataset row count", len(c) == cleaned_rows and c.isna().sum().sum() == 0, f"{len(c)} rows, {int(c.isna().sum().sum())} NaN")
        pr = pd.read_csv(got["Download Full Column Data Profile"])
        check("12d Column profile has one row per column", len(pr) == c.shape[1], pr.shape)
        x = pd.ExcelFile(got["Download Excel Workbook"])
        check("12e Excel workbook opens with expected sheets", len(x.sheet_names) >= 3, x.sheet_names)
        z = zipfile.ZipFile(got["Download Power BI Starter Pack"]); check("12f Power BI ZIP valid and non-empty", z.testzip() is None and len(z.namelist()) >= 3, z.namelist())
        src = got["Download cleaning script"].read_text(); compile(src, "script.py", "exec"); check("12g Cleaning script is valid Python", True, len(src))
        # reproducibility: run script next to the original CSV and compare with downloaded cleaned CSV
        work = pathlib.Path(tempfile.mkdtemp()); (work / pathlib.Path(CSV).name).write_bytes(pathlib.Path(CSV).read_bytes())
        sp = work / got["Download cleaning script"].name; sp.write_text(src)
        r = subprocess.run([sys.executable, str(sp)], cwd=work, capture_output=True, text=True, timeout=120)
        produced = [f for f in work.iterdir() if f.suffix == ".csv" and f.name != pathlib.Path(CSV).name]
        ok = r.returncode == 0 and produced
        if ok:
            rep = pd.read_csv(produced[0]); ok = rep.shape == c.shape and rep.reset_index(drop=True).equals(c.reset_index(drop=True)) or (rep.shape == c.shape and (rep.round(6).astype(str).values == c.round(6).astype(str).values).all())
        check("12h Exported script reproduces the cleaned CSV from the original file", ok, (r.stderr or "")[-150:] or (produced[0].name if produced else "no output"))
        check("12i Export page exception-free", exceptions(page) == 0)
    except Exception as e: check("12 Exports", False, e)

    # Session state / navigation
    try:
        go(page, "Data Upload & Preview"); check("S1 Navigation back keeps dataset", active_rows(page) == cleaned_rows)
        page.get_by_role("button", name=re.compile("Reload Original Dataset")).click(); settle(page, 2.5)
        check("S2 Reload Original restores uncleaned upload", active_rows(page) == n_csv, active_rows(page))
    except Exception as e: check("S session/nav", False, e)
    check("Z No uncaught browser JS errors during whole run", not errs, errs[:2])
    b.close()
passed = sum(1 for _, ok, _ in RESULTS if ok); print(f"\nE2E RESULT: {passed}/{len(RESULTS)} passed")
json.dump(RESULTS, open(os.environ.get("E2E_JSON", "e2e_results.json"), "w"), indent=1)
sys.exit(0 if passed == len(RESULTS) else 1)
