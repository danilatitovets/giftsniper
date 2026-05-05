from __future__ import annotations

import asyncio
import time

_LOCK = asyncio.Lock()
_LAST_REQUEST_TS = 0.0


async def wait_turn(*, rps_limit: float, min_interval_ms: int) -> None:
    global _LAST_REQUEST_TS
    interval = max(0.0, float(min_interval_ms) / 1000.0)
    if rps_limit > 0:
        interval = max(interval, 1.0 / float(rps_limit))
    async with _LOCK:
        now = time.monotonic()
        wait_s = interval - (now - _LAST_REQUEST_TS)
        if wait_s > 0:
            await asyncio.sleep(wait_s)
        _LAST_REQUEST_TS = time.monotonic()
