"""
data/charts.py
==============
Builds every Plotly figure that users configure by hand (Visualizations page,
Interactive Dashboard "Customize" section, Smart Dashboard Builder).

The rule: *validate the choice, then draw it.* Invalid column choices raise
``ChartConfigError`` with a message that is safe to show users; the UI layer
turns that into a friendly note. ``safe_build_chart`` does that conversion for
callers that prefer a ``(figure, message)`` pair.

Pure pandas + Plotly; no Streamlit imports, so it is unit-tested directly.
See docs/CHART_COMPATIBILITY_MATRIX.md for what each chart accepts.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from data.aggregation import group_aggregate, normalize_aggregation, to_numeric_clean
from data.loader import detect_datetime_columns

logger = logging.getLogger("analyticspro.charts")

#: Chart types the builder understands, in display order.
CHART_TYPES: tuple[str, ...] = (
    "Bar Chart", "Line Chart", "Area Chart", "Scatter Plot", "Histogram",
    "Box Plot", "Violin Plot", "Pie Chart", "Donut Chart", "Heatmap",
)

#: Colouring/grouping by a column with more distinct values than this is refused
#: (the legend would be unreadable and Plotly gets slow).
MAX_COLOR_GROUPS = 30

#: What each chart needs. Used by the docs generator and as the test oracle.
CHART_SPECS: dict[str, dict[str, str]] = {
    "Bar Chart": {"x": "category, date or numeric", "y": "numeric (any column with Count)", "color": "optional category", "aggregation": "yes (category/date X)"},
    "Line Chart": {"x": "category, date or numeric", "y": "numeric (any column with Count)", "color": "optional category", "aggregation": "yes (category/date X)"},
    "Area Chart": {"x": "category, date or numeric", "y": "numeric (any column with Count)", "color": "optional category", "aggregation": "yes (category/date X)"},
    "Scatter Plot": {"x": "any column, different from Y", "y": "numeric", "color": "optional category", "aggregation": "no"},
    "Histogram": {"x": "not used", "y": "numeric (the column to bin)", "color": "optional category", "aggregation": "no"},
    "Box Plot": {"x": "optional category", "y": "numeric", "color": "optional category", "aggregation": "no"},
    "Violin Plot": {"x": "optional category", "y": "numeric", "color": "optional category", "aggregation": "no"},
    "Pie Chart": {"x": "category", "y": "optional numeric (counts rows if omitted)", "color": "not used", "aggregation": "yes"},
    "Donut Chart": {"x": "category", "y": "optional numeric (counts rows if omitted)", "color": "not used", "aggregation": "yes"},
    "Heatmap": {"x": "not used", "y": "not used", "color": "not used", "aggregation": "no (correlation of numeric columns)"},
}

_FRIENDLY_FALLBACK = (
    "This chart could not be built with the selected columns. "
    "Try different columns or another chart type."
)


class ChartConfigError(ValueError):
    """The chosen columns/options cannot make this chart. ``str(exc)`` is user-safe."""


# --------------------------------------------------------------------------- helpers
def canonical_chart_type(chart_type: str) -> str:
    """Match a chart type case-insensitively ("Bar chart" == "Bar Chart")."""
    wanted = str(chart_type).strip().lower()
    for known in CHART_TYPES:
        if known.lower() == wanted:
            return known
    raise ChartConfigError(f"'{chart_type}' is not a supported chart type.")


def _require_column(df: pd.DataFrame, col: str | None, role: str) -> str:
    """Check a column was chosen and exists; the message names what is missing."""
    if col is None or col == "(None)":
        raise ChartConfigError(f"Choose {role}.")
    if col not in df.columns:
        raise ChartConfigError(f"'{col}' is not in the dataset.")
    return col


def _x_kind(df: pd.DataFrame, x: str, date_columns: Sequence[str] | None) -> str:
    """Classify the X column as 'date', 'numeric' or 'category'."""
    series = df[x]
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"
    if pd.api.types.is_bool_dtype(series):
        return "category"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if date_columns is not None:
        return "date" if x in date_columns else "category"
    return "date" if x in detect_datetime_columns(df[[x]]) else "category"


def _check_color(df: pd.DataFrame, color: str | None) -> str | None:
    """Validate the optional colour/group column (existence and group count)."""
    if color in (None, "(None)", "None"):
        return None
    if color not in df.columns:
        raise ChartConfigError(f"The color/group column '{color}' is not in the dataset.")
    groups = int(df[color].nunique(dropna=True))
    if groups > MAX_COLOR_GROUPS:
        raise ChartConfigError(
            f"'{color}' has {groups} different values; choose a color/group column with "
            f"at most {MAX_COLOR_GROUPS}."
        )
    return color


def _numeric_frame(df: pd.DataFrame, col: str, role: str = "a Y-axis column") -> pd.DataFrame:
    """Copy of df where ``col`` is numeric with inf/text turned into NaN."""
    working = df.copy()
    working[col] = to_numeric_clean(working[col])
    if working[col].notna().sum() == 0:
        raise ChartConfigError(f"'{col}' has no numeric values, so it cannot be used for {role}.")
    return working


def _label_keys(frame: pd.DataFrame, cols: Sequence[str]) -> pd.DataFrame:
    """Show missing category values as '(missing)' instead of 'nan'."""
    for col in dict.fromkeys(cols):
        frame[col] = frame[col].astype(object).where(frame[col].notna(), "(missing)").astype(str)
    return frame


def _limit_top_x(result: pd.DataFrame, x: str, value: str, top_n: int) -> pd.DataFrame:
    """Keep the ``top_n`` x-values with the largest total, sorted by that total."""
    totals = result.groupby(x)[value].sum(min_count=1).sort_values(ascending=False)
    keep = list(totals.head(top_n).index)
    order = {k: i for i, k in enumerate(keep)}
    limited = result[result[x].isin(keep)].copy()
    limited["__order__"] = limited[x].map(order)
    return limited.sort_values("__order__").drop(columns="__order__")


def finish_figure(fig: go.Figure, height: int = 350, top_margin: int = 50) -> go.Figure:
    """Apply the app's standard compact layout."""
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=top_margin, b=10))
    return fig


# --------------------------------------------------------------------------- builders
def _build_aggregated_xy(
    df: pd.DataFrame, kind: str, x: str | None, y: str | None, color: str | None, agg: str, top_n: int,
    palette: Sequence[str] | None, color_sequence: Sequence[str] | None,
    date_columns: Sequence[str] | None, aggregate_numeric_x: bool,
) -> go.Figure:
    """Bar/line/area chart: aggregate Y per X (and colour group) unless X is numeric."""
    if x is None or y is None:
        raise ChartConfigError("Choose both an X-axis column and a numeric Y-axis column.")
    x = _require_column(df, x, "an X-axis column")
    y = _require_column(df, y, "a Y-axis column")
    canonical_agg = normalize_aggregation(agg)
    if x == y and canonical_agg != "Count":
        raise ChartConfigError("Choose a different column for X than for Y to group and aggregate the data.")
    if canonical_agg != "Count":
        df = _numeric_frame(df, y)
    color = _check_color(df, color)
    x_kind = _x_kind(df, x, date_columns)
    if x_kind == "numeric" and aggregate_numeric_x:
        x_kind = "category"          # the page treats X as a grouping column even when it is numeric
    title_value = f"{canonical_agg} of {y}" if canonical_agg != "Count" else f"Count of {y}"
    title = f"{title_value} by {x}"

    if x_kind == "numeric":
        plot = df[[c for c in dict.fromkeys([x, y] + ([color] if color else []))]].copy()
        plot[x] = to_numeric_clean(plot[x])
        plot = plot.dropna(subset=[x]).sort_values(x)
        if plot.empty:
            raise ChartConfigError(f"'{x}' has no numeric values to plot.")
        value_name = y
        title = f"{y} by {x}"
    else:
        working = df
        if x_kind == "date":
            working = df.copy()
            working[x] = pd.to_datetime(working[x], errors="coerce")
            working = working.dropna(subset=[x])
            if working.empty:
                raise ChartConfigError(f"'{x}' has no valid dates to plot.")
        keys = [x] + ([color] if color and color != x else [])
        plot, value_name = group_aggregate(working, keys, y, canonical_agg)
        if x_kind == "date":
            plot = plot.sort_values(x)
        else:
            plot = _label_keys(plot, keys)
            plot = _limit_top_x(plot, x, value_name, top_n)
    if plot[value_name].notna().sum() == 0:
        raise ChartConfigError(f"No values are left to plot for '{y}'.")

    group_color = color if color else None
    if kind == "Bar Chart":
        fig = px.bar(
            plot, x=x, y=value_name, color=group_color or (value_name if palette else None),
            color_continuous_scale=palette if (palette and not group_color) else None,
            color_discrete_sequence=color_sequence, barmode="group", title=title,
        )
    elif kind == "Line Chart":
        fig = px.line(plot, x=x, y=value_name, color=group_color, markers=True,
                      color_discrete_sequence=color_sequence, title=title)
    else:
        fig = px.area(plot, x=x, y=value_name, color=group_color,
                      color_discrete_sequence=color_sequence, title=title)
    return fig


def _build_scatter(
    df: pd.DataFrame, x: str | None, y: str | None, color: str | None,
    color_sequence: Sequence[str] | None,
) -> go.Figure:
    """Scatter plot of two columns with optional colour groups."""
    x = _require_column(df, x, "an X-axis column")
    y = _require_column(df, y, "a Y-axis column")
    if x == y:
        raise ChartConfigError("Choose two different columns for the X and Y axes.")
    color = _check_color(df, color)
    plot = _numeric_frame(df, y)
    if pd.api.types.is_numeric_dtype(plot[x]):
        plot[x] = to_numeric_clean(plot[x])
    plot = plot.dropna(subset=[y])
    return px.scatter(plot, x=x, y=y, color=color, color_discrete_sequence=color_sequence,
                      title=f"{y} vs {x}")


def _build_distribution(
    df: pd.DataFrame, kind: str, x: str | None, y: str | None, color: str | None, bins: int,
    color_sequence: Sequence[str] | None, points: str, date_columns: Sequence[str] | None,
) -> go.Figure:
    """Histogram, box or violin plot of one numeric column."""
    y = _require_column(df, y, "a numeric column (Y)")
    plot = _numeric_frame(df, y, role="this chart")
    color = _check_color(plot, color)
    if kind == "Histogram":
        return px.histogram(plot, x=y, color=color, nbins=int(bins),
                            color_discrete_sequence=color_sequence, title=f"Distribution of {y}")
    x_col = None
    if x not in (None, "(None)", "None") and x in plot.columns and _x_kind(plot, x, date_columns) == "category":
        groups = int(plot[x].nunique(dropna=True))
        if groups > MAX_COLOR_GROUPS:
            raise ChartConfigError(
                f"'{x}' has {groups} different values; choose a category with at most {MAX_COLOR_GROUPS}."
            )
        x_col = x
    if kind == "Box Plot":
        return px.box(plot, x=x_col, y=y, color=color, color_discrete_sequence=color_sequence,
                      title=f"Box Plot of {y}")
    return px.violin(plot, x=x_col, y=y, color=color, box=True, points=points,
                     color_discrete_sequence=color_sequence, title=f"Violin Plot of {y}")


def _build_pie(
    df: pd.DataFrame, kind: str, x: str | None, y: str | None, agg: str, top_n: int,
    color_sequence: Sequence[str] | None,
) -> go.Figure:
    """Pie/donut of row counts or an aggregated value per category."""
    x = _require_column(df, x, "a category column (X)")
    hole = 0.48 if kind == "Donut Chart" else 0
    if y in (None, "(None)", "None"):
        counts = df[x].astype(object).where(df[x].notna(), "(missing)").astype(str).value_counts().head(top_n)
        pie = counts.rename_axis(x).reset_index(name="Count")
        return px.pie(pie, names=x, values="Count", hole=hole, color_discrete_sequence=color_sequence,
                      title=f"{kind}: {x}")
    y = _require_column(df, y, "a values column")
    canonical_agg = normalize_aggregation(agg)
    working = df if canonical_agg == "Count" else _numeric_frame(df, y, role="the values")
    pie, value_name = group_aggregate(working, [x], y, canonical_agg)
    pie = _label_keys(pie, [x])
    pie = pie.dropna(subset=[value_name]).sort_values(value_name, ascending=False).head(top_n)
    if pie.empty:
        raise ChartConfigError(f"No values are left to plot for '{y}'.")
    if (pie[value_name] < 0).any():
        raise ChartConfigError("Pie and donut charts cannot show negative totals. Try a bar chart instead.")
    return px.pie(pie, names=x, values=value_name, hole=hole, color_discrete_sequence=color_sequence,
                  title=f"{canonical_agg} of {y} by {x}")


def _build_heatmap(df: pd.DataFrame, columns: Sequence[str] | None) -> go.Figure:
    """Correlation heatmap of the numeric columns."""
    numeric = [c for c in (columns if columns is not None else df.columns)
               if c in df.columns and pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
    if len(numeric) < 2:
        raise ChartConfigError("A correlation heatmap needs at least two numeric columns.")
    corr = df[numeric].apply(to_numeric_clean).corr()
    corr = corr.dropna(how="all").dropna(axis=1, how="all")
    if corr.shape[0] < 2:
        raise ChartConfigError("The numeric columns are constant or empty, so no correlations can be calculated.")
    return px.imshow(corr, text_auto=".2f", zmin=-1, zmax=1, color_continuous_scale="RdBu_r",
                     title="Numeric correlation heatmap")


def build_chart(
    df: pd.DataFrame, chart_type: str, *, x: str | None = None, y: str | None = None,
    color: str | None = None, agg: str = "Average", top_n: int = 30, bins: int = 30,
    palette: Sequence[str] | None = None, color_sequence: Sequence[str] | None = None,
    columns: Sequence[str] | None = None, date_columns: Sequence[str] | None = None,
    violin_points: str = "outliers", aggregate_numeric_x: bool = False,
) -> go.Figure:
    """Build one figure or raise ``ChartConfigError`` explaining what to change.

    ``x``/``y``/``color`` are column names; see ``CHART_SPECS`` for what each chart
    type accepts. ``agg`` is any label understood by ``normalize_aggregation``.
    ``palette`` colours single-series bars by value; ``color_sequence`` is the
    discrete colour list. ``date_columns`` can pass already-detected date columns
    to avoid re-detecting them. With ``aggregate_numeric_x`` a numeric X is grouped
    like a category instead of being plotted row by row.
    """
    kind = canonical_chart_type(chart_type)
    if df is None or len(df) == 0 or len(df.columns) == 0:
        raise ChartConfigError("There is no data to chart.")
    if kind in ("Bar Chart", "Line Chart", "Area Chart"):
        return _build_aggregated_xy(df, kind, x, y, color, agg, int(top_n), palette, color_sequence,
                                    date_columns, aggregate_numeric_x)
    if kind == "Scatter Plot":
        return _build_scatter(df, x, y, color, color_sequence)
    if kind in ("Histogram", "Box Plot", "Violin Plot"):
        return _build_distribution(df, kind, x, y, color, bins, color_sequence, violin_points, date_columns)
    if kind in ("Pie Chart", "Donut Chart"):
        return _build_pie(df, kind, x, y, agg, int(top_n), color_sequence)
    return _build_heatmap(df, columns)


def safe_build_chart(df: pd.DataFrame, chart_type: str, **options) -> tuple[go.Figure | None, str | None]:
    """``build_chart`` that never raises: returns ``(figure, None)`` or ``(None, message)``.

    Unexpected errors are logged (exception type and the column names chosen, never
    cell values) and replaced by a generic friendly message.
    """
    try:
        return build_chart(df, chart_type, **options), None
    except ChartConfigError as exc:
        return None, str(exc)
    except (ValueError, TypeError, KeyError, ZeroDivisionError, OverflowError) as exc:
        logger.warning(
            "Chart build failed (%s) type=%s x=%s y=%s color=%s",
            type(exc).__name__, chart_type, options.get("x"), options.get("y"), options.get("color"),
        )
        logger.debug("Chart build traceback", exc_info=True)
        return None, _FRIENDLY_FALLBACK


# --------------------------------------------------------------------------- time trend
_TREND_FREQ = {"Daily": "D", "Weekly": "W", "Monthly": "MS"}


def trend_frame(df: pd.DataFrame, date_col: str, value_col: str, agg: str = "Sum",
                grain: str = "Daily") -> pd.DataFrame:
    """Aggregate ``value_col`` over time. Returns columns ``[date_col, value_col]``.

    Rows with an unparseable date are dropped; an empty frame is returned if no
    valid dates remain. ``grain`` is "Daily", "Weekly" or "Monthly".
    """
    from data.aggregation import aggregate_grouped
    if grain not in _TREND_FREQ:
        raise ChartConfigError(f"Unknown trend interval '{grain}'.")
    _require_column(df, date_col, "a date column")
    _require_column(df, value_col, "a value column")
    working = pd.DataFrame({
        "__date__": pd.to_datetime(df[date_col], errors="coerce"),
        "__value__": to_numeric_clean(df[value_col]) if normalize_aggregation(agg) != "Count" else df[value_col],
    }).dropna(subset=["__date__"])
    if working.empty:
        return pd.DataFrame(columns=[date_col, value_col])
    series = working.set_index("__date__")["__value__"]
    result = aggregate_grouped(series.resample(_TREND_FREQ[grain]), agg)
    return result.rename(value_col).reset_index().rename(columns={"__date__": date_col})


def build_trend_chart(df: pd.DataFrame, date_col: str, value_col: str, agg: str = "Sum",
                      grain: str = "Daily", color_sequence: Sequence[str] | None = None) -> go.Figure:
    """Line chart of ``value_col`` aggregated per day/week/month."""
    frame = trend_frame(df, date_col, value_col, agg, grain)
    if frame.empty:
        raise ChartConfigError("No valid dates remain in the data.")
    label = normalize_aggregation(agg).lower()
    return px.line(frame, x=date_col, y=value_col, markers=True, color_discrete_sequence=color_sequence,
                   title=f"{grain} {label} {value_col} trend")


def build_donut(labels: Sequence[str], values: Sequence[float], centre_value: str, centre_title: str,
                colors: Sequence[str], height: int = 250) -> go.Figure:
    """Donut of ``values`` with a label in the hole (no legend: the page draws its own).

    ``colors`` are used in order, so a matching HTML legend can use the same list.
    """
    if len(labels) != len(values) or not len(values):
        raise ChartConfigError("There is nothing to show in the donut.")
    fig = go.Figure(go.Pie(
        labels=list(labels), values=list(values), hole=0.66, sort=False, direction="clockwise", textinfo="none",
        marker=dict(colors=[colors[i % len(colors)] for i in range(len(values))], line=dict(color="#ffffff", width=2)),
        hovertemplate="%{label}: %{value:,.2f} (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        showlegend=False, height=height, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)",
        annotations=[dict(text=f"<b>{centre_value}</b><br><span style='font-size:11px'>{centre_title}</span>",
                          x=0.5, y=0.5, showarrow=False, font=dict(size=17, color="#0f1b3d"))],
    )
    return fig
