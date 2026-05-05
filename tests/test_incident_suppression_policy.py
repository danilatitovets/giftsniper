from datetime import datetime, timedelta, timezone

from app.services.incident_manager import should_suppress_event


def _incident(**kwargs):
    base = {
        "last_payload_hash": "hash-1",
        "last_seen_at": datetime.now(timezone.utc) - timedelta(minutes=20),
        "muted_until": None,
        "is_false_positive": False,
        "acknowledged_at": None,
    }
    base.update(kwargs)
    return type("I", (), base)()


def _event(**kwargs):
    base = {"payload_hash": "hash-2", "severity": "warning"}
    base.update(kwargs)
    return type("E", (), base)()


def test_muted_incident_suppresses_delivery():
    incident = _incident(muted_until=datetime.now(timezone.utc) + timedelta(minutes=30))
    assert should_suppress_event(incident, _event(), datetime.now(timezone.utc)) is True


def test_acked_warning_not_resent():
    incident = _incident(acknowledged_at=datetime.now(timezone.utc))
    assert should_suppress_event(incident, _event(severity="warning"), datetime.now(timezone.utc)) is True


def test_critical_escalation_bypasses_ack_suppression():
    incident = _incident(acknowledged_at=datetime.now(timezone.utc), last_seen_at=datetime.now(timezone.utc) - timedelta(minutes=30))
    assert should_suppress_event(incident, _event(severity="critical"), datetime.now(timezone.utc)) is False


def test_false_positive_same_payload_suppressed():
    incident = _incident(is_false_positive=True, last_payload_hash="same")
    assert should_suppress_event(incident, _event(payload_hash="same"), datetime.now(timezone.utc)) is True
