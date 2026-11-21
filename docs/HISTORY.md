# Project history

A short record of how the project evolved. The detailed reports from the earlier passes were removed from the repository to keep it tidy (they described old page names, old test counts and an old score, which no longer match the code); the current facts are in [VALIDATION_REPORT.md](VALIDATION_REPORT.md), [CHANGE_REPORT.md](CHANGE_REPORT.md) and [PROJECT_SCORECARD.md](PROJECT_SCORECARD.md).

| Pass | What happened |
|---|---|
| Prototype | A Google Colab notebook (now in `archive/`) explored cleaning, correlation, outliers and simple models. |
| First cleanup | Dead code and duplicate files removed from the first Streamlit version. |
| Regression tests and P0 fixes | A pytest suite was added that failed on the old code, then the confirmed bugs were fixed until it passed. |
| Input handling, performance, reliability | Safer CSV/Excel reading (delimiter and encoding detection), faster data preparation, unit tests for the data layer. |
| Architecture | `app.py` (about 2,300 lines) was split into one module per page under `phase4/views/`, and non-UI logic moved to `phase4/data/`. The long data-preparation page became one function per tab. |
| Custom dashboard | The Interactive Dashboard (filters, custom KPI cards and charts) and the Smart Dashboard Builder were added. |
| Latest pass | Shared aggregation, column-role and chart modules; the rule-based assistant renamed **Ask Your Data**; import improvements (worksheet choice, decimal commas, leading zeros); friendly errors; type hints and mypy; CI definition; dependency audit; stricter lint; this history and a tidier repository. |

Score history (see the scorecard for the evidence): 56 -> 74 -> 76.0 -> 88.0.

## Ideas not built (kept from the old roadmap)

- Richer Dataset Comparison (schema differences, value drift).
- Undo for a single cleaning step (today the whole dataset can be reloaded).
