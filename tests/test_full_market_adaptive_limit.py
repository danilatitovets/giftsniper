"""Adaptive TonAPI page limit for full collection scan."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.services.real_market_collection_scan import parse_page_limit_fallbacks, scan_collection_listings
from app.services.tonapi_collection_client import TonAPICollectionClient


def _settings(**kw: object) -> Settings:
    base: dict = {
        "BOT_TOKEN": "x",
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "TONAPI_ENABLED": True,
        "TONAPI_API_KEY": "unit-test-key",
    }
    base.update(kw)
    return Settings(**base)


@pytest.mark.asyncio
async def test_full_market_adaptive_limit_fallback(monkeypatch: pytest.MonkeyPatch):
    settings = _settings(
        full_market_page_limit=10000,
        full_market_min_page_limit=100,
        full_market_max_items=500,
        full_market_request_sleep_ms=0,
        full_market_progress_every_items=50,
    )
    client = TonAPICollectionClient(settings)
    seen: list[tuple[int, int]] = []

    async def fake_raw(self, _addr: str, *, limit: int, offset: int):
        seen.append((limit, offset))
        if limit == 10000 and offset == 0:
            return [], 400, "limit too large", None
        if limit == 5000 and offset == 0:
            return [{"address": "0:a", "metadata": {"name": "T #1"}}], 200, "", None
        return [], 200, "", None

    monkeypatch.setattr(TonAPICollectionClient, "fetch_collection_items_page_raw", fake_raw)
    rows, loaded, partial, _t = await scan_collection_listings(client, settings, "0:c", on_progress=None)
    assert seen[0] == (10000, 0)
    assert seen[1] == (5000, 0)
    assert loaded == 1
    assert partial is False


@pytest.mark.asyncio
async def test_full_market_no_infinite_loop_on_empty_batch(monkeypatch: pytest.MonkeyPatch):
    settings = _settings(
        full_market_page_limit=500,
        full_market_min_page_limit=100,
        full_market_max_items=50000,
        full_market_request_sleep_ms=0,
    )
    client = TonAPICollectionClient(settings)
    calls = {"n": 0}

    async def fake_raw(self, _addr: str, *, limit: int, offset: int):
        calls["n"] += 1
        return [], 200, "", None

    monkeypatch.setattr(TonAPICollectionClient, "fetch_collection_items_page_raw", fake_raw)
    rows, loaded, partial, _t = await scan_collection_listings(client, settings, "0:c", on_progress=None)
    assert calls["n"] == 1
    assert loaded == 0
    assert rows == []
    assert partial is False


@pytest.mark.asyncio
async def test_full_market_429_does_not_immediately_reduce_limit(monkeypatch: pytest.MonkeyPatch):
    settings = _settings(
        full_market_page_limit=1000,
        full_market_min_page_limit=100,
        full_market_max_items=500,
        full_market_request_sleep_ms=0,
        full_market_rate_limit_sleep_seconds=0.001,
        full_market_429_streak_before_reduce_limit=3,
        full_market_progress_every_items=50,
    )
    client = TonAPICollectionClient(settings)
    limits: list[int] = []
    state = {"done": False}

    async def fake_raw(self, _addr: str, *, limit: int, offset: int):
        limits.append(limit)
        if len(limits) <= 2:
            return [], 429, "", None
        if not state["done"]:
            state["done"] = True
            return [{"address": "0:z", "metadata": {"name": "Z #1"}}], 200, "", None
        return [], 200, "", None

    monkeypatch.setattr(TonAPICollectionClient, "fetch_collection_items_page_raw", fake_raw)
    rows, loaded, partial, _t = await scan_collection_listings(client, settings, "0:c", on_progress=None)
    assert limits[:2] == [1000, 1000]
    assert limits[2] == 1000
    assert loaded == 1
    assert partial is False


def test_parse_page_limit_fallbacks_default_order() -> None:
    lad = parse_page_limit_fallbacks("")
    assert lad[0] == 10000
    assert 200 in lad
    assert lad[-1] == 100


@pytest.mark.asyncio
async def test_full_scan_starts_with_10000(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(
        full_market_page_limit=10000,
        full_market_min_page_limit=100,
        full_market_max_items=5000,
        full_market_request_sleep_ms=0,
    )
    client = TonAPICollectionClient(settings)
    seen: list[int] = []

    async def fake_raw(self, _addr: str, *, limit: int, offset: int):
        seen.append(limit)
        return [], 200, "", None

    monkeypatch.setattr(TonAPICollectionClient, "fetch_collection_items_page_raw", fake_raw)
    await scan_collection_listings(client, settings, "0:c", on_progress=None)
    assert seen[0] == 10000


@pytest.mark.asyncio
async def test_limit_too_large_fallback_to_1000(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(
        full_market_page_limit=10000,
        full_market_min_page_limit=100,
        full_market_max_items=500,
        full_market_request_sleep_ms=0,
    )
    client = TonAPICollectionClient(settings)
    seq: list[tuple[int, int]] = []

    async def fake_raw(self, _addr: str, *, limit: int, offset: int):
        seq.append((limit, offset))
        if offset != 0:
            return [], 200, "", {"total": 10}
        if limit in (10000, 5000, 2000):
            return [], 400, "limit too large", None
        if limit == 1000:
            return [{"address": "0:a1", "metadata": {"name": "N"}}], 200, "", {"total": 10}
        return [], 200, "", {"total": 10}

    monkeypatch.setattr(TonAPICollectionClient, "fetch_collection_items_page_raw", fake_raw)
    rows, loaded, partial, _t = await scan_collection_listings(client, settings, "0:c", on_progress=None)
    assert (10000, 0) in seq
    assert (5000, 0) in seq
    assert (2000, 0) in seq
    assert (1000, 0) in seq
    assert loaded >= 1
    assert len(rows) >= 1


@pytest.mark.asyncio
async def test_429_backoff_before_limit_decrease(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(
        full_market_page_limit=10000,
        full_market_min_page_limit=100,
        full_market_max_items=5000,
        full_market_request_sleep_ms=0,
        full_market_rate_limit_sleep_seconds=0.001,
        full_market_429_streak_before_reduce_limit=3,
    )
    client = TonAPICollectionClient(settings)
    limits: list[int] = []

    async def fake_raw(self, _addr: str, *, limit: int, offset: int):
        limits.append(limit)
        if len(limits) <= 2:
            return [], 429, "", None
        return [{"address": "0:z", "metadata": {"name": "Z #1"}}], 200, "", None

    monkeypatch.setattr(TonAPICollectionClient, "fetch_collection_items_page_raw", fake_raw)
    await scan_collection_listings(client, settings, "0:c", on_progress=None)
    assert limits[0] == limits[1] == 10000
    assert limits[2] == 10000


@pytest.mark.asyncio
async def test_silent_api_cap_does_not_stop_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(
        full_market_page_limit=10000,
        full_market_min_page_limit=100,
        full_market_max_items=3500,
        full_market_request_sleep_ms=0,
        full_market_progress_every_items=5000,
    )
    client = TonAPICollectionClient(settings)
    calls: list[tuple[int, int]] = []

    async def fake_raw(self, _addr: str, *, limit: int, offset: int):
        calls.append((limit, offset))
        if offset >= 3000:
            return [], 200, "", {"total": 300_000}
        return (
            [{"address": f"0:x{offset + i}", "metadata": {"name": f"N {offset + i}"}} for i in range(1000)],
            200,
            "",
            {"total": 300_000},
        )

    monkeypatch.setattr(TonAPICollectionClient, "fetch_collection_items_page_raw", fake_raw)
    _rows, loaded, partial, _t = await scan_collection_listings(client, settings, "0:c", on_progress=None)
    assert loaded >= 3000
    assert partial is True
    assert len(calls) >= 4


@pytest.mark.asyncio
async def test_offset_increments_by_batch_len(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(
        full_market_page_limit=10000,
        full_market_min_page_limit=100,
        full_market_max_items=5000,
        full_market_request_sleep_ms=0,
    )
    client = TonAPICollectionClient(settings)
    seq: list[tuple[int, int]] = []

    async def fake_raw(self, _addr: str, *, limit: int, offset: int):
        seq.append((limit, offset))
        if offset == 0:
            return (
                [{"address": f"0:a{i}", "metadata": {"name": f"T #{i}"}} for i in range(1000)],
                200,
                "",
                None,
            )
        return [], 200, "", None

    monkeypatch.setattr(TonAPICollectionClient, "fetch_collection_items_page_raw", fake_raw)
    await scan_collection_listings(client, settings, "0:c", on_progress=None)
    assert seq[0] == (10000, 0)
    assert seq[1][1] == 1000


@pytest.mark.asyncio
async def test_full_scan_reaches_total(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(
        full_market_page_limit=5000,
        full_market_min_page_limit=100,
        full_market_max_items=100_000,
        full_market_request_sleep_ms=0,
    )
    client = TonAPICollectionClient(settings)

    async def fake_raw(self, _addr: str, *, limit: int, offset: int):
        if offset >= 25_000:
            return [], 200, "", {"total": 25_000}
        batch = [{"address": f"0:b{offset + i}", "metadata": {"name": f"X #{offset + i}"}} for i in range(5000)]
        return batch, 200, "", {"total": 25_000}

    monkeypatch.setattr(TonAPICollectionClient, "fetch_collection_items_page_raw", fake_raw)
    _rows, loaded, partial, total = await scan_collection_listings(client, settings, "0:c", on_progress=None)
    assert total == 25_000
    assert loaded >= 25_000
    assert partial is False


@pytest.mark.asyncio
async def test_no_infinite_loop_when_errors_repeat(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(
        full_market_page_limit=1000,
        full_market_min_page_limit=100,
        full_market_max_items=50_000,
        full_market_request_sleep_ms=0,
    )
    client = TonAPICollectionClient(settings)
    calls = {"n": 0}

    async def fake_raw(self, _addr: str, *, limit: int, offset: int):
        calls["n"] += 1
        return [], 503, "boom", None

    monkeypatch.setattr(TonAPICollectionClient, "fetch_collection_items_page_raw", fake_raw)
    _rows, loaded, partial, _t = await scan_collection_listings(client, settings, "0:c", on_progress=None)
    assert calls["n"] <= 10
    assert partial is True
    assert loaded == 0
