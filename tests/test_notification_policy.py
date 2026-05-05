from datetime import datetime, timezone

from app.services.notification_policy import (
    classify_severity,
    group_events_for_digest,
    is_quiet_hours,
    should_batch,
    should_send_now,
)


class _Settings:
    def __init__(self, mode="smart", quiet=False, min_sev="warning", critical_ignore=True):
        self.delivery_mode = mode
        self.quiet_hours_enabled = quiet
        self.quiet_hours_start = "23:00"
        self.quiet_hours_end = "08:00"
        self.digest_interval_minutes = 180
        self.min_severity_to_notify = min_sev
        self.critical_ignore_quiet_hours = critical_ignore


class _Event:
    def __init__(self, sev):
        self.severity = sev


def test_critical_sends_immediately():
    s = _Settings(mode="smart", quiet=True)
    assert should_send_now(s, _Event("critical"), datetime.now(timezone.utc)) is True


def test_warning_batched_during_quiet_hours():
    s = _Settings(mode="smart", quiet=True)
    now = datetime(2026, 1, 1, 23, 30, tzinfo=timezone.utc)
    assert should_send_now(s, _Event("warning"), now) is False
    assert should_batch(s, _Event("warning"), now) is True


def test_info_ignored_if_min_severity_warning():
    s = _Settings(mode="smart", quiet=False, min_sev="warning")
    assert should_send_now(s, _Event("info"), datetime.now(timezone.utc)) is False


def test_digest_groups_by_severity():
    events = [type("E", (), {"severity": "critical"})(), type("E", (), {"severity": "warning"})()]
    grouped = group_events_for_digest(events)
    assert len(grouped["critical"]) == 1
    assert len(grouped["warning"]) == 1
