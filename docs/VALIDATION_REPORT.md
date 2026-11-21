# Validation report

Everything marked **Verified locally** was actually run in this environment during this pass. Nothing here comes from a remote CI run.

## Environment

| Item | Value |
|---|---|
| OS / Python | Linux, Python 3.12.3 (the only interpreter available; 3.13 was **not** tested) |
| Install | Fresh virtual environment, `pip install -r requirements-dev.txt` (+ mypy, ruff, pip-audit): succeeded; `pip check` reported "No broken requirements found" |
| Key versions | streamlit 1.66.1, pandas 3.0.5, numpy 2.5.2, plotly 7.0.0, pyarrow 25.0.1, openpyxl 3.1.5, xlrd 2.0.2, statsmodels 0.15.0, pillow 13.0.0, pytest 9.1.1, mypy 2.4.0, ruff 0.17.2 |
| History | The first validation run used the originally pinned Streamlit 1.63.0 / Pillow 12.3.0 (651 tests passed at that time). The pins were then raised to Streamlit 1.66.1 / Pillow 13 and **everything below was re-run on the new pins in a second fresh environment** |

## Commands run (from `phase4/` unless noted)

```bash
python -m pyflakes app.py views data utils tests
ruff check app.py views data utils
python -m mypy app.py views data utils --ignore-missing-imports
coverage run --source=data,utils -m pytest -m "not browser" --junitxml=junit.xml && coverage report
coverage run --source=app,views -m pytest -m "not browser" && coverage report
RUN_BROWSER_TESTS=1 python -m pytest tests/browser -m browser
streamlit run app.py --server.headless true --server.port 8611 --browser.gatherUsageStats false   # then GET /_stcore/health and /
pip-audit -r ../requirements.txt          # run from the repository root path
python ../scripts/make_chart_matrix.py
```

## Results

| Check | Result | Status |
|---|---|---|
| pyflakes (app, views, data, utils, tests) | no findings | Verified locally |
| ruff (pycodestyle errors, pyflakes, import order, bugbear, pyupgrade, simplify) | all checks passed | Verified locally |
| mypy on `app.py`, `views/`, `data/`, `utils/` (34 files) | no issues | Verified locally |
| Full non-browser suite (unit + integration + Streamlit AppTest) | **765 passed, 0 failed, 0 errors, 0 skipped**, 5 browser tests deselected; ~190 s | Verified locally (fresh venv, final pins) |
| Baseline for comparison (uploaded zip) | 295 passed, 0 failed | Verified locally |
| Coverage, `data/` + `utils/` (2,030 statements) | **95%** (95 missed) | Verified locally |
| Coverage, `app.py` + `views/` (1,540 statements) | **90%** (158 missed) | Verified locally |
| Chart cross-product (`tests/test_charts.py`) | 190 tests pass: chart type x X x Y x aggregation x colour, 8 edge datasets x 10 chart types, 26 pinned outcomes, value-correctness checks | Verified locally |
| Chart compatibility matrix | 70 scenarios: 43 supported, 27 refused with a message, 0 crashes (`docs/CHART_COMPATIBILITY_MATRIX.md`, generated from the code and checked by a test) | Verified locally |
| Every page x every shipped sample file | 3 files x 11 pages render without exception | Verified locally |
| Import regressions (`tests/test_import_options.py`, page-level import tests) | all pass: leading zeros, decimal commas, worksheets, delimiters, encodings, duplicate headers, malformed rows, empty file | Verified locally |
| App startup from the fresh venv (final pins) | `/_stcore/health` returned `ok`, `/` returned HTTP 200, no error lines in the server log | Verified locally |
| Loader benchmark, 300,000 rows x 8 columns (25.3 MB), one run each | original 0.57 s -> new 1.11 s | Verified locally; single run, not a statistical benchmark |
| `pip-audit` on the final `requirements.txt` | **No known vulnerabilities found.** (Before the pin change: 37 advisories, all in Pillow 12.3.0) | Verified locally (PyPI reachable) |
| Generated cleaning script | 38 tests *execute* the generated script on the original file and compare with the app's own result (every operation, CSV and Excel, several delimiters and encodings, and steps done through the real UI buttons) with `assert_frame_equal`; all pass | Verified locally |
| Dashboard redesign | 61 tests: card numbers (KPI deltas, composition shares, quality checks, ring), HTML escaping of hostile column names/values, 15 text/background colour pairs at WCAG AA (lowest 5.66:1), every previous control still present, degraded datasets, active-page highlight | Verified locally; **appearance in a real browser not verified** |
| Refactor equivalence | `generate_visual_recommendations` output compared before/after the split on 6 datasets: identical; pinned by a golden test | Verified locally |

## Dependency audit detail

The only advisories found were in Pillow 12.3.0, a transitive dependency of Streamlit 1.63.0 (which required `pillow<13`). Streamlit 1.66.1 allows Pillow 13, so the pins were changed to `streamlit==1.66.1` plus `pillow>=13.0.0,<14`. This was **tested rather than assumed**: the whole suite (765 tests at the final run) passes, the app starts and `pip-audit` is clean on that set. The audit covers advisories known to PyPI's database at the time of the run; it is not a guarantee that no other vulnerabilities exist, and new ones can appear later.

## Checks not executed, and why

| Check | Reason |
|---|---|
| Remote GitHub Actions run (3.12 and 3.13) | No GitHub access from this environment. The workflow was updated and its commands were run locally on 3.12. Run `git push` and confirm all jobs are green. |
| Browser tests (5, Playwright) | `playwright install chromium` fails here: `getaddrinfo ENOTFOUND cdn.playwright.dev`. With the tests selected they skip (5 skipped). |
| Python 3.13 | Not installed here. |
| Visual check of the dashboard redesign and the keyboard focus ring | Needs a browser. The CSS is present; its appearance is unverified. |
| Keyboard-only and screen-reader walkthrough | Needs a browser and assistive technology. |
| Files above 300,000 rows; memory profiling | Not measured. |
| Legal review of dependency licenses | Not a technical check. |

## Existing failures

None remained at the end of the run. During development the new tests found and fixed defects (listed in CHANGE_REPORT.md section 3); those were newly *discovered*, not newly *introduced*, except one first-draft classifier error (integer salaries treated as identifiers) that was caught by its test before the final run.

## Reproduce

```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cd phase4
python -m pytest -m "not browser"                         # about 2 minutes
streamlit run app.py
```
