"""Глобальный NFT-индекс: индексер, резолвер, UX."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import Settings
from app.services import global_nft_indexer as gidx
from app.services import nft_global_resolve as ngr
from app.services.nft_name_index import parse_collection_number_payload


def _mock_session_local():
    """Каждый вызов SessionLocal() — новый async context manager с awaitable commit/rollback."""
    class _CM:
        async def __aenter__(self):
            m = MagicMock()
            m.commit = AsyncMock()
            m.rollback = AsyncMock()
            return m

        async def __aexit__(self, *a):
            return False

    return _CM()


def _settings(**kw) -> Settings:
    base = {
        "BOT_TOKEN": "x",
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "TONAPI_API_KEY": "k",
        "TONAPI_ENABLED": True,
        "NFT_GLOBAL_INDEX_ENABLED": True,
        "NFT_GLOBAL_INDEX_LIVE_DISCOVERY_FOR_PAID": True,
    }
    base.update(kw)
    return Settings(**base)


@pytest.mark.asyncio
async def test_sync_all_collections_paginates(monkeypatch):
    calls: list[tuple[int, int]] = []

    async def fake_page(*, limit, offset):
        calls.append((limit, offset))
        if offset == 0:
            return [{"address": "EQa", "metadata": {"name": "A"}}], 200, {}
        return [], 200, {}

    client = MagicMock()
    client.configured = True
    client.fetch_nft_collections_page = AsyncMock(side_effect=fake_page)

    monkeypatch.setattr(gidx, "TonAPICollectionClient", lambda s: client)
    monkeypatch.setattr(gidx, "SessionLocal", _mock_session_local)

    async def fake_upsert(session, **k):
        return None

    monkeypatch.setattr(gidx.repo, "upsert_collection", fake_upsert)
    monkeypatch.setattr(gidx.repo, "upsert_alias", fake_upsert)

    st = _settings(NFT_GLOBAL_INDEX_MAX_COLLECTIONS_PER_RUN=0)
    out = await gidx.sync_all_nft_collections(st, limit_per_page=1000, max_collections=None)
    assert len(calls) >= 1
    assert calls[0][0] == 1000
    assert "collections_upserted" in out


@pytest.mark.asyncio
async def test_sync_all_collections_offset_by_batch_len(monkeypatch):
    seq = [
        ([{"address": "EQ1", "metadata": {"name": "N1"}}], 200, {}),
        ([{"address": "EQ2", "metadata": {"name": "N2"}}], 200, {}),
        ([], 200, {}),
    ]

    async def fake_page(*, limit, offset):
        if not seq:
            return [], 200, {}
        if offset == 0:
            return seq[0][0], 200, {}
        if offset == 1:
            return seq[1][0], 200, {}
        return [], 200, {}

    client = MagicMock()
    client.configured = True
    offsets: list[int] = []

    async def wrapped(*, limit, offset):
        offsets.append(offset)
        return await fake_page(limit=limit, offset=offset)

    client.fetch_nft_collections_page = AsyncMock(side_effect=wrapped)

    monkeypatch.setattr(gidx, "TonAPICollectionClient", lambda s: client)
    monkeypatch.setattr(gidx, "SessionLocal", _mock_session_local)
    monkeypatch.setattr(gidx.repo, "upsert_collection", AsyncMock())
    monkeypatch.setattr(gidx.repo, "upsert_alias", AsyncMock())

    st = _settings()
    await gidx.sync_all_nft_collections(st, limit_per_page=1, max_collections=10)
    assert 0 in offsets
    assert 1 in offsets


@pytest.mark.asyncio
async def test_sync_all_collections_handles_429(monkeypatch):
    n429 = {"c": 0}

    async def fake_page(*, limit, offset):
        if n429["c"] < 1:
            n429["c"] += 1
            return [], 429, {}
        return [], 200, {}

    client = MagicMock()
    client.configured = True
    client.fetch_nft_collections_page = AsyncMock(side_effect=fake_page)

    monkeypatch.setattr(gidx, "TonAPICollectionClient", lambda s: client)
    monkeypatch.setattr(gidx, "SessionLocal", _mock_session_local)
    monkeypatch.setattr(gidx.repo, "upsert_collection", AsyncMock())
    monkeypatch.setattr(gidx.repo, "upsert_alias", AsyncMock())
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    st = _settings()
    out = await gidx.sync_all_nft_collections(st, limit_per_page=10, max_collections=5)
    assert out.get("errors", 0) >= 0


@pytest.mark.asyncio
async def test_sync_cli_sleep_ms_respected(monkeypatch):
    seq = [
        ([{"address": "EQ1", "metadata": {"name": "N1"}}], 200, {}),
        ([], 200, {}),
    ]

    async def fake_page(*, limit, offset):
        return seq.pop(0)

    client = MagicMock()
    client.configured = True
    client.fetch_nft_collections_page = AsyncMock(side_effect=fake_page)
    monkeypatch.setattr(gidx, "TonAPICollectionClient", lambda s: client)
    monkeypatch.setattr(gidx, "SessionLocal", _mock_session_local)
    monkeypatch.setattr(gidx.repo, "upsert_collection", AsyncMock())
    monkeypatch.setattr(gidx.repo, "upsert_alias", AsyncMock())
    slp = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", slp)
    st = _settings()
    await gidx.sync_all_nft_collections(st, limit_per_page=1, max_collections=2, sleep_ms=1200)
    assert slp.await_args_list
    assert any(abs(float(c.args[0]) - 1.2) < 0.001 for c in slp.await_args_list if c.args)


@pytest.mark.asyncio
async def test_sample_aliases_from_item_names(monkeypatch):
    items = [
        {
            "address": "EQNFT1",
            "metadata": {"name": "Bunny Muffin #974"},
            "index": 974,
        }
    ]

    client = MagicMock()
    client.configured = True
    client.fetch_collection_items_page_raw = AsyncMock(return_value=(items, 200, "", {}))

    monkeypatch.setattr(gidx, "TonAPICollectionClient", lambda s: client)
    monkeypatch.setattr(gidx, "SessionLocal", _mock_session_local)
    monkeypatch.setattr(gidx.repo, "upsert_item", AsyncMock())
    monkeypatch.setattr(gidx.repo, "upsert_alias", AsyncMock())
    monkeypatch.setattr(gidx.repo, "update_collection_index_state", AsyncMock())

    st = _settings()
    out = await gidx.sample_collection_aliases(st, "EQColl", sample_items=5)
    assert out.get("sampled") == 1


@pytest.mark.asyncio
async def test_index_collection_items_resume(monkeypatch):
    st = _settings(NFT_GLOBAL_INDEX_FULL_ITEMS_ENABLED=True)

    row = MagicMock()
    row.last_index_offset = 100
    row.next_item_index = None
    row.items_indexed_count = 50

    client = MagicMock()
    client.configured = True
    client.fetch_collection_items_page_raw = AsyncMock(return_value=([], 200, "", {}))

    monkeypatch.setattr(gidx, "TonAPICollectionClient", lambda s: client)
    monkeypatch.setattr(gidx, "SessionLocal", _mock_session_local)
    monkeypatch.setattr(gidx.repo, "get_collection_row", AsyncMock(return_value=row))
    monkeypatch.setattr(gidx.repo, "upsert_item", AsyncMock())
    monkeypatch.setattr(gidx.repo, "upsert_alias", AsyncMock())
    monkeypatch.setattr(gidx.repo, "update_collection_index_state", AsyncMock())

    out = await gidx.index_collection_items(st, "EQC", limit_per_page=50, max_items=None, resume=True)
    client.fetch_collection_items_page_raw.assert_awaited()
    call_kw = client.fetch_collection_items_page_raw.await_args
    assert call_kw[1]["offset"] == 100


@pytest.mark.asyncio
async def test_index_collection_items_no_infinite_loop(monkeypatch):
    st = _settings(NFT_GLOBAL_INDEX_FULL_ITEMS_ENABLED=True)
    row = MagicMock(last_index_offset=0, next_item_index=None, items_indexed_count=0)

    async def always_items(*a, **k):
        return [{"address": "EQX", "metadata": {"name": "X #1"}}], 200, "", {}

    client = MagicMock()
    client.configured = True
    client.fetch_collection_items_page_raw = AsyncMock(side_effect=always_items)

    monkeypatch.setattr(gidx, "TonAPICollectionClient", lambda s: client)
    monkeypatch.setattr(gidx, "SessionLocal", _mock_session_local)
    monkeypatch.setattr(gidx.repo, "get_collection_row", AsyncMock(return_value=row))
    monkeypatch.setattr(gidx.repo, "upsert_item", AsyncMock())
    monkeypatch.setattr(gidx.repo, "upsert_alias", AsyncMock())
    monkeypatch.setattr(gidx.repo, "update_collection_index_state", AsyncMock())

    out = await gidx.index_collection_items(st, "EQC", limit_per_page=10, max_items=25, resume=False)
    assert out["indexed"] <= 25


@pytest.mark.asyncio
async def test_resolve_from_item_index(monkeypatch):
    hit = MagicMock()
    hit.nft_address = "EQTARGET________________________________________900"

    async def fake_find(session, bn, num):
        return [hit]

    nft_payload = {
        "address": hit.nft_address,
        "collection": {"address": "EQC", "name": "C", "metadata": {"name": "C"}},
        "metadata": {"name": "Bunny Muffin #974"},
    }

    client = MagicMock()
    client.get_nft = AsyncMock(return_value=nft_payload)

    monkeypatch.setattr("app.services.nft_global_resolve.repo.find_items_by_base_and_number", fake_find)
    monkeypatch.setattr(
        "app.services.nft_global_resolve.repo.find_aliases_by_normalized", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        "app.services.nft_global_resolve.repo.find_collection_by_name_normalized", AsyncMock(return_value=[])
    )

    st = _settings()
    tgt, err = await ngr.try_resolve_via_global_index(
        MagicMock(), st, client, display_collection="Bunny Muffin", number=974
    )
    assert err is None
    assert tgt is not None
    assert tgt.address == hit.nft_address


@pytest.mark.asyncio
async def test_unknown_paid_triggers_live_discovery(monkeypatch):
    from app.services import real_market_collection_scan as rms
    from app.services.nft_collection_resolve import CollectionResolutionResult

    async def fake_try(session, settings, client, *, display_collection, number):
        return None, None

    monkeypatch.setattr("app.services.nft_global_resolve.try_resolve_via_global_index", fake_try)
    monkeypatch.setattr(
        "app.services.real_market_collection_scan.resolve_collection_address_by_name",
        AsyncMock(
            return_value=CollectionResolutionResult(
                address=None, name=None, source="none", confidence="low", candidates=[]
            )
        ),
    )
    enq = AsyncMock()
    monkeypatch.setattr("app.services.nft_global_resolve.enqueue_live_discovery", enq)

    st = _settings(NFT_GLOBAL_INDEX_ENABLED=True, NFT_GLOBAL_INDEX_LIVE_DISCOVERY_FOR_PAID=True)
    client = MagicMock()
    client.configured = True
    user = MagicMock(plan="pro")

    monkeypatch.setattr("app.db.session.SessionLocal", _mock_session_local)

    tgt, err = await rms.resolve_target_for_full_market("Unknown Xyz #12", user, st, client)
    assert tgt is None
    assert err and "расширенный поиск" in err
    assert "mock" not in err.lower()
    assert enq.called


@pytest.mark.asyncio
async def test_unknown_free_asks_for_link(monkeypatch):
    from app.services import real_market_collection_scan as rms
    from app.services.nft_collection_resolve import CollectionResolutionResult

    async def fake_try(session, settings, client, *, display_collection, number):
        return None, None

    monkeypatch.setattr("app.services.nft_global_resolve.try_resolve_via_global_index", fake_try)
    monkeypatch.setattr(
        "app.services.real_market_collection_scan.resolve_collection_address_by_name",
        AsyncMock(
            return_value=CollectionResolutionResult(
                address=None, name=None, source="none", confidence="low", candidates=[]
            )
        ),
    )

    st = _settings(NFT_GLOBAL_INDEX_ENABLED=True)
    client = MagicMock()
    client.configured = True
    user = MagicMock(plan="free")

    monkeypatch.setattr("app.db.session.SessionLocal", _mock_session_local)

    tgt, err = await rms.resolve_target_for_full_market("Unknown Xyz #12", user, st, client)
    assert tgt is None
    assert "не нашёл nft" in err.lower()


def test_no_collections_json_in_user_messages():
    m1 = ngr.message_unknown_collection_paid("Demo")
    m2 = ngr.message_unknown_collection_free("Demo")
    assert "collections.json" not in m1.lower()
    assert "collections.json" not in m2.lower()


def test_no_mock_words_in_index_messages():
    m1 = ngr.message_unknown_collection_paid("X")
    m2 = ngr.message_unknown_collection_free("X")
    low = (m1 + m2).lower()
    assert "mock" not in low


def test_parse_collection_number_payload_compat():
    assert parse_collection_number_payload("Timeless Book #38902") == ("Timeless Book", 38902)
