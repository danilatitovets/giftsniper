from app.services.notification_policy import format_digest


def test_digest_groups_incidents_separately():
    events = [
        type("E", (), {"severity": "critical", "title": "x", "incident_id": 2, "alert_type": "concentration_risk"})(),
        type("E", (), {"severity": "info", "title": "rec", "incident_id": 2, "alert_type": "regime_change_recovery"})(),
    ]
    text = format_digest(events)
    assert "Ongoing incidents" in text
    assert "Recoveries" in text
