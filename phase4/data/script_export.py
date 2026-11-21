"""
data/script_export.py
=====================
Turn what a user did in AnalyticsPro (how the file was imported + the cleaning
steps applied on the Data Preparation page) into a standalone, readable pandas
script. Running the script on the original file reproduces the cleaned dataset,
so the work is documented, repeatable and independent of the app.

Every supported step is verified by tests that execute the generated script and
compare the result with what the app itself produced. Steps the generator does
not know are kept in the script as clearly marked comments rather than dropped.

Pure Python; no Streamlit imports.
"""
from __future__ import annotations

from typing import Any

#: Step operations the generator can turn into code.
SUPPORTED_OPS: tuple[str, ...] = (
    "drop_columns", "rename_column", "reorder_columns", "remove_duplicates", "fill_missing",
    "convert_type", "clean_text", "fix_infinite", "datetime_convert", "datetime_extract",
)

# ----- helper functions that are copied into a script only when a step needs them -----------
_HELPERS: dict[str, str] = {
    "fill_missing": '''
def fill_missing(df, columns, numeric_strategy, numeric_custom, categorical_strategy, categorical_custom):
    """Fill (or drop rows with) missing values the way AnalyticsPro's Missing Values tab does."""
    out = df.copy()
    drop_cols = []
    for col in columns:
        if col not in out.columns:
            continue
        s = out[col]
        if int(s.isna().sum()) == 0:
            continue
        is_numeric = pd.api.types.is_numeric_dtype(s)
        strategy = numeric_strategy if is_numeric else categorical_strategy
        if strategy == "Drop rows":
            drop_cols.append(col)
            continue
        if is_numeric:
            if strategy == "Mean":
                value = s.mean()
            elif strategy == "Zero":
                value = 0
            elif strategy == "Custom value":
                try:
                    value = float(numeric_custom)
                except (TypeError, ValueError):
                    continue
            else:
                value = s.median()
            if pd.notna(value):
                out[col] = s.fillna(value)
        else:
            if strategy == "Mode":
                mode = s.mode(dropna=True)
                value = mode.iloc[0] if not mode.empty else "Unknown"
            elif strategy == "Custom value":
                value = categorical_custom if categorical_custom else "Unknown"
            else:
                value = "Unknown"
            out[col] = s.fillna(value)
    if drop_cols:
        out = out.dropna(subset=drop_cols).reset_index(drop=True)
    return out
''',
    "convert_type": '''
def convert_type(df, col, target_type):
    """Convert one column to Integer / Float / String / Category / DateTime / Boolean."""
    out = df.copy()
    original = out[col]
    if target_type == "Integer":
        out[col] = pd.to_numeric(original, errors="coerce").astype("Int64")
    elif target_type == "Float":
        out[col] = pd.to_numeric(original, errors="coerce").astype(float)
    elif target_type == "String":
        out[col] = original.astype(str)
    elif target_type == "Category":
        out[col] = original.astype("category")
    elif target_type == "DateTime":
        out[col] = pd.to_datetime(original, errors="coerce")
    elif target_type == "Boolean":
        out[col] = original.map(
            lambda x: True if str(x).strip().lower() in ["true", "1", "yes", "y"]
            else (False if str(x).strip().lower() in ["false", "0", "no", "n"] else None)
        )
    return out
''',
    "clean_text": '''
def clean_text(df, columns, operations):
    """Apply strip / lower / upper / dedupe_spaces / empty_to_nan to text columns."""
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            continue
        s = out[col].astype("string")
        if "strip" in operations:
            s = s.str.strip()
        if "lower" in operations:
            s = s.str.lower()
        if "upper" in operations:
            s = s.str.upper()
        if "dedupe_spaces" in operations:
            s = s.str.replace(r"\\s+", " ", regex=True)
        if "empty_to_nan" in operations:
            s = s.replace("", pd.NA)
        out[col] = s.astype(object).where(s.notna(), None)
    return out
''',
}


def _load_code(info: dict, input_name: str) -> list[str]:
    """Lines that read the original file and repeat AnalyticsPro's import clean-up."""
    source = info.get("source", {})
    lines: list[str] = []
    if source.get("format") == "excel":
        sheet = source.get("sheet", 0)
        lines += [f"df = pd.read_excel({input_name}, sheet_name={sheet!r}, dtype=object).infer_objects()"]
        if info.get("blank_rows_dropped"):
            lines += ['df = df.dropna(how="all").reset_index(drop=True)   # completely blank rows']
        if info.get("empty_unnamed_dropped"):
            lines += [f"df = df.drop(columns={list(info['empty_unnamed_dropped'])!r})   # empty unnamed columns"]
        for col in info.get("numeric_text_columns", []):
            lines += [f'df[{col!r}] = pd.to_numeric(df[{col!r}].str.strip(), errors="coerce")   # numbers stored as text']
    else:
        sep, enc = source.get("delimiter", ","), source.get("encoding", "utf-8")
        lines += [f"df = pd.read_csv({input_name}, sep={sep!r}, encoding={enc!r})"]
        text_cols = list(info.get("text_columns", []))
        if text_cols:
            lines += [
                "# Codes with leading zeros (e.g. 00123) are re-read as text so the zeros are kept.",
                f"_raw = pd.read_csv({input_name}, sep={sep!r}, encoding={enc!r}, usecols={text_cols!r}, dtype=str)",
                f"for _col in {text_cols!r}:",
                "    df[_col] = _raw[_col].str.strip().where(_raw[_col].notna())",
            ]
    decimals = [(d["column"], d["style"]) for d in info.get("decimal_columns", [])]
    if decimals:
        lines += [
            "# Numbers written with a decimal comma (12,50) or thousands separators are converted.",
            f"for _col, _style in {decimals!r}:",
            '    _text = df[_col].astype("string").str.strip()',
            '    if _style == "comma":',
            '        _text = _text.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)',
            "    else:",
            '        _text = _text.str.replace(",", "", regex=False)',
            '    df[_col] = pd.to_numeric(_text, errors="coerce").astype("float64")',
        ]
    lines += ['df.columns = [str(c).strip() if str(c).strip() else f"Unnamed_{i}" for i, c in enumerate(df.columns)]']
    for col in info.get("datetime_columns", []):
        lines += [f'df[{col!r}] = pd.to_datetime(df[{col!r}], errors="coerce")   # detected as dates on import']
    return lines


def _extract_code(column: str, part: str) -> str:
    target = {"Year": ("year", "s.dt.year"), "Month": ("month", "s.dt.month"), "Day": ("day", "s.dt.day"),
              "Weekday": ("weekday", "s.dt.day_name()"), "Hour": ("hour", "s.dt.hour")}[part]
    return f"df[{column + '_' + target[0]!r}] = {target[1]}"


def _step_code(step: dict[str, Any]) -> tuple[list[str], set[str]]:
    """Code lines for one recorded step and the helper functions it needs."""
    op = step["op"]
    if op == "drop_columns":
        return [f'df = df.drop(columns={list(step["columns"])!r}, errors="ignore")'], set()
    if op == "rename_column":
        return [f'df = df.rename(columns={{{step["old"]!r}: {step["new"]!r}}})'], set()
    if op == "reorder_columns":
        return [f'_order = {list(step["order"])!r}',
                "df = df[_order + [c for c in df.columns if c not in _order]]"], set()
    if op == "remove_duplicates":
        keep = "first" if step["action"] == "Keep first occurrence" else "last"
        return [f"df = df.drop_duplicates(keep={keep!r}).reset_index(drop=True)"], set()
    if op == "fill_missing":
        return [f'df = fill_missing(df, {list(step["columns"])!r}, {step["numeric_strategy"]!r}, '
                f'{step.get("numeric_custom")!r}, {step["categorical_strategy"]!r}, {step.get("categorical_custom")!r})'], {op}
    if op == "convert_type":
        return [f'df = convert_type(df, {step["column"]!r}, {step["target_type"]!r})'], {op}
    if op == "clean_text":
        return [f'df = clean_text(df, {list(step["columns"])!r}, {list(step["operations"])!r})'], {op}
    if op == "fix_infinite":
        return [f"for _col in {list(step['columns'])!r}:",
                "    df[_col] = df[_col].replace([np.inf, -np.inf], np.nan)"], set()
    if op == "datetime_convert":
        col = step["column"]
        target = repr(col) if step.get("overwrite") else repr(col + "_datetime")
        return [f'df[{target}] = pd.to_datetime(df[{col!r}], errors="coerce")'], set()
    if op == "datetime_extract":
        col = step["column"]
        lines = [f'_s = pd.to_datetime(df[{col!r}], errors="coerce")']
        lines += [_extract_code(col, part).replace("s.dt", "_s.dt") for part in step["parts"]]
        return lines, set()
    raise ValueError(f"Unsupported step '{op}'.")


def _entry_steps(entry: dict) -> list[dict]:
    """The structured step(s) of one history entry (one dict, or a list for composite actions)."""
    step = entry.get("step")
    if isinstance(step, dict):
        return [step]
    if isinstance(step, list):
        return [x for x in step if isinstance(x, dict)]
    return []


def exportable_steps(history: list[dict]) -> list[dict]:
    """All recorded structured steps of a cleaning history, in order."""
    return [step for entry in history for step in _entry_steps(entry)]


def unexportable_actions(history: list[dict]) -> list[str]:
    """History entries that have no structured step (they will appear as comments only)."""
    return [str(e.get("action", "")) for e in history if not _entry_steps(e)]


def build_cleaning_script(history: list[dict], import_info: dict, *, source_name: str,
                          input_path: str | None = None, output_path: str | None = None) -> str:
    """Return the text of a standalone pandas script.

    ``history`` is the cleaning history (entries ``{"time", "action", "step"?}``),
    ``import_info`` is ``data.loader.import_steps(df)`` for the loaded file and
    ``source_name`` is the uploaded file's name. ``input_path`` / ``output_path``
    override the default file names used in the script.
    """
    input_path = input_path or source_name
    stem = source_name.rsplit(".", 1)[0] or "dataset"
    output_path = output_path or f"cleaned_{stem}.csv"
    body: list[str] = []
    helpers: set[str] = set()
    for number, entry in enumerate(history, start=1):
        action = str(entry.get("action", "")).replace("\n", " ")
        steps = _entry_steps(entry)
        body.append(f"# Step {number}: {action}")
        if steps:
            for step in steps:
                lines, needed = _step_code(step)
                body += lines
                helpers |= needed
        else:
            body.append("# (this step could not be exported automatically; repeat it by hand)")
        body.append("")
    out = [
        '"""Cleaning script generated by AnalyticsPro.',
        "",
        "It repeats, on the original file, the import clean-up and every cleaning step applied on the",
        "Data Preparation page, in the same order. Requires: pip install pandas openpyxl",
        '"""',
        "import numpy as np",
        "import pandas as pd",
        "",
        f"INPUT_FILE = {input_path!r}    # path to your copy of the original file",
        f"OUTPUT_FILE = {output_path!r}",
        "",
    ]
    for name in ("fill_missing", "convert_type", "clean_text"):
        if name in helpers:
            out.append(_HELPERS[name].strip("\n"))
            out.append("")
    out += ["", "# ---- 1. Load the file (repeats AnalyticsPro's import) ----"]
    out += _load_code(import_info, "INPUT_FILE")
    out += ["", "# ---- 2. Cleaning steps ----"]
    out += body if body else ["# (no cleaning steps were applied)", ""]
    out += ["# ---- 3. Save the result ----", "df.to_csv(OUTPUT_FILE, index=False)",
            'print(f"Saved {len(df):,} rows x {len(df.columns)} columns to {OUTPUT_FILE}")', ""]
    return "\n".join(out)
