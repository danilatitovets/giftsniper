from datetime import datetime, timedelta, timezone

from app.services.incident_analytics import (
    calculate_incident_age,
    calculate_time_to_recover,
    calculate_false_positive_rate,
    summarize_incidents,
)


def _incident(**kwargs):
    base = {
        "first_seen_at": datetime.now(timezone.utc) - timedelta(hours=2),
        "recovered_at": None,
        "severity": "warning",
        "muted_until": None,
        "acknowledged_at": None,
        "alert_type": "data_stale",
        "is_false_positive": False,
    }
    base.update(kwargs)
    return type("I", (), base)()


def test_time_to_recover_calculation():
    inc = _incident(recovered_at=datetime.now(timezone.utc))
    assert calculate_time_to_recover(inc) is not None


def test_incident_age_positive():
    inc = _incident()
    assert calculate_incident_age(inc) > 0


def test_summarize_counts_open_critical_recovered():
    open_incidents = [_incident(severity="critical"), _incident(severity="warning")]
    recovered = [_incident(recovered_at=datetime.now(timezone.utc))]
    summary = summarize_incidents(open_incidents, recovered)
    assert summary["open_count"] == 2
    assert summary["critical_count"] == 1
    assert summary["recovered_count"] == 1


def test_false_positive_rate():
    incidents = [_incident(is_false_positive=True), _incident(is_false_positive=False)]
    count, rate = calculate_false_positive_rate(incidents)
    assert count == 1
    assert rate > 0
