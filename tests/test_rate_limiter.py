from datetime import datetime, timedelta, timezone

from app.services.rate_limiter import check_command_rate_limit


def test_rate_limiter_blocks_repeated_heavy_commands():
    user_id = 999001
    now = datetime.now(timezone.utc)
    for _ in range(2):
        ok, _ = check_command_rate_limit(
            user_id,
            "/scan",
            per_minute_limit=10,
            heavy_per_hour_limit=2,
            now=now,
        )
        assert ok
    ok, retry = check_command_rate_limit(
        user_id,
        "/scan",
        per_minute_limit=10,
        heavy_per_hour_limit=2,
        now=now + timedelta(seconds=1),
    )
    assert ok is False
    assert retry > 0
