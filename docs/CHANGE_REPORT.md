# Change report

Baseline: `AnalyticsPro_fixed.zip` (the upload for this pass: the original project plus the earlier one-line bar-chart fix and its test). Everything below was verified by the checks in [VALIDATION_REPORT.md](VALIDATION_REPORT.md). The uploaded zip itself is the rollback copy; the work was also tracked in a local git repository (not included in the final zip) so every change could be diffed.

## 1. Summary of the original project

AnalyticsPro is a Streamlit data-exploration app: CSV/Excel upload, data cleaning, automatic EDA, KPI and interactive dashboards, chart builders, correlation, outliers, dataset comparison, and CSV/Excel/Power BI/HTML exports. Architecture: `app.py` router -> `views/` (one module per page) -> `data/` (pure logic) and `utils/`. It started this pass at 295 passing tests, a 75.5/100 score, and a list of known weaknesses.

## 2. Files

**Added (20):** `data/aggregation.py`, `data/columns.py`, `data/charts.py`, `data/analyst.py`, `data/script_export.py`, `data/dashboard_cards.py`, `views/dashboard_ui.py`; `tests/test_script_export.py`, `tests/test_dashboard_cards.py`, `tests/test_dashboard_ui.py`, `tests/test_aggregation.py`, `test_columns.py`, `test_charts.py`, `test_analyst.py`, `test_import_options.py`, `test_ask_and_import_pages.py`, `test_docs_in_sync.py`; `scripts/make_chart_matrix.py`; `phase4/ruff.toml`; and docs `CHART_COMPATIBILITY_MATRIX.md`, `FEATURE_OWNERSHIP_MATRIX.md`, `LICENSE_DECISION.md`, `NOTEBOOK.md`, `CHANGE_REPORT.md`, `VALIDATION_REPORT.md`.

**Modified (main ones):** `app.py`, `data/loader.py`, `data/intent.py`, `data/recommender.py`, `data/cleaner.py`; `views/analyst.py` (rewritten), `views/interactive_dashboard.py` (rewritten), `views/eda.py` (split), `views/export.py`, `views/visualizations.py`, `views/upload.py`, `views/data_prep.py`, `views/kpi.py`, `views/comparison.py`, `views/common.py`; `utils/helpers.py`, `utils/session_state.py`; type hints/docstrings/import order in the other `data/` and `utils/` modules; `.github/workflows/ci.yml`, `.streamlit/config.toml`, `requirements.txt` (pins), `requirements-dev.txt`, `README.md`, `docs/PROJECT_SCORECARD.md`; the eight older reports were folded into `docs/HISTORY.md` and removed.

**Renamed:** the page "AI Data Analyst" is now "Ask Your Data" (the old route name still works as an alias).
**Removed:** the eight outdated reports (`CLEANUP_REPORT`, `FIXES_AFTER_REVIEW`, `FULL_PROJECT_AUDIT`, `IMPLEMENTATION_REPORT`, `PROJECT_IMPROVEMENT_ROADMAP`, `PROJECT_REVIEW`, `TESTING_REPORT`, `UPGRADE_NOTES`; summarised in `docs/HISTORY.md`). **Moved:** the notebook to `archive/`; `tests/test_regressions_stage1.py` renamed `test_regressions.py`. No application code or test was deleted; one line in `tests/conftest.py` (the page list) was updated for the rename; six lines were appended to `tests/test_helpers.py`.

## 3. Issues found and fixed

| # | Issue | Fix | Regression test |
|---|---|---|---|
| 1 | Bar chart with categorical X and a different colour column showed an error (fixed earlier in the baseline) | Group keeps the colour column; grouped bars | `test_regression_bar_with_categorical_x_...`, `test_custom_bar_chart_supports_color_...` |
| 2 | Chart-building logic duplicated in 4 places, with different aggregation rules | One builder `data/charts.py` + `data/aggregation.py` | 190 chart tests, 26 pinned outcomes |
| 3 | Invalid chart choices could produce raw errors | `ChartConfigError` messages; `safe_build_chart` never raises | `test_safe_build_never_raises_on_garbage`, edge-dataset tests |
| 4 | Suggested prompts and chart defaults used the first numeric column even if it was an ID | Column roles (`data/columns.py`); suggestions from schema, each validated against the router | `test_suggestions_never_use_identifier_columns`, `test_every_suggestion_is_answerable...` |
| 5 | Page claimed to be an "AI Data Analyst" | Renamed; on-page text says it is rule-based and calls no service | `test_page_states_it_is_rule_based_and_not_ai` |
| 6 | "How many records per region?" was answered as a plain row count | Category-aware routing precedes the row-count rule | `test_routing`, `test_value_counts_answer_matches_pandas` |
| 7 | Smart builder and KPI cards defaulted to ID columns | They use measure columns first | `test_smart_dashboard_never_uses_identifier_columns` |
| 8 | Only the first Excel sheet could be loaded | Worksheet picker; only that sheet is parsed; helpful errors for unknown/empty sheets | `test_any_sheet_can_be_chosen...`, `test_only_the_requested_sheet_is_parsed` |
| 9 | Leading zeros (`00123`) lost in CSV **and Excel text cells** | CSV: digit-only columns with a leading zero stay text; Excel: text cells no longer pass through pandas' type guessing | `test_leading_zero_*`, `test_excel_text_cells_keep_leading_zeros` |
| 10 | Decimal commas (`12,50`) stayed text | Auto-detect when unambiguous; user setting for ambiguous values like `1,234`; mixed/ambiguous columns untouched and noted | `tests/test_import_options.py` (decimal section) |
| 11 | Numbers such as `1,234` or `12,50` were detected as dates | Separated-number guard in date detection | `test_separated_numbers_are_not_mistaken_for_dates` |
| 12 | Raw exception text shown to users (upload, comparison, type conversion) | Friendly messages on the page; routine failures log only the exception type, and unexpected upload errors are logged with a traceback to the server log, never to the page | `test_bad_uploads_show_a_friendly_error...` |
| 13 | Stale dashboard selections after loading a new file | All `linked_dash_*` state cleared on a new upload | `test_new_upload_clears_dashboard_selections...` |
| 14 | Unused `statsmodels.api` import and unused `metrics` variable | Feature check via `find_spec`; variable removed with the rewrite | pyflakes clean |
| 15 | `use_container_width` deprecation (16 uses) | `width="stretch"`; none left | grep + suite |
| 16 | Import notes could render user text as Markdown | `escape_markdown` | `test_import_notes_render_user_text_literally` |
| 17 | 37 `pip-audit` advisories in Pillow 12.3.0 (via Streamlit 1.63.0, which capped Pillow below 13) | Pins moved to `streamlit==1.66.1` and `pillow>=13.0.0,<14`; full suite re-run on them; `pip-audit` clean | whole suite on the new pins |
| 18 | The longest functions: 210-line recommender, 194-line EDA page | One helper per section; recommender output compared identical on 6 datasets | `test_recommendation_output_is_pinned_for_the_shipped_samples` |
| 19 | `views/` had no type hints; default-binding lambdas in the export page defeated type checking | Hints added; lambdas simplified; mypy now covers `app.py`, `views/`, `data/`, `utils/` (31 files); all 231 top-level functions are fully annotated | mypy in CI and locally |
| 20 | A weak correlation (e.g. +0.2) was labelled "Moderate Negative" on the Correlation page whenever the threshold was set below 0.3; the pair picker broke on column names containing " vs " | `correlation_strength` / `correlated_pairs` extracted to `data/profiler.py` (Weak/Moderate/Strong bands, sign from the value); picker uses indexes | `test_correlation_strength_labels_regression`, `test_correlated_pairs_*` |
| 21 | Six functions of 74-133 lines (visualizations page and its recommendation applier, correlation page, KPI page, `fill_missing_values`, `validate_dataframe`) | One helper per responsibility; the KPI page now uses the shared aggregation helpers, so infinite values are ignored there as on the dashboard | existing suites + new profiler tests |
| 22 | **Cross-session data leak:** the default `cleaning_history` list (and other default lists/dicts) was one object shared by all sessions in the server process, so one user's cleaning steps could appear in another user's session | Defaults are deep-copied per session; history is appended without mutating in place | `test_session_defaults_are_not_shared_between_sessions`, `test_default_containers_are_distinct_objects_per_session` (both fail on the old code) |
| 23 | Excel "numbers stored as text" were converted before blank rows were removed, so whole numbers became floats | Convert after blank-row removal | `test_excel_whole_number_text_column_stays_integer_...` |

## 3b. New feature: reproducible cleaning script

The Export & Reporting page now offers **Download cleaning script (.py)** with an in-page preview. The importer records how a file was read (delimiter, encoding, sheet, leading-zero columns, decimal-comma columns, date columns) and every Data Preparation action is recorded in structured form (`data/script_export.py`). The generated script is plain pandas and does not need the app. Steps that cannot be exported are kept as clearly marked comments and listed on the page. It is verified by executing the script and comparing the result with the app's own output (`tests/test_script_export.py`, 38 tests).

## 3c. Dashboard redesign (card layout)

The Interactive Dashboard was restyled to follow a reference dashboard image supplied by the owner (layout and look only, not its payroll content): four KPI cards with coloured icon circles and a change-vs-full-dataset figure; a composition donut with a legend; a data-quality checklist with Good/Review/Fix pills; a completeness progress ring; a latest-records table; a segment bar chart; and a trend card. The sidebar became navy with the current page highlighted. The numbers come from the new `data/dashboard_cards.py` (pure pandas, unit-tested); the markup and CSS from `views/dashboard_ui.py` (all user text escaped; every text/background colour pair is checked for WCAG AA contrast by a test). All previous controls, widget keys and sections are kept (filters, custom KPI cards and charts, Smart Dashboard Builder, filtered table and downloads). **Not verified:** how it looks in a real browser. Only automated page tests and a contrast calculation were possible here.

## 4. Behaviour changes you should know about

- Dashboard custom charts follow the dashboard's **Aggregation** setting (they previously always averaged).
- Dashboard bar charts with a **date** X aggregate per date (previously one bar per row); bars with a colour column are **grouped** (previously stacked).
- Colouring/grouping by a column with more than 30 distinct values is refused with a message.
- `Sum` of a group whose values are all missing is now missing rather than 0.
- Excel: completely blank rows and empty unnamed columns are removed (and reported); numbers stored as text are still converted.
- A file with headers but no rows is now rejected with a message instead of loading an empty dataset.
- The dashboard's top metrics row is now four HTML KPI cards instead of five Streamlit metrics, and the "Explore" bar/trend charts moved into the card layout. A filtered view having fewer rows than the full dataset is shown as neutral, not as bad news; only data completeness is coloured good or bad.
- Excel text-number columns become integers (not floats) when blank rows are present.
- Loading is about 2x slower for big CSVs (see validation report) because of the leading-zero check.

## 5. Architecture and UI

`aggregation`, `columns`, `charts`, `analyst` are new pure modules; views call them. `app.py` has helper functions for navigation, upload and status. The dashboard page has one helper per section. The Data Preparation columns tab has one helper per action. UI additions: "Import options" in the sidebar, "Import notes" on the upload page, "What can I ask?" on Ask Your Data, page captions that state each page's purpose, keyboard focus ring, friendly messages.

## 6. Testing, dependency and security findings

See VALIDATION_REPORT.md. In short: 765 tests pass; 95%/90% coverage; `pip-audit` first reported 37 advisories (all Pillow 12.3.0, pulled in by Streamlit 1.63.0), which the verified pin change to Streamlit 1.66.1 + Pillow 13 cleared.

## 7. Remaining limitations and blockers

- **Remote CI has not run** (no GitHub access); local equivalents passed. **Browser tests did not run**: Chromium cannot be downloaded here (`getaddrinfo ENOTFOUND cdn.playwright.dev`). **Python 3.13 untested** (only 3.12 installed).
- **No license** was added: owner decision ([LICENSE_DECISION.md](LICENSE_DECISION.md)).
- **No demo GIF/new screenshots**: no browser was available to capture genuine ones.
- No function is longer than 65 lines now, but `app.py` (402 lines) and a few helper-heavy modules are still large; nested/inner functions are not type-annotated.
- The dependency pins changed (Streamlit 1.63.0 -> 1.66.1): tested here, but anyone with a different environment should reinstall from `requirements.txt` and run the suite.
- Heuristics can be wrong: a whole-number ID column with no ID-like name and random values looks like a measure; ambiguous decimal values are left as text unless you choose a setting.
- Accessibility beyond the focus ring was not tested.
