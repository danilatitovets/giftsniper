from pathlib import Path

from app.services.pricing_change_policy import format_pricing_change_policy_report


def test_policy_text_no_guaranteed_profit_phrase():
    data = {
        "ready": False,
        "not_ready_reasons": ["sample"],
        "evidence": {},
        "suggested_safe_changes": {},
        "risks": ["x"],
    }
    txt = format_pricing_change_policy_report(data)
    assert "гарант" not in txt.lower()


def test_no_auto_env_in_pricing_tuner_docstring():
    p = Path(__file__).resolve().parents[1] / "app" / "services" / "pricing_tuner.py"
    assert "Not auto-applied" in p.read_text(encoding="utf-8")
