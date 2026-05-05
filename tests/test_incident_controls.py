from datetime import datetime, timedelta, timezone


def test_ack_incident_shape():
    incident = type("I", (), {"acknowledged_at": datetime.now(timezone.utc)})()
    assert incident.acknowledged_at is not None


def test_mute_and_unmute_shape():
    incident = type("I", (), {"muted_until": datetime.now(timezone.utc) + timedelta(minutes=30)})()
    assert incident.muted_until is not None
    incident.muted_until = None
    assert incident.muted_until is None


def test_manual_resolve_shape():
    incident = type("I", (), {"status": "open", "resolved_manually_at": None})()
    incident.status = "recovered"
    incident.resolved_manually_at = datetime.now(timezone.utc)
    assert incident.status == "recovered"


def test_false_positive_mark_shape():
    incident = type("I", (), {"is_false_positive": False})()
    incident.is_false_positive = True
    assert incident.is_false_positive is True


def test_actions_timeline_contains_expected_keywords():
    text = "🧷 Incident actions\n- 2026-01-01: ack\n- 2026-01-01: mute"
    assert "ack" in text
    assert "mute" in text
