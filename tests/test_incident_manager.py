from datetime import datetime, timedelta, timezone

from app.services.incident_manager import should_suppress_event


def test_same_payload_suppressed():
    incident = type("I", (), {"last_payload_hash": "abc", "last_seen_at": datetime.now(timezone.utc)})()
    event = type("E", (), {"payload_hash": "abc"})()
    assert should_suppress_event(incident, event, datetime.now(timezone.utc)) is True


def test_first_event_not_suppressed():
    event = type("E", (), {"payload_hash": "abc"})()
    assert should_suppress_event(None, event, datetime.now(timezone.utc)) is False
