# AnalyticsPro — Stage 3 report: Analytics screens redesign

Scope: Interactive Dashboard, Visualizations, Correlation & Relationships, Outlier Detection. Source of truth: Stage 2 ZIP. Visual reference: Stitch exports.

## 1. Files changed
| File | Why |
|---|---|
| `phase4/views/interactive_dashboard.py` | Target screen |
| `phase4/views/visualizations.py` | Target screen |
| `phase4/views/correlation.py` | Target screen |
| `phase4/views/outliers.py` | Target screen |
| `phase4/tests/test_analytics_screens.py` | New: 56 focused tests |
| `phase4/views/dashboard_ui.py` | **Exception (not on the allow-list).** It is the Interactive Dashboard's own presentation module (KPI-card HTML, CSS, palette). The cards, legend, pills and ring cannot adopt the shared tokens without editing it. Changed: colour constants now read from `TOKENS`/`CHART_COLORS`, KPI-card markup and CSS restyled. All public names, class names used by tests and HTML escaping are unchanged. |
| `phase4/.streamlit/config.toml` | **Exception.** Added `[theme] primaryColor = "#4f46e5"`. Streamlit's default red was visible on sliders, radios, checkboxes and multiselect tags. This is a one-line, app-wide colour change that also affects unrelated screens (in the direction of consistency). |
| `docs/STAGE3_REPORT.md` | This report |

Not changed: `app.py`, `views/common.py`, everything under `data/` and `utils/`, all other views, all existing tests.

## 2. Features preserved
- Every widget key (`linked_dash_*`, `vis_*`, `corr_*`, `outlier_col`, `outlier_method`, `iqr_mult`, `z_thresh`, `smart_rec_apply_*`) and every route/session-state key.
- All filters, aggregation, trend grains, custom KPI cards, custom charts (10 types), Smart Dashboard Builder (build/hide/download), reset, filtered CSV/Excel export.
- All 8 manual chart types and their controls, Smart Visual Recommendations (apply + inline previews).
- 3 correlation methods, threshold, colour scale, ranked pair table, pair inspector with OLS trendline when `statsmodels` is installed.
- IQR and z-score detection, bounds, box plot, histogram with bounds, first-100 outlier records. Metric labels are unchanged.
- No backend calculation, chart builder or data function was touched.

## 3. UI improvements
- Duplicate in-page titles removed (`st.subheader`, the dashboard's own "Dashboard" title); each screen uses the shared page intro like Stage 2.
- Shared components throughout: `render_section_heading`, `card_container`, `badge_html`, `callout_html`, `style_figure`, `goto_page_button`.
- Interactive Dashboard: palette moved onto the design tokens (surface `#f8f9ff`, indigo/teal/amber/rose), KPI cards with label + tinted icon + 32px tabular value + change pill, section hierarchy, "Active slice" badge, card-wrapped filters/customize/smart builder/records, primary "Build dashboard" button, side-by-side download buttons, 1-column KPI grid at ≤640px, duplicate in-chart titles hidden on titled cards, off-palette chart colours replaced.
- Visualizations: recommendation cards with chart-type badges; "Chart studio" two-column layout (configuration panel + chart card); controls stacked in the panel.
- Correlation: feature chips, three summary metrics, heatmap and ranked pairs side by side, inspector with controls beside the plot, table height fits its rows, link to Outlier Detection.
- Outliers: method/bounds/status badges, charts in cards, brand-coloured bound lines, record-count caption, link to Data Preparation when records are flagged.
- All Plotly figures get the shared font, palette and grid.

## 4. Tests executed (exact results)
Run from `phase4/`:
- Baseline before edits: `pytest -m "not browser"` → **859 passed, 5 deselected**.
- After: `pytest -m "not browser"` → **915 passed, 5 deselected** (+56 new, 0 failures).
- `ruff check app.py views data utils` → All checks passed.
- `python -m pyflakes app.py views data utils tests` → no output (clean).
- `python -m mypy app.py views data utils --ignore-missing-imports` → Success: no issues found in 34 source files.
- `coverage run --source=data,utils … ; coverage report` → **95%** total (target ≥95% data/utils met). The app/views coverage command from the guide was not run.
- `pip-audit -r requirements.txt` → No known vulnerabilities found.
- Browser tests (`RUN_BROWSER_TESTS=1 pytest -m browser`): **3 failed, 2 passed**. The 3 failures (`test_sidebar_text_has_wcag_aa_contrast_before_and_after_upload`, `test_sidebar_can_be_reopened_after_closing` ×2) fail identically on the untouched Stage 2 code, so they pre-date this work; I did not investigate their cause.
- Python 3.13.18 was used (CI matrix is 3.12/3.13); 3.12 was not run.

Manual browser check (Playwright/Chromium, `retail_sales_messy.csv`): all four screens loaded with no page errors at 1440px; Interactive Dashboard also checked at 390px with the sidebar hidden by injected CSS (the sidebar overlay could not be collapsed by my script, so the phone check covers main content only, and only the Dashboard was reviewed at phone width). Other screens were viewed at desktop width only. This is a visual spot check, not a full cross-browser or accessibility audit.

## 5. Known issues and limitations
- Outlier Detection defaults its target column to the first numeric column, which can be an ID such as `order_id`. Existing behaviour (`exclude_id=False`), left as is.
- The handoff guide describes a correlation "Role Shield", an outlier download button and capping/trimming in Data Preparation; none exist in this codebase. I did not add them. The new callout on Outlier Detection describes only what Data Preparation really offers.
- Custom charts in the Dashboard's "Choose charts" use the chart builder's default colours (not the indigo palette) because colour options differ per chart type and I did not change chart behaviour.
- The long recommendation list pushes the Chart studio below the fold on Visualizations (the expander is open by default, as before).
- Existing Stage 1/2 sidebar spacing is unchanged.

## 6. Differences from the Stitch references
Layout and hierarchy were followed; features that do not exist in the app were not invented. Not implemented: export chart PNG/SVG, copy Plotly JSON, aggregated groupby matrix, sort-order and direct-label toggles, reset canvas, regression equation/R²/p-values and per-pair prose, high-leverage outlier callout, flagged-record search/severity filters/batch actions/pagination, winsorization preview, "Calculation settings", 3-month moving-average overlay, segment target bars, header search/health chip. Recommendations are stacked cards (not 3-across) to keep the original order and inline previews. Stitch's Pearson/Spearman/Kendall tab control and chart-type icon grid were kept as the existing select boxes. The Stitch correlation heatmap is cell-styled; the app keeps the Plotly heatmap and its scale options.

## 7. Backend confirmation
No file under `data/` or `utils/`, no `app.py` and no `views/common.py` was modified (verified by a recursive diff against the Stage 2 ZIP: only the files in section 1 differ).
