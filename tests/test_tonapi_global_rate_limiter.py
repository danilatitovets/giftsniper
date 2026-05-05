from __future__ import annotations

import asyncio
import time

import pytest

from app.services import tonapi_rate_limiter as limiter


@pytest.mark.asyncio
async def test_global_rate_limiter_serializes_tonapi_requests():
    limiter._LAST_REQUEST_TS = 0.0
    t0 = time.monotonic()
    await asyncio.gather(
        limiter.wait_turn(rps_limit=10_000, min_interval_ms=120),
        limiter.wait_turn(rps_limit=10_000, min_interval_ms=120),
        limiter.wait_turn(rps_limit=10_000, min_interval_ms=120),
    )
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.20
