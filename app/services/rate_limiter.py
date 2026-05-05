from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone


HEAVY_COMMANDS = {
    "/scan",
    "/scan_universe",
    "/capital_plan_universe",
    "/universe_report",
    "/market_regime",
    "/collection_strength",
    "/flip_plan",
    "/lite_plan",
    "/budget_deals",
    "/compound_plan",
    "/sell_to_buy",
    "/m4_plan",
}

_per_minute: dict[int, deque[datetime]] = defaultdict(deque)
_heavy_per_hour: dict[int, deque[datetime]] = defaultdict(deque)


def _cleanup(bucket: deque[datetime], window_seconds: int, now: datetime) -> None:
    threshold = now - timedelta(seconds=window_seconds)
    while bucket and bucket[0] < threshold:
        bucket.popleft()


def _seconds_until_reset(bucket: deque[datetime], window_seconds: int, now: datetime) -> int:
    if not bucket:
        return 0
    reset_at = bucket[0] + timedelta(seconds=window_seconds)
    return max(1, int((reset_at - now).total_seconds()))


def check_command_rate_limit(
    user_id: int,
    command: str,
    *,
    per_minute_limit: int,
    heavy_per_hour_limit: int,
    now: datetime | None = None,
) -> tuple[bool, int]:
    ts = now or datetime.now(timezone.utc)
    minute_bucket = _per_minute[user_id]
    _cleanup(minute_bucket, 60, ts)
    if len(minute_bucket) >= per_minute_limit:
        return False, _seconds_until_reset(minute_bucket, 60, ts)
    minute_bucket.append(ts)

    if command in HEAVY_COMMANDS:
        hour_bucket = _heavy_per_hour[user_id]
        _cleanup(hour_bucket, 3600, ts)
        if len(hour_bucket) >= heavy_per_hour_limit:
            return False, _seconds_until_reset(hour_bucket, 3600, ts)
        hour_bucket.append(ts)

    return True, 0
