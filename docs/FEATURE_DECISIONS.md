> **Status update (latest pass).** The rename discussed below was completed: the page is now called **Ask Your Data** (the old route name "AI Data Analyst" still works as an alias). Overlapping pages were differentiated rather than merged; see [FEATURE_OWNERSHIP_MATRIX.md](FEATURE_OWNERSHIP_MATRIX.md). The decision log below is kept as written.

# Feature Decisions

One decision per feature, with the evidence behind it. **Nothing in the "needs approval" section has been implemented.** Decision vocabulary: Keep unchanged, Keep and fix, Simplify, Merge, Rename, Remove, Add.

Principle: do not remove a feature because another page has a similar name. Remove or merge only where the functionality is genuinely duplicated, and keep distinct pages where users benefit from them.

## Per-feature decisions

Columns: purpose; overlap; useful to the target audience?; confirmed problems (after the fixes already made); recommendation; risk of changing it; how to verify.

### Data Upload & Preview
- **Purpose:** load CSV/XLSX/XLS, preview rows, per-column summary.
- **Overlap:** the per-column summary resembles Data Preparation's "Data Quality" tab.
- **Useful:** essential.
- **Problems:** fixed: same-name replacement, delimiters, encodings, multi-sheet notice, illegible uploader. Open: only the first sheet loads (notice only); leading zeros lost in numeric-looking IDs.
- **Decision: Keep and fix (done).** Optional later: a sheet selector; a "read as text" option for ID columns (S4-8).
- **Risk:** low. **Verify:** `test_loader.py`, upload AppTest and browser tests (all pass).

### Data Preparation (10 tabs)
- **Purpose:** missing values, duplicates, columns, text, numeric, date parts, stats, before/after, preview, downloads.
- **Overlap:** "Column Stats" overlaps EDA statistics; "Preview & Export" repeats downloads that also exist on Export; two reset buttons here plus the sidebar one.
- **Useful:** essential; the main differentiator of the product.
- **Problems:** fixed: silent blanking on conversion, silent `0` fill, 59 s render. Open: ~490-line function (complexity 62), too many tabs.
- **Decision: Keep and fix (done); Simplify (S4-2, S4-3, S4-5); then split into a module.**
- **Risk:** medium: most state keys live here. **Verify:** click-through tests for each tab, 300k-row timing, original dataset never modified (tested).

### Cleaning history and Before vs After
- **Purpose:** timestamped log of operations; side-by-side metrics before and after.
- **Overlap:** none. **Useful:** yes: the strongest differentiator.
- **Problems:** the history line was an injection site (fixed).
- **Decision: Keep unchanged.** It is also the foundation for the recommended script export (P3-01).
- **Risk:** low. **Verify:** history escaping test.

### Automatic EDA
- **Purpose:** health score, plain-language insights, distributions, missing-value analysis.
- **Overlap:** contains **Correlation Overview and Outlier Overview** sections that duplicate the dedicated pages; missing-value analysis overlaps Data Preparation's tab.
- **Useful:** yes, as the first look at a dataset.
- **Problems:** fixed: literal `**`, HTML injection. Open: duplication.
- **Decision: Simplify (S4-1):** replace the two duplicated sections with short summaries that link to the dedicated pages. Keep distributions and insights.
- **Risk:** low-medium (users who rely on the combined view). **Verify:** page tests updated; no references to removed widgets.

### KPI Dashboard
- **Purpose:** headline metrics for one numeric column plus a category breakdown.
- **Overlap:** partial: Visualizations' "KPI Summary" recommendation shows similar numbers.
- **Useful:** yes: a fast, readable summary for non-technical users.
- **Problems:** none confirmed; values verified against independent calculations.
- **Decision: Keep unchanged.** Distinct enough (selectable metric, breakdown); revisit only if users report confusion.
- **Risk:** low. **Verify:** `test_pages.py::test_kpi_dashboard_*`.

### Visualizations and Smart Recommendations
- **Purpose:** 8 chart types with controls; recommendations generated from the actual columns.
- **Overlap:** the chart-prompt page builds some of the same charts.
- **Useful:** essential.
- **Problems:** fixed: crash on numeric-only data; real metrics dropped by name matching. Open: none confirmed.
- **Decision: Keep and fix (done).**
- **Risk:** low. **Verify:** edge matrix, recommendation click-through and swap tests.

### Correlation & Relationships
- **Purpose:** heatmap with method and colour choice, threshold-filtered pair table, pairwise inspector.
- **Overlap:** EDA's duplicate overview (see above). **Useful:** yes, distinct.
- **Problems:** none confirmed. Label is truncated in the sidebar.
- **Decision: Keep unchanged; Rename to a shorter label (S4-9).**
- **Risk:** low. **Verify:** page tests.

### Outlier Detection
- **Purpose:** IQR or z-score detection with thresholds, box plot, distribution, outlier records.
- **Overlap:** EDA overview; the IQR maths existed in three places (now one).
- **Useful:** yes, distinct.
- **Problems:** none; page results match independent calculations (characterization tests).
- **Decision: Keep unchanged (logic consolidated, done).**
- **Risk:** low. **Verify:** `test_outliers.py`, `test_detect_outliers.py`.

### AI Data Analyst (chart prompts)
- **Purpose:** plain-English requests turned into bar, line, histogram or scatter charts.
- **Overlap:** the same charts exist on Visualizations; value is convenience for non-technical users.
- **Useful:** moderate: a friendly entry point, limited to four chart types.
- **Problems:** the name is misleading (no model, no network); fixed: short column names matching inside words, `count` on line charts.
- **Decision: Rename (S4-4)** to "Ask a Question" (or similar); keep the feature. Do **not** add an LLM: no justified need, and it would raise privacy and cost questions.
- **Risk:** low. **Verify:** `test_intent.py`, page tests.

### Dataset Comparison
- **Purpose:** compare two files side by side.
- **Overlap:** none. **Useful:** yes, and it matches the stated purpose.
- **Problems:** thin: counts, health and common column names only; order bug fixed.
- **Decision: Keep and improve later (P3-02):** dtype and schema differences.
- **Risk:** low. **Verify:** deltas and order are tested today.

### Export & Reporting
- **Purpose:** HTML executive report, cleaned CSV, column-profile CSV.
- **Overlap:** cleaned CSV/Excel are also on Data Preparation.
- **Useful:** essential.
- **Problems:** fixed: eager generation, escaping, download names.
- **Decision: Keep; make it the single place for downloads (S4-2).**
- **Risk:** low-medium (users looking for Excel on this page today must go to Prep). **Verify:** browser download tests.

### Reset mechanisms
- Sidebar **Reset Dataset** (reloads the uploaded file; confirmed) + Prep **Reset Changes** (back to the session checkpoint) + Prep **Restore Original**.
- **Decision: Simplify (S4-3):** remove or relabel the sidebar button; keep the two on Data Preparation, whose meanings are distinct.

### Supporting items
- **statsmodels** (optional, scatter trendline only): Simplify (S4-6), replace with a NumPy least-squares line and drop the dependency.
- **Phase 1 notebook** (3.4 MB, unreferenced): Keep, but move to `archive/` (S4-7); consider stripping saved outputs (about 3.2 MB).
- **Sample datasets:** added (synthetic).

## Status of cleanup decisions (2026-10-23)

Implemented in the cleanup passes: S4-1 (Automatic EDA now summarizes and directs users to the dedicated Correlation and Outlier Detection pages), S4-2 (downloads centralized; Preview tab retained), S4-3 (sidebar action relabeled), S4-4 (visible assistant/branding labels made accurate), and S4-9 (shorter Correlation label). S4-5 remains deferred until the app can be run and checked end to end. S4-6 was deferred because the trendline implementation still uses statsmodels. S4-7 was deferred to avoid removing saved notebook content. S4-8 remains a future usability improvement.

## Deferred decisions (not implemented)

| ID | Change | User-facing effect | Trade-off | Reversible |
|---|---|---|---|---|
| S4-1 | EDA links to Correlation/Outlier pages instead of repeating them | EDA page shorter | Loses the single-page overview | Yes (one commit) |
| S4-2 | Export is the only place for downloads (add Excel there); remove duplicates from Data Preparation's last tab, rename it "Preview" | Users find downloads in one place | Muscle memory for people used to the Prep tab | Yes |
| S4-3 | Remove or relabel sidebar "Reset Dataset" | One fewer button | "Reload original file" is occasionally handy; could be kept under a clearer name | Yes |
| S4-4 | Rename "AI Data Analyst" to "Ask a Question"; remove "ENTERPRISE AI PLATFORM" and "AI Studio" wording | Honest labelling | Less "marketing" feel | Yes |
| S4-5 | Merge "Column Stats" tab into EDA | One fewer tab | Statistics move to another page | Yes |
| S4-6 | Replace statsmodels trendline with NumPy | No visible change | Tiny numeric differences possible; verify against OLS | Yes |
| S4-7 | Move the notebook to `archive/` (optionally strip outputs) | none | Outputs are lost if stripped (history keeps them) | Yes |
| S4-8 | Option to read ID-like columns as text (keeps leading zeros) | New control on upload | Adds a setting to explain | Yes |
| S4-9 | Shorten "Correlation & Relationships" label | Fits the sidebar | None | Yes |

Rollback: each change is one commit on its own, so `git revert <commit>` undoes it; the tests for the old behaviour are updated in the same commit.

## Additions (maximum three, ranked)

1. **Export cleaning history as a Python script** - high value, medium effort; worth doing next.
2. **Richer Dataset Comparison** - moderate value, low-medium effort; worth doing after (1).
3. **Undo for individual steps** - moderate value, medium effort; only if (1) is built.

Not recommended now: an LLM-backed analyst, a database, authentication, deployment infrastructure.
