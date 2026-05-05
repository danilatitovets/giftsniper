from datetime import datetime, timedelta, timezone

from app.services.incident_manager import escalate_incident


def test_three_warnings_escalate_to_critical():
    incident = type("I", (), {"event_count": 3, "first_seen_at": datetime.now(timezone.utc) - timedelta(hours=1)})()
    event = type("E", (), {"severity": "warning", "alert_type": "strength_drop"})()
    sev, _ = escalate_incident(incident, event, datetime.now(timezone.utc))
    assert sev == "critical"


def test_concentration_lasting_over_6h_escalates():
    incident = type("I", (), {"event_count": 1, "first_seen_at": datetime.now(timezone.utc) - timedelta(hours=7)})()
    event = type("E", (), {"severity": "warning", "alert_type": "concentration_risk"})()
    sev, _ = escalate_incident(incident, event, datetime.now(timezone.utc))
    assert sev == "critical"
