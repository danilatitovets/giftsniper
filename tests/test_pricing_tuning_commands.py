from app.services.pricing_tuner import (
    analyze_pricing_accuracy,
    format_pricing_config_suggest,
    format_pricing_tuning_report,
)


def test_tuning_report_empty():
    rep = analyze_pricing_accuracy([])
    txt = format_pricing_tuning_report(rep)
    assert "0" in txt or "Закрытых" in txt


def test_suggest_after_analyze():
    analyze_pricing_accuracy([])
    s = format_pricing_config_suggest()
    assert isinstance(s, str)
