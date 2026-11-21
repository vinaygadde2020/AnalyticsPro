# Feature ownership matrix

Which page owns which capability, what is shared, and what was decided. Written *before* changing anything in the overlap review, then updated with the outcome.

## Pages

| Page | Purpose | Input | Output | Unique capability (kept) |
|---|---|---|---|---|
| Data Upload & Preview | Load a file and look at it | CSV/XLSX/XLS, import options | Preview, profile, import notes | Import options (worksheet, decimal separator, leading zeros) |
| Data Preparation | Clean the active dataset | Active dataset | Changed dataset + audit trail (each step is also recorded in structured form) | The **only** page that modifies data |
| Automatic EDA | Understand the data's quality and shape | Active dataset | Statistics, quality report, insights | Profiling and written insights |
| KPI Dashboard | Headline numbers for the *whole* dataset | Active dataset | KPI cards, top segments, one trend | Zero-configuration summary |
| Interactive Dashboard | Explore a *filtered* slice in a card layout | Active dataset + filters | KPI cards (change vs full dataset), composition donut, data-quality checklist, completeness ring, latest records, segment and trend charts, custom KPI cards and charts, filtered download | Slicers/filters, custom KPI cards, Smart Dashboard Builder |
| Visualizations | Build **one** chart with full styling | Active dataset | One styled chart; recommended charts | Palette, height, grid; chart recommendations |
| Correlation & Relationships | Relationships between numeric columns | Numeric columns | Matrix, ranked pairs, trendline | Correlation analysis |
| Outlier Detection | Find unusual values | Numeric column | Flagged rows, bounds | IQR / z-score methods |
| Ask Your Data | Plain-English questions (rule-based, **not AI**) | A typed question | Number, table or chart | Natural-language routing; schema-aware suggestions |
| Dataset Comparison | Compare two files | Second upload | Side-by-side metrics | Only multi-dataset page |
| Export & Reporting | Download results | Active dataset | CSV, Excel, Power BI pack, HTML report, **reproducible cleaning script (.py)** | Reports, exports and the cleaning script |

## Duplicated logic found, and what happened

| Logic | Where it was repeated | Outcome |
|---|---|---|
| Sum / Average / Median / ... | Dashboard (3 places), Visualizations, recommender, KPI cards | **Merged** into `data/aggregation.py`; every page calls it. `Sum` of an all-missing group is now missing instead of 0 |
| Building bar/line/area/pie/box/violin/scatter/histogram/heatmap figures | Visualizations page, Dashboard custom charts, Smart builder, Dashboard explore charts | **Merged** into `data/charts.py` (`build_chart`, validation + friendly messages) |
| "Is this column an ID / a metric / a category?" | `recommender`, `intent`, each page's first-numeric default | **Merged** into `data/columns.py`; Ask Your Data, chart defaults, KPI defaults and the Smart builder use it |
| Trend over time | Dashboard, KPI page (`compute_time_trend`) | Dashboard uses `build_trend_chart`; the KPI page keeps `compute_time_trend` (different return shape, different page purpose) |
| KPI cards | KPI Dashboard vs Interactive Dashboard | **Retained, differentiated**: KPI = whole dataset, no setup; Dashboard = filtered, user-chosen cards. Page captions now say so |
| Chart builder | Visualizations vs Dashboard "Customize" | **Retained, differentiated**: Visualizations = one chart with styling; Dashboard = many charts reacting to shared filters. Both use the same builder |

Nothing was removed. No new chart builder or KPI feature was added.
