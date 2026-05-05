from app.bot.handlers.alerts import _parse_smart_type


def test_smart_alert_on_off_parser():
    assert _parse_smart_type("/smart_alert_on regime_change", "/smart_alert_on") == "regime_change"
    assert _parse_smart_type("/smart_alert_off stay_in_cash", "/smart_alert_off") == "stay_in_cash"


def test_health_dashboard_formats_key_sections():
    text = (
        "🩺 Health Dashboard\n"
        "Market regime: risk_off\n"
        "Universe collections: 3\n"
        "Active smart alerts: 2\n"
        "Data freshness summary: stale\n"
    )
    assert "Market regime:" in text
    assert "Active smart alerts:" in text
