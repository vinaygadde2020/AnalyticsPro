# Project Scorecard

Same ten categories and weights as before. A point is credited only for work that was implemented **and** verified here; anything blocked by the environment earns nothing. Half-point steps are judgement, not measurements.

**Result: 76.0 -> 88.0 / 100 (Very good).** *(The previous scorecard was reported as 75.5, but its ten category scores add up to 76.0; that was an addition error and is corrected here. The improvement is +8.5 points from 76.0.)* Rating bands: 70-79 Good, 80-89 Very good. The 85 target is met *only on locally verified evidence*: remote CI and the browser tests have still not run, and the score would drop if they exposed problems. What is left is listed at the end.

| # | Category | Max | Before (76.0) | Now | Main remaining deduction |
|---|---|---:|---:|---:|---|
| 1 | Idea and usefulness | 10 | 7.0 | 8.0 | Still a general-purpose EDA tool; the reproducible-script export is the differentiator, but nobody has used it yet |
| 2 | Architecture | 15 | 12.5 | 14.5 | `app.py` is 402 lines; longest function is 65 lines (`parse_chart_intent`) |
| 3 | Features and completeness | 15 | 11.5 | 13.5 | Pages are differentiated, not merged; the script covers Data Preparation actions only (not charts or filters) |
| 4 | Code quality | 10 | 6.5 | 9.0 | All 231 top-level functions are fully annotated; inner functions and some `list`/`dict` types are loose |
| 5 | Functional correctness | 15 | 12.5 | 14.5 | Heuristics (ID detection, ambiguous decimals) can still guess wrong; documented |
| 6 | UI/UX | 10 | 7.0 | 7.5 | Card-style dashboard redesign and focus ring added but **not verified in a browser**; keyboard/screen-reader use untested |
| 7 | Performance | 5 | 4.0 | 4.0 | Loading is ~2x slower than before (0.57 s -> 1.11 s for 25 MB); larger files unmeasured |
| 8 | Security and reliability | 5 | 3.5 | 4.5 | Audit is clean today but is a point-in-time check; no penetration-style testing |
| 9 | Testing | 10 | 8.0 | 8.5 | CI never ran remotely; browser tests and Python 3.13 not run here |
| 10 | Documentation and portfolio | 5 | 3.5 | 4.0 | No license (owner decision), no demo GIF |
| | **Total** | **100** | **76.0** | **88.0** | |

## Evidence

1. **Idea 7.0 -> 8.0.** The misleading "AI" label is now accurate ("Ask Your Data", with an on-page statement that it is rule-based), each page has a stated purpose, and the app now has a genuinely distinctive capability: it exports a standalone pandas script that reproduces the import and all cleaning steps. Not higher: no real users, and the script covers cleaning only.
2. **Architecture 12.5 -> 14.5.** Four new Streamlit-free modules (`aggregation`, `columns`, `charts`, `analyst`) replaced logic repeated across five pages; `app.py` `main` (127 lines) became small helpers; the dashboard's long render function became a dozen helpers; every function that was over 70 lines (recommender 210, EDA page 194, visualizations page 133, correlation 89, fill_missing_values 87, ...) was split by responsibility, the recommender output being proven identical on 6 datasets and pinned by a golden test. Longest function is now 65 lines. Deductions: `app.py` grew 340 -> 402 lines because of the import options.
3. **Features 11.5 -> 13.5.** New: **reproducible cleaning script export** (all 10 Data Preparation operations plus the file import, with an in-page preview), worksheet picker, decimal-separator setting, leading-zero preservation, import notes, schema-aware suggestions, "what can I ask" help, record counts per category, column-type listing. Nothing removed. The script is verified by executing it and comparing with the app's own output (38 tests, CSV and Excel, through the real UI buttons).
4. **Code quality 6.5 -> 9.0.** pyflakes, ruff and mypy (31 files, including `views/`) are clean; no deprecated `use_container_width` left (16 -> 0); the three places that showed raw exception text now show friendly messages and log the detail; docstrings on all `data/`+`utils/` functions; all 231 top-level functions fully type-annotated; unused code removed. Not higher: inner functions are unannotated, many types are the loose `list`/`dict`, and ruff now also enforces bugbear, pyupgrade and simplify rules.
5. **Correctness 12.5 -> 14.5.** Defects found *by the new tests or while refactoring* and fixed with regression tests: (a) bar chart with a different colour column (earlier), (b) numbers like `1,234` detected as dates, (c) Excel text cells lost leading zeros, (d) "How many records per region?" answered as a plain row count, (e) integer columns such as `salary` misclassified as identifiers in the first draft of the classifier, (f) a weak correlation labelled "Moderate Negative" and a pair picker that broke on names containing " vs ", (g) **default session lists shared between sessions, which could leak one user's cleaning history to another** (the two regression tests fail on the old code), (h) Excel whole-number text columns turning into floats. The Smart builder and KPI defaults no longer pick ID columns. Open: ambiguous or random-valued identifiers; no real-browser verification.
6. **UI/UX 7.0 -> 7.5.** Friendly messages instead of raw errors, import options, clearer page captions, focus-ring CSS, and the card-style dashboard redesign (navy sidebar, KPI cards, donut, quality checklist, progress ring) whose colour pairs are proven WCAG AA by a test. The browser suite could not run (Chromium cannot be downloaded in this environment) and the redesign has never been seen in a browser, so no extra points are given for how it looks.
7. **Performance 4.0.** Unchanged: a 300,000 x 8 CSV (25.3 MB) loads in 1.11 s versus 0.57 s before, because a second read protects leading zeros. One run each on this machine, not a statistical benchmark.
8. **Security 3.5 -> 4.5.** `pip-audit` first found 37 advisories, all in Pillow 12.3.0 (via Streamlit 1.63.0, which capped Pillow below 13). The pins were moved to Streamlit 1.66.1 + Pillow 13, the full suite was re-run on them and `pip-audit` now reports nothing. Also added: logging that records exception types rather than cell values, `showErrorDetails="type"`, Markdown escaping of user text in notes, friendly errors for bad uploads. Not claimed: that the app is "secure"; an audit is a point-in-time check against known advisories.
9. **Testing 8.0 -> 8.5.** 295 -> 765 tests, 0 deleted; coverage `data/`+`utils/` 95%, `app.py`+`views/` 90%; chart cross-product, edge datasets, import regressions, page checks for every shipped sample file, doc-sync test. Not higher: remote CI has not run, browser tests skipped, Python 3.13 unavailable here.
10. **Documentation 3.5 -> 4.0.** Docs now agree with the code and with each other, outdated reports were folded into one history file, the chart matrix is generated from the code. Missing: a license decision and a demo GIF (no browser to record one).

## What would raise it further (and what could lower it)

| Work | Needs | Approx. gain |
|---|---|---:|
| Push to GitHub; get CI green on 3.12 and 3.13; run the 5 browser tests | GitHub account, a network that can download Chromium | +1 to +1.5 (or a deduction if they fail) |
| Choose and add a license; record a demo GIF | Owner decision; a browser | +0.5 to +1 |
| Keyboard and screen-reader pass; verify the focus ring visually | A browser and assistive technology | +0.5 to +1 |
| Extend the script export to chart/filter settings; real-user feedback | Time; users | +0.25 to +0.5 |

## Score history

56 (original baseline) -> 74 (previous documented pass) -> 75.5 as reported at the start of this pass (its category scores actually sum to 76.0) -> **88.0** (this pass). The earlier detailed table for the 56 -> 74 step is preserved in git history of this file.
