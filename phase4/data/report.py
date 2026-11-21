"""
data/report.py
==============
Generation of the downloadable HTML executive report.

No Streamlit imports. Every piece of user-controlled text (file name, column
names, cell values that appear in insights) is HTML-escaped before it is placed
in the document.
"""

from __future__ import annotations

import re
from html import escape as html_escape
from typing import Any

import pandas as pd

from data.profiler import (
    calculate_dataset_health,
    dataset_metrics,
    generate_eda_insights,
    numeric_statistics,
)


def insight_to_html(text: Any) -> str:
    """HTML-escape an insight string, then turn **bold** markdown into <b>...</b>.
    Escaping first means column names / file names can never inject markup."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html_escape(str(text)))


def generate_html_report(df: pd.DataFrame, dataset_name: str) -> str:
    """Build the standalone HTML report for a dataset (all user text is HTML-escaped)."""
    m = dataset_metrics(df)
    h = calculate_dataset_health(df)
    insights = generate_eda_insights(df)
    nums_df = numeric_statistics(df)

    insights_html = "".join(f"<li>{insight_to_html(ins)}</li>" for ins in insights)
    safe_name = html_escape(str(dataset_name))

    table_html = ""
    if not nums_df.empty:
        table_html = nums_df.round(2).to_html(classes="table", index=False)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>AnalyticsPro Executive Data Report - {safe_name}</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 40px; color: #1e293b; background: #fff; }}
            h1 {{ color: #4f46e5; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; }}
            h2 {{ color: #0f172a; margin-top: 30px; }}
            .metric-cards {{ display: flex; gap: 15px; margin: 20px 0; }}
            .card {{ background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 15px; flex: 1; text-align: center; }}
            .card-val {{ font-size: 22px; font-weight: bold; color: #4f46e5; }}
            .card-lbl {{ font-size: 12px; color: #64748b; font-weight: 600; text-transform: uppercase; }}
            ul {{ line-height: 1.6; font-size: 14px; }}
            .table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 13px; }}
            .table th, .table td {{ border: 1px solid #cbd5e1; padding: 8px 12px; text-align: left; }}
            .table th {{ background-color: #f1f5f9; color: #0f172a; }}
            .footer {{ margin-top: 50px; font-size: 11px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 15px; }}
        </style>
    </head>
    <body>
        <h1>📊 AnalyticsPro Executive Data Summary</h1>
        <p><b>Dataset Name:</b> {safe_name}</p>

        <div class="metric-cards">
            <div class="card"><div class="card-val">{m['rows']:,}</div><div class="card-lbl">Total Rows</div></div>
            <div class="card"><div class="card-val">{m['columns']:,}</div><div class="card-lbl">Columns</div></div>
            <div class="card"><div class="card-val">{m['missing']:,}</div><div class="card-lbl">Missing Values</div></div>
            <div class="card"><div class="card-val">{h['overall']}/100</div><div class="card-lbl">Health Score</div></div>
        </div>

        <h2>💡 Key Insights & Findings</h2>
        <ul>{insights_html}</ul>

        <h2>📈 Summary Statistics</h2>
        {table_html}

        <div class="footer">Generated automatically by AnalyticsPro AI Studio • Made by Vinay</div>
    </body>
    </html>
    """
    return html_content
