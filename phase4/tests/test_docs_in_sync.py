"""Generated documentation must match the code it describes."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_chart_matrix_doc_is_up_to_date():
    spec = importlib.util.spec_from_file_location("make_chart_matrix", ROOT / "scripts" / "make_chart_matrix.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    committed = (ROOT / "docs" / "CHART_COMPATIBILITY_MATRIX.md").read_text(encoding="utf-8")
    assert module.render().strip() == committed.strip(), "run: python scripts/make_chart_matrix.py"


def test_requirements_files_are_pinned_or_deliberately_loose():
    lines = [l.strip() for l in (ROOT / "requirements.txt").read_text().splitlines() if l.strip() and not l.startswith("#")]
    pinned = [l for l in lines if "==" in l]
    loose = [l for l in lines if "==" not in l]
    assert len(pinned) >= 6 and set(loose) <= {"xlrd>=2.0.1", "statsmodels", "pillow>=13.0.0,<14"}
