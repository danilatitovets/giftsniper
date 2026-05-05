from app.services.incident_manager import detect_recovery, format_recovery_message


def test_recovery_closes_condition_for_regime():
    ok, _ = detect_recovery("regime_change", {"prev_regime": "risk_off", "current_regime": "neutral"})
    assert ok is True


def test_recovery_notification_formatted():
    incident = type("I", (), {"id": 1, "alert_type": "regime_change"})()
    text = format_recovery_message(incident, "Было risk_off, стало neutral")
    assert "Recovery" in text
