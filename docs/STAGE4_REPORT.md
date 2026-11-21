# AnalyticsPro — Stage 4 report: Advanced screens redesign

Scope: **Ask Your Data**, **Dataset Comparison**, **Export & Reporting**. Source of truth: `AnalyticsPro_Stage3_AnalyticsScreens.zip`. Visual reference: the Stitch exports (used for layout and hierarchy only).

## 1. Files changed
| File | Why |
|---|---|
| `phase4/views/analyst.py` | Target screen |
| `phase4/views/comparison.py` | Target screen |
| `phase4/views/export.py` | Target screen |
| `phase4/tests/test_advanced_screens.py` | New: 41 focused tests for the three screens |
| `docs/STAGE4_REPORT.md` | This report |

No file outside the allow-list was changed. A recursive `diff -rq` against the Stage 3 ZIP shows exactly the files above and nothing else.

## 2. Features preserved
**Ask Your Data**
- Rule-based question answering through `answer_question`, automatic insights, the four dataset-quality metrics (labels unchanged), the "What can I ask?" operation list, suggested prompts, the question box and every answer type: success/info/warning message, table, bar-from-table and chart (histogram, bar, line, scatter, with the OLS trendline when `statsmodels` is installed).
- Widget keys `ai_query_input` and `sug_btn_<n>`; the public function `render_chart_from_intent(df, intent)`; the statements "not an AI model" and "no API key" (still `st.caption`).
- Suggested prompts still write the question box before it is created (script order preserved).

**Dataset Comparison**
- Uploader key `second_dataset_file` (same label and file types), primary and secondary `st.metric` calls with identical labels, values and deltas, the sorted common-column list (still rendered with `st.write` as a backtick list), and the same error messages (`ValueError` and unexpected-error paths) and info/warning messages.

**Export & Reporting**
- All six downloads with identical labels, file names, MIME types, `type`, `width` and help text: Executive Report (HTML, primary), processed CSV, column profile CSV, Excel workbook, Power BI starter pack (ZIP), cleaning script (`export_cleaning_script`).
- Deferred data: files are still built only when a button is clicked (`data=lambda`). A test enforces that rendering the page calls none of the file builders.
- Script preview expander ("Preview the script"), the step-count caption, the "could not be exported" warning, and the openpyxl-missing warning.

## 3. UI improvements
All three screens use the Stage 1–3 shared components (`render_page_intro`, `render_section_heading`, `card_container`, `badge_html`, `notice_html`, `insight_grid_html`, `insight_html`, `style_figure`, `CHART_COLORS`). No CSS and no design tokens were added.

**Ask Your Data**
- The duplicate `st.subheader` is replaced by the shared page intro; the "local and rule-based, not an AI model" statement sits in its own card at the top.
- "Dataset at a glance": the four metrics, then data-grounded insights as a responsive card grid (bold and `column` names rendered, all text escaped).
- "Ask a question" card: the input first, suggested prompts below it (two per row).
- "Answer" card: the question is echoed with a "Matched rule: …" badge taken from the real handler (omitted for unsupported questions), then the message, table and chart. Before any question, an info notice explains where answers will appear.
- Side panel: "What can I ask?" (the existing operations) and "Column roles" (existing `classify_columns`; identifiers highlighted; first 24 columns shown). On narrow screens the panel stacks below the main column.
- Charts use the shared font, grid and palette; the bar chart colour scale is indigo instead of Plotly's blues.

**Dataset Comparison**
- Upload section in a card with a note that the secondary file is read for the comparison only.
- Primary and secondary cards, each headed by a Primary/Secondary badge and the escaped file name.
- A row of difference pills (rows, columns, missing cells, health) with a caption explaining the colours: green = better, red = worse, grey = no judgement.
- "Common Columns" card with exact-name-match explanation; the warning for no overlap is unchanged.

**Export & Reporting**
- Header badge with the dataset name and size; sections for report, dataset/profile, Excel/Power BI and script.
- Each export is a card with a title, a format badge (HTML, CSV, XLSX, ZIP, PY), a plain description and an "Includes" line. The "Includes" text only lists what the code produces (sheets in the workbook, files in the zip).
- Button hierarchy: only the Executive Report is primary (indigo); everything else is secondary. Buttons stay full-width in their card.
- The Power BI "not a native .pbix file" explanation is now a visible info notice rather than a caption.

## 4. Tests executed (exact results)
Run from `phase4/` with Python 3.12.3, Streamlit 1.66.1, in an isolated virtual environment:

| Command | Result |
|---|---|
| Baseline, before edits: `python -m pytest -m "not browser"` (unmodified Stage 3) | **915 passed, 5 deselected** |
| `python -m pytest tests/test_advanced_screens.py` | **41 passed** |
| `python -m pytest -m "not browser"` (final code) | **956 passed, 5 deselected** (+41 new, 0 failures) |
| `ruff check app.py views data utils` | All checks passed |
| `python -m pyflakes app.py views data utils tests` | no output (clean) |
| `python -m mypy app.py views data utils --ignore-missing-imports` | Success: no issues found in 34 source files |
| Import check (`views.analyst`, `views.comparison`, `views.export`, `views.common`) | ok |
| `streamlit run app.py --server.headless true` | started; `/_stcore/health` returned HTTP 200 |

The new tests cover: all three pages with a normal dataset, an empty dataset, a categorical-only dataset and a single-row dataset; absence of unsupported claims in page text; balanced generated HTML; the pages not modifying the dataset; HTML escaping of column names, file names and typed questions; the Ask flow (empty state, typed question, suggestion click, unsupported question, chart question); the comparison metrics, deltas, difference-pill colours, common columns, no-overlap warning, an invalid file and the active dataset staying unchanged; and the export page's exact download list, button hierarchy, deferred file building, Power BI wording, step count/unexportable warning, and the openpyxl-missing path.

**Not run:**
- **Browser tests** (`RUN_BROWSER_TESTS=1 pytest -m browser`): no browser could be installed here (the Playwright download host and the Ubuntu package are unreachable). The Stage 3 report records 3 pre-existing browser failures (sidebar contrast/reopen); I could not re-check them. The browser download test searches for the button labels listed in section 2, which are unchanged.
- **No screenshots** were taken, so none of the visual changes has been seen rendered.
- Coverage, `pip-audit`, and Python 3.13 were not run in this stage.

## 5. Known issues and limitations
- Layout, spacing and the narrow-screen stacking of the Ask Your Data side panel are untested visually. Please open the three pages at desktop and phone width.
- Ask Your Data no longer uses expanders for the insights and the operation list; both are now always visible, which makes the page longer.
- Suggested prompts now sit two per row (they were three) because they live in the wider-than-half main column.
- The question box appears above the prompts on screen but is created after them in code (a container slot). This keeps the original click-to-fill behaviour; do not reorder the code without keeping that in mind.
- File sizes are not shown on the Export cards: showing them would mean building every file on each page load, which would remove the deferred downloads.
- `st.bar_chart` (used for `bar_from_table` answers) is native Streamlit and takes its colour from the app theme (indigo since Stage 3).
- The response text of an answer (`answer.message`) is still rendered by the native alert widgets, so its typography follows Streamlit's defaults.

## 6. Differences from Stitch
Followed: page hierarchy, card layout, query box with prompt chips, answer cards, taxonomy/guide side panel, primary/secondary dataset cards, delta strip, export-module card grid and download-button hierarchy.

Not implemented because the application has no such feature: "100% Local engine / zero telemetry / zero hallucination" marketing claims, execution times, "Matched AST" and match percentages, query history and Clear History, Copy Plotly Spec, Export Table to CSV, Open in Visualizations from an answer, an in-page Role Protection Guard demo, Switch Primary/Secondary, Export Comparison Audit, KS test and drift charts, the schema drift matrix, verdict and promote-baseline actions, Batch Export (ZIP), Audit Export History, Copy Script / Open in Colab, the dark script panel with latency/checksum tiles, file-size and row-count statistics on export cards, PDF export, DAX/M-query, the visual asset gallery, the governance/signature log and ISO claims. The Excel card is a single workbook card without Stitch's formula claims. The Power BI card describes a starter pack, not a `.pbit`/`.pbix` template.

## 7. Backend confirmation
No file under `data/` or `utils/`, no `app.py` and no `views/common.py` was modified (byte-identical to the Stage 3 ZIP; verified with `cmp` and `diff -rq`). No calculation, router, aggregation, export builder or script generator was touched. No dependency was added.

## 8. Exceptions to the allowed file list
None.
