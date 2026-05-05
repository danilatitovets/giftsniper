"""No user-facing text should promise guaranteed profit (Stage 31 QA)."""

from pathlib import Path

FORBIDDEN = ("гарантированная прибыль", "обещаем прибыль", "100% profit", "guaranteed profit")


def _iter_py_files(root: Path):
    for p in root.rglob("*.py"):
        if "venv" in p.parts or ".venv" in p.parts:
            continue
        yield p


def test_no_guaranteed_profit_phrase_in_services_and_handlers():
    root = Path(__file__).resolve().parents[1] / "app"
    bad = []
    for p in _iter_py_files(root):
        try:
            t = p.read_text(encoding="utf-8").lower()
        except OSError:
            continue
        for f in FORBIDDEN:
            if f.lower() in t:
                bad.append((p, f))
    assert not bad, bad
