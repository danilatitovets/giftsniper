from app.services.smart_alerts import payload_hash, should_send_smart_alert
from datetime import datetime, timedelta, timezone


def test_payload_hash_prevents_duplicates():
    h = payload_hash("abc")
    assert should_send_smart_alert(None, 180, h, h) is False


def test_cooldown_blocks_repeated_alert():
    now = datetime.now(timezone.utc)
    assert should_send_smart_alert(now, 180, "new", "old") is False


def test_hash_change_after_cooldown_sends():
    past = datetime.now(timezone.utc) - timedelta(hours=4)
    assert should_send_smart_alert(past, 180, "new", "old") is True
