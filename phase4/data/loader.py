"""
data/loader.py
===============
Reusable dataset loading functions for AnalyticsPro.

Responsibilities:
    * Loading CSV files (with encoding fallback)
    * Loading XLSX / XLS files (with error handling)
    * Column-name cleanup
    * Basic datetime detection / conversion
    * Safe, high-level "load anything" entry point

No Streamlit UI code lives in this module — it only returns clean
pandas DataFrames (or raises a descriptive exception) so it can be
reused by app.py or any other caller.
"""

from __future__ import annotations

import copy
import csv
import logging
import re
import warnings
from typing import Any

import pandas as pd

logger = logging.getLogger("analyticspro.loader")

#: Decimal-separator choices for ``load_dataset``/``convert_decimal_text_columns``.
DECIMAL_AUTO, DECIMAL_POINT, DECIMAL_COMMA = "auto", ".", ","

# Encodings attempted in order. "utf-8-sig" decodes both plain UTF-8 and UTF-8
# with a BOM. cp1252 must come before latin-1: latin-1 accepts every byte, so
# anything placed after it is unreachable (and Windows "smart quotes" would load
# as control characters).
_CSV_ENCODING_FALLBACKS = ["utf-8-sig", "cp1252", "latin1"]

# Delimiters considered when auto-detecting (comma first = preferred on ties).
_DELIMITER_CANDIDATES = [",", ";", "\t", "|"]
_SNIFF_BYTES = 64 * 1024


def detect_delimiter(sample_text: str) -> str:
    """
    Guess the field delimiter from the start of a CSV file.

    Each candidate is tried with a real CSV parser (so quoted fields are
    respected). A candidate qualifies when it splits the header into 2+
    fields and at least 80% of the sampled rows have the same field count;
    the one giving the most fields wins, with ties going to the earlier
    candidate (comma first). Falls back to a comma.
    """
    lines = [ln for ln in sample_text.splitlines()[:50] if ln.strip()]
    if len(lines) < 1:
        return ","
    best, best_width = ",", 1
    for delim in _DELIMITER_CANDIDATES:
        try:
            widths = [len(row) for row in csv.reader(lines, delimiter=delim)]
        except csv.Error:
            continue
        header_width = widths[0]
        if header_width < 2:
            continue
        consistent = sum(1 for w in widths if w == header_width) / len(widths)
        if consistent >= 0.8 and header_width > best_width:
            best, best_width = delim, header_width
    return best


def _sniff_text(file_obj: Any, encoding: str) -> str:
    """Decode the first chunk of the file for delimiter detection."""
    if hasattr(file_obj, "seek"):
        file_obj.seek(0)
    chunk = file_obj.read(_SNIFF_BYTES)
    if hasattr(file_obj, "seek"):
        file_obj.seek(0)
    if isinstance(chunk, bytes):
        return chunk.decode(encoding, errors="replace")
    return str(chunk)


def _add_note(df: pd.DataFrame, text: str) -> None:
    """Record something the importer changed or could not decide (shown to the user)."""
    df.attrs.setdefault("import_notes", []).append(text)


def _record_import_step(df: pd.DataFrame, key: str, value: Any) -> None:
    """Remember *how* a file was read (structured), so a standalone script can repeat it.

    ``key`` is one of: ``source`` (dict), ``text_columns`` / ``datetime_columns`` /
    ``numeric_text_columns`` / ``empty_unnamed_dropped`` (lists of names),
    ``decimal_columns`` (list of ``{"column", "style"}``) or ``blank_rows_dropped`` (bool).
    """
    steps = df.attrs.setdefault("import_steps", {})
    if isinstance(value, list):
        steps.setdefault(key, []).extend(value)
    else:
        steps[key] = value


def import_steps(df: pd.DataFrame | None) -> dict:
    """Structured record of how ``df`` was imported (empty dict if unknown)."""
    if df is None:
        return {}
    return copy.deepcopy(df.attrs.get("import_steps", {}))


def import_notes(df: pd.DataFrame | None) -> list[str]:
    """Messages the importer attached to ``df`` (empty list if none)."""
    if df is None:
        return []
    return list(df.attrs.get("import_notes", []))


def _duplicate_header_names(sample_text: str, delimiter: str) -> list[str]:
    """Names that appear more than once in the header row (pandas silently renames them)."""
    try:
        header = next(csv.reader([ln for ln in sample_text.splitlines() if ln.strip()][:1], delimiter=delimiter))
    except (StopIteration, csv.Error):
        return []
    names = [h.strip() for h in header if h.strip()]
    return sorted({n for n in names if names.count(n) > 1})


_LEADING_ZERO = re.compile(r"[+-]?0\d+")
_DIGITS_ONLY = re.compile(r"[+-]?\d+")


def _restore_leading_zero_columns(df: pd.DataFrame, file_obj: Any, encoding: str, sep: str) -> None:
    """Put back text for numeric-looking code columns such as ``00123``.

    pandas turns ``00123`` into the number 123. A numeric column is restored to
    text when every value is digits only and at least one starts with a zero
    (postcodes, product codes, phone-like identifiers). Genuine measurements
    never look like that, so they stay numeric. Each restored column is noted.
    """
    numeric = [c for c in df.columns
               if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
    if not numeric:
        return
    try:
        file_obj.seek(0)
        raw = pd.read_csv(file_obj, encoding=encoding, sep=sep, usecols=numeric, dtype=str)
    except (ValueError, UnicodeError, pd.errors.ParserError):
        return
    finally:
        file_obj.seek(0)
    for col in numeric:
        if col not in raw.columns:
            continue
        values = raw[col].dropna().str.strip()
        if values.empty or not values.str.fullmatch(_DIGITS_ONLY).all():
            continue
        if values.str.fullmatch(_LEADING_ZERO).any():
            df[col] = raw[col].str.strip().where(raw[col].notna())
            _record_import_step(df, "text_columns", [col])
            _add_note(df, f"Column '{col}' contains values with leading zeros (such as {values[values.str.fullmatch(_LEADING_ZERO)].iloc[0]}), "
                          "so it was kept as text to preserve them.")


def load_csv(file_obj: Any, delimiter: str | None = None, *, keep_leading_zeros: bool = True) -> pd.DataFrame:
    """
    Load a CSV file-like object into a DataFrame. The delimiter is
    auto-detected (comma, semicolon, tab or pipe) unless `delimiter` is
    given, and the text encoding is tried in a safe order (see
    _CSV_ENCODING_FALLBACKS).

    With ``keep_leading_zeros`` (the default) numeric-looking code columns such
    as ``00123`` stay text; see ``_restore_leading_zero_columns``. Things the
    importer changed are listed by ``import_notes(df)``.

    Returns a pandas DataFrame. Raises ValueError with a readable
    message if the file is empty, malformed or cannot be decoded.
    """
    for encoding in _CSV_ENCODING_FALLBACKS:
        try:
            sample = _sniff_text(file_obj, encoding)
            sep = delimiter or detect_delimiter(sample)
            file_obj.seek(0) if hasattr(file_obj, "seek") else None
            df = pd.read_csv(file_obj, encoding=encoding, sep=sep)
        except (UnicodeDecodeError, UnicodeError):
            continue
        except pd.errors.EmptyDataError as exc:
            raise ValueError("Could not read CSV file: the file is empty.") from exc
        except pd.errors.ParserError as exc:
            logger.warning("CSV parse error: %s", type(exc).__name__)
            line = re.search(r"line (\d+)", str(exc))
            where = f"Line {line.group(1)}" if line else "A row"
            raise ValueError(
                f"Could not read CSV file: {where} has a different number of fields than the header. "
                "Check the delimiter and any quote characters in the file."
            ) from exc
        except Exception as exc:
            logger.warning("CSV read failed: %s", type(exc).__name__)
            raise ValueError(
                "Could not read CSV file: it does not look like valid delimited text."
            ) from exc
        _record_import_step(df, "source", {"format": "csv", "delimiter": sep, "encoding": encoding})
        for name in _duplicate_header_names(sample, sep):
            _add_note(df, f"The column name '{name}' appears more than once in the file; the repeats were renamed ('{name}.1', ...).")
        if keep_leading_zeros and hasattr(file_obj, "seek"):
            _restore_leading_zero_columns(df, file_obj, encoding, sep)
        return df
    raise ValueError(
        f"Could not read CSV file: it could not be decoded with any of the supported encodings "
        f"({', '.join(_CSV_ENCODING_FALLBACKS)})."
    )


def load_excel(file_obj: Any, sheet_name: int | str = 0, *, keep_leading_zeros: bool = True) -> pd.DataFrame:
    """
    Load one sheet of an Excel (.xlsx / .xls) workbook into a DataFrame.

    ``sheet_name`` is a sheet name or zero-based position (default: the first
    sheet). Only the requested sheet is parsed. Failures (missing engine,
    corrupt file, unknown or empty sheet) are re-raised as a readable
    ValueError. Completely blank rows and unnamed all-empty columns are dropped
    and reported through ``import_notes``. Text cells such as ``00123`` keep their
    leading zeros (pandas would otherwise turn them into 123) unless
    ``keep_leading_zeros`` is False; other numbers stored as text become numbers.
    """
    try:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        with pd.ExcelFile(file_obj) as workbook:
            names = list(workbook.sheet_names)
            if isinstance(sheet_name, int):
                if not 0 <= sheet_name < len(names):
                    raise ValueError(f"Sheet number {sheet_name + 1} does not exist; the workbook has {len(names)} sheet(s).")
                sheet_label = names[sheet_name]
            else:
                if sheet_name not in names:
                    raise ValueError(f"Sheet '{sheet_name}' was not found. Available sheets: {', '.join(names)}.")
                sheet_label = sheet_name
            # dtype=object stops pandas guessing types from text, which would drop leading zeros.
            df = workbook.parse(sheet_label, dtype=object).infer_objects()
    except ImportError as exc:
        raise ValueError(
            "Reading this Excel file requires an additional package "
            "('openpyxl' for .xlsx or 'xlrd' for legacy .xls)."
        ) from exc
    except ValueError as exc:
        if str(exc).startswith(("Sheet ", "Could not")):
            raise
        logger.warning("Excel read failed: %s", type(exc).__name__)
        raise ValueError("Could not read Excel file: it may be corrupt or not a real Excel workbook.") from exc
    except Exception as exc:
        logger.warning("Excel read failed: %s", type(exc).__name__)
        raise ValueError("Could not read Excel file: it may be corrupt or not a real Excel workbook.") from exc

    if df.shape[1] == 0:
        raise ValueError(f"Could not read Excel sheet: sheet '{sheet_label}' has no data.")
    _record_import_step(df, "source", {"format": "excel", "sheet": sheet_label})
    blank_rows = int(df.isna().all(axis=1).sum()) if len(df) else 0
    if blank_rows:
        df = df.dropna(how="all").reset_index(drop=True)
    empty_unnamed = [c for c in df.columns if str(c).startswith("Unnamed:") and df[c].isna().all()]
    if empty_unnamed:
        df = df.drop(columns=empty_unnamed)
    if blank_rows:
        _record_import_step(df, "blank_rows_dropped", True)
        _add_note(df, f"Removed {blank_rows} completely blank row(s) from sheet '{sheet_label}'.")
    if empty_unnamed:
        _record_import_step(df, "empty_unnamed_dropped", [str(c) for c in empty_unnamed])
        _add_note(df, f"Removed {len(empty_unnamed)} empty unnamed column(s) from sheet '{sheet_label}'.")
    # After the blank rows are gone, so a column of whole numbers stays integer instead of float.
    _convert_numeric_text(df, keep_leading_zeros)
    return df


_PLAIN_NUMBER = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?")


def _convert_numeric_text(df: pd.DataFrame, keep_leading_zeros: bool) -> None:
    """Excel cells holding numbers as text ("123", "4.5") become numbers, as CSV columns do.

    Columns containing codes with leading zeros stay text (and are noted) unless
    ``keep_leading_zeros`` is False. Anything that is not purely numeric is untouched.
    """
    for col in df.columns:
        series = df[col]
        if not (pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series)):
            continue
        values = series.dropna()
        if values.empty or not all(isinstance(v, str) for v in values):
            continue
        text = values.str.strip()
        if not text.str.fullmatch(_PLAIN_NUMBER).all():
            continue
        zeros = text.str.fullmatch(_LEADING_ZERO)
        if keep_leading_zeros and zeros.any():
            _add_note(df, f"Column '{col}' contains values with leading zeros (such as {text[zeros].iloc[0]}), "
                          "so it was kept as text to preserve them.")
            continue
        df[col] = pd.to_numeric(series.str.strip(), errors="coerce")
        _record_import_step(df, "numeric_text_columns", [col])


def excel_sheet_names(file_obj: Any) -> list[str]:
    """
    Return the sheet names of an Excel workbook, or [] if they cannot be
    read. Used to offer a worksheet choice when a workbook has several.
    """
    try:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        with pd.ExcelFile(file_obj) as workbook:
            names = list(workbook.sheet_names)
    except Exception:
        names = []
    finally:
        if hasattr(file_obj, "seek"):
            try:
                file_obj.seek(0)
            except Exception:
                pass
    return names


_SEPARATED_NUMBER = r"[+-]?(\d{1,3}([.,]\d{3})+([.,]\d+)?|\d+[.,]\d+)"


# --------------------------------------------------------------------------- decimal commas
_INT = re.compile(r"[+-]?\d+")
_POINT_DECIMAL = re.compile(r"[+-]?\d+\.\d+")
_COMMA_DECIMAL = re.compile(r"[+-]?\d+,\d+")
_DOT_THOUSANDS = re.compile(r"[+-]?\d{1,3}(\.\d{3})+(,\d+)?")      # 1.234  1.234,56  1.234.567
_COMMA_THOUSANDS = re.compile(r"[+-]?\d{1,3}(,\d{3})+(\.\d+)?")    # 1,234  1,234.56  1,234,567


def _classify_number_text(value: str) -> set[str]:
    """Which numeric formats a string could be, e.g. ``1,234`` -> {comma_decimal, comma_thousands}."""
    kinds: set[str] = set()
    if _INT.fullmatch(value):
        kinds.add("int")
    if _POINT_DECIMAL.fullmatch(value):
        kinds.add("point_decimal")
    if _COMMA_DECIMAL.fullmatch(value):
        kinds.add("comma_decimal")
    if _DOT_THOUSANDS.fullmatch(value):
        kinds.add("dot_thousands")
    if _COMMA_THOUSANDS.fullmatch(value):
        kinds.add("comma_thousands")
    return kinds


def _decimal_comma_to_number(series: pd.Series, mode: str) -> tuple[pd.Series | None, str | None]:
    """Try to read a text column as numbers. Returns ``(numbers, None)``, or ``(None, reason)``.

    ``reason`` is only set for an ambiguous column (values like ``1,234`` that could be
    thousands or decimals), so the caller can tell the user to choose a setting.
    """
    values = series.dropna().astype(str).str.strip()
    if values.empty:
        return None, None
    kinds = [_classify_number_text(v) for v in values.unique()]
    if any(not k for k in kinds):
        return None, None                       # contains non-numeric text: leave as text
    present = set().union(*kinds)
    if present <= {"int"}:
        return None, None                       # nothing to convert

    def convert(style: str) -> pd.Series:
        text = series.astype("string").str.strip()
        text = text.str.replace(".", "", regex=False).str.replace(",", ".", regex=False) if style == "comma" \
            else text.str.replace(",", "", regex=False)
        numbers = pd.to_numeric(text, errors="coerce").astype("float64")
        numbers.attrs["style"] = style
        return numbers

    if mode == DECIMAL_COMMA:
        ok = all(k & {"int", "comma_decimal", "dot_thousands"} for k in kinds)
        return (convert("comma"), None) if ok else (None, None)
    if mode == DECIMAL_POINT:
        ok = all(k & {"int", "point_decimal", "comma_thousands"} for k in kinds) and "comma_thousands" in present
        return (convert("point"), None) if ok else (None, None)

    # Auto: convert only when the evidence points to exactly one reading.
    readings = {_only_reading(v, k) for v, k in zip(values.unique(), kinds) if not k <= {"int"}}
    readings.discard("either")
    if readings == {"comma"}:
        ok = all(k & {"int", "comma_decimal", "dot_thousands"} for k in kinds)
        return (convert("comma"), None) if ok else (None, None)
    if readings == {"point"}:
        # Plain "3.14" text needs no repair (and "1.10" might be a version label), so only
        # convert when English thousands separators ("1,234.56") are actually present.
        ok = all(k & {"int", "point_decimal", "comma_thousands"} for k in kinds) and "comma_thousands" in present
        return (convert("point"), None) if ok else (None, None)
    if readings == {"comma", "point"}:
        return None, None                       # mixed formats: do not guess
    return None, "ambiguous"                    # every value could be read either way (e.g. 1,234)


def _only_reading(value: str, kinds: set[str]) -> str:
    """"comma" / "point" when a value can only be one format, "either" when ambiguous."""
    unsigned = value.lstrip("+-")
    comma_ok = bool(kinds & {"comma_decimal", "dot_thousands"})
    point_ok = bool(kinds & {"point_decimal", "comma_thousands"})
    if comma_ok and point_ok:
        # "1,234" (comma decimal vs English thousands) and "1.234" (English decimal vs
        # dot thousands) are genuinely ambiguous, unless a leading zero or repeated
        # separators settle it ("0,123", "1,234,567", "1.234.567").
        if unsigned.startswith("0") and "," in unsigned and "comma_decimal" in kinds:
            return "comma"
        if unsigned.count(",") >= 2:
            return "point"
        if unsigned.count(".") >= 2:
            return "comma"
        return "either"
    if comma_ok:
        return "comma"
    if point_ok:
        return "point"
    return "either"


def convert_decimal_text_columns(df: pd.DataFrame, mode: str = DECIMAL_AUTO) -> pd.DataFrame:
    """Turn text columns such as ``12,50`` or ``1.234,56`` into numbers.

    ``mode``: ``"auto"`` converts only when one reading is unambiguous (e.g.
    ``12,50``, ``1.234,56`` or ``1,234.56``) and records a note for ambiguous
    columns such as ``1,234``; ``","`` forces decimal commas (``.`` = thousands);
    ``"."`` forces decimal points (``,`` = thousands). A column is converted only
    when *every* non-missing value fits, so ordinary text is never touched.
    Returns a copy; conversions are listed by ``import_notes``.
    """
    if mode not in (DECIMAL_AUTO, DECIMAL_POINT, DECIMAL_COMMA):
        raise ValueError("Decimal setting must be 'auto', '.' or ','.")
    result = df.copy()
    result.attrs = copy.deepcopy(dict(df.attrs))
    result.attrs["import_notes"] = import_notes(df)
    for col in result.columns:
        series = result[col]
        if not (pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series)):
            continue
        numbers, reason = _decimal_comma_to_number(series, mode)
        if numbers is not None:
            result[col] = numbers
            _record_import_step(result, "decimal_columns", [{"column": col, "style": numbers.attrs.get("style", "point")}])
            style = "decimal comma" if mode == DECIMAL_COMMA else "decimal point" if mode == DECIMAL_POINT else "number format"
            _add_note(result, f"Column '{col}' was read as numbers ({style}); original text such as '{series.dropna().iloc[0]}' was converted.")
        elif reason == "ambiguous":
            _add_note(result, f"Column '{col}' has values like '{series.dropna().iloc[0]}' that could use a decimal comma or thousands separators, "
                              "so it was left as text. Choose a decimal setting in Import options to convert it.")
    return result


def load_dataset(
    file_obj: Any, file_name: str | None = None, *, sheet_name: int | str = 0,
    decimal: str = DECIMAL_AUTO, keep_leading_zeros: bool = True,
) -> pd.DataFrame:
    """
    Safe, high-level dataset loader. Dispatches to load_csv() or
    load_excel() based on the file extension and returns a clean
    DataFrame ready for use in the application.

    `file_name` is required when `file_obj` doesn't expose a `.name`
    attribute (e.g. Streamlit's UploadedFile already has one).
    ``sheet_name`` (Excel only) picks the worksheet, ``decimal`` is "auto", "."
    or ",", and ``keep_leading_zeros`` (CSV only) keeps codes like 00123 as text.
    Anything the importer changed is listed by ``import_notes(df)``.
    """
    name = file_name or getattr(file_obj, "name", "")
    lowered = str(name).lower()

    if lowered.endswith(".csv"):
        raw = load_csv(file_obj, keep_leading_zeros=keep_leading_zeros)
    elif lowered.endswith((".xlsx", ".xls")):
        raw = load_excel(file_obj, sheet_name=sheet_name, keep_leading_zeros=keep_leading_zeros)
    else:
        raise ValueError(
            f"Unsupported file type for '{name}'. Please upload a CSV, "
            "XLSX, or XLS file."
        )

    raw = convert_decimal_text_columns(raw, decimal)
    return prepare_loaded_dataframe(raw)


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize column names: strip whitespace and replace empty /
    unnamed columns with a stable placeholder (Unnamed_<index>).
    """
    if df is None:
        return df
    result = df.copy()
    result.columns = [
        str(col).strip() if str(col).strip() else f"Unnamed_{i}"
        for i, col in enumerate(result.columns)
    ]
    return result


def detect_datetime_columns(df: pd.DataFrame) -> list:
    """
    Best-effort detection of columns that look like dates/times but
    are not yet stored as a datetime dtype. A column qualifies when
    at least 80% of a sample of its non-null values parse as dates.
    """
    if df is None or df.empty:
        return []
    result = []
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            result.append(col)
        elif pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col]):
            try:
                sample = df[col].dropna().head(30)
                if len(sample) > 0:
                    # Short all-digit strings (ids, codes, years such as "1001") are
                    # not dates, even though pandas can parse some of them as years.
                    digits_only = sample.astype(str).str.fullmatch(r"\d{1,7}")
                    if digits_only.mean() > 0.5:
                        continue
                    # Numbers written with separators ("12,50", "1,234", "1.234.567") are not dates
                    # either, although pandas can read some of them as a year.
                    number_text = sample.astype(str).str.strip().str.fullmatch(_SEPARATED_NUMBER)
                    if number_text.mean() > 0.5:
                        continue
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", UserWarning)   # "could not infer format"
                        parsed = pd.to_datetime(sample, errors="coerce")
                    if parsed.notna().mean() >= 0.8:
                        result.append(col)
            except Exception:
                pass
    return result


def convert_datetime_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a copy of df with every column detected by
    detect_datetime_columns() converted to a real datetime64 dtype.
    """
    if df is None or df.empty:
        return df
    result = df.copy()
    for col in detect_datetime_columns(result):
        result[col] = pd.to_datetime(result[col], errors="coerce")
    return result


def prepare_loaded_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply the standard "just loaded" preparation pipeline to a raw
    DataFrame: clean column names, then detect and convert obvious
    datetime columns. This is the single function that should be
    called right after any raw load so every entry point (sidebar
    uploader, dataset-comparison uploader, future importers) behaves
    consistently.
    """
    if df is None:
        return df
    notes = import_notes(df)
    steps = import_steps(df)
    prepared = clean_column_names(df)
    # Columns that were text and will become datetimes (a script must repeat this conversion).
    to_convert = [c for c in detect_datetime_columns(prepared) if not pd.api.types.is_datetime64_any_dtype(prepared[c])]
    prepared = convert_datetime_columns(prepared)
    if to_convert:
        steps["datetime_columns"] = [str(c) for c in to_convert]
    if notes:
        prepared.attrs["import_notes"] = notes
    if steps:
        prepared.attrs["import_steps"] = steps
    return prepared
