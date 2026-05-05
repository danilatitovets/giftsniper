from datetime import datetime, timedelta, timezone

from app.services.smart_alerts import payload_hash, should_send_smart_alert


def test_no_duplicate_alert_if_payload_hash_same():
    now = datetime.now(timezone.utc) - timedelta(hours=5)
    h = payload_hash("same")
    assert should_send_smart_alert(now, cooldown_minutes=1, new_hash=h, old_hash=h) is False


def test_cooldown_blocks_repeated_alert():
    now = datetime.now(timezone.utc)
    assert should_send_smart_alert(now, cooldown_minutes=180, new_hash="new", old_hash="old") is False
