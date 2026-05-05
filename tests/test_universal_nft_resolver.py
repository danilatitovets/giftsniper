from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.config import Settings
from app.services.real_market_collection_scan import TargetNftInfo
from app.services.universal_nft_resolver import resolve_universal_nft


def _settings(**kw: object) -> Settings:
    base: dict = {
        "BOT_TOKEN": "x",
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "TONAPI_ENABLED": True,
        "TONAPI_API_KEY": "k",
        "FULL_MARKET_SCAN_ENABLED": True,
        "NFT_GLOBAL_INDEX_ENABLED": True,
    }
    base.update(kw)
    return Settings(**base)


def _target() -> TargetNftInfo:
    return TargetNftInfo(
        name="Pretty Posy #28864",
        number=28864,
        address="EQf_tg_gift____________________8qtF4fAABwwL-e",
        collection_name="Pretty Posy",
        collection_address="EQA0EzRYX5wm_q46_NX8b7EYhtOkXfXgsr06ETbov1a7StZl",
        model="Aurora",
        backdrop="Blue",
        symbol="Star",
        image_url="https://img.example/nft.png",
    )


@pytest.mark.asyncio
async def test_address_success_tonapi(monkeypatch: pytest.MonkeyPatch):
    client = type("C", (), {"get_nft": AsyncMock(return_value={})})()
    monkeypatch.setattr(
        "app.services.universal_nft_resolver.resolve_target_for_full_market",
        AsyncMock(return_value=(_target(), None)),
    )
    monkeypatch.setattr(
        "app.services.universal_nft_resolver.learn_from_successful_nft_check",
        AsyncMock(return_value=None),
    )
    out, err = await resolve_universal_nft("EQ" + "a" * 46, object(), _settings(), client, learn=True)
    assert err is None and out is not None
    assert out.nft_address.startswith("EQ")


@pytest.mark.asyncio
async def test_address_404_friendly_no_crash(monkeypatch: pytest.MonkeyPatch):
    from app.sources.http import MarketSourceUnavailable

    client = type("C", (), {"get_nft": AsyncMock(return_value=None)})()
    monkeypatch.setattr(
        "app.services.universal_nft_resolver.resolve_target_for_full_market",
        AsyncMock(side_effect=MarketSourceUnavailable("http error 404")),
    )
    out, err = await resolve_universal_nft("EQ" + "b" * 46, object(), _settings(), client)
    assert out is None and err
    assert "Не нашёл NFT через TonAPI" in err


@pytest.mark.asyncio
async def test_successful_resolve_learns_alias_and_item(monkeypatch: pytest.MonkeyPatch):
    client = type("C", (), {"get_nft": AsyncMock(return_value={})})()
    learned = {"n": 0}

    async def _learn(*_a, **_k):
        learned["n"] += 1

    monkeypatch.setattr(
        "app.services.universal_nft_resolver.resolve_target_for_full_market",
        AsyncMock(return_value=(_target(), None)),
    )
    monkeypatch.setattr("app.services.universal_nft_resolver.learn_from_successful_nft_check", _learn)
    out, err = await resolve_universal_nft("Pretty Posy #28864", object(), _settings(), client, learn=True)
    assert err is None and out is not None
    assert learned["n"] == 1


@pytest.mark.asyncio
async def test_name_number_local_item_success(monkeypatch: pytest.MonkeyPatch):
    client = type("C", (), {"get_nft": AsyncMock(return_value={})})()
    monkeypatch.setattr(
        "app.services.universal_nft_resolver.resolve_target_for_full_market",
        AsyncMock(return_value=(_target(), None)),
    )
    monkeypatch.setattr(
        "app.services.universal_nft_resolver.learn_from_successful_nft_check",
        AsyncMock(return_value=None),
    )
    out, err = await resolve_universal_nft("Pretty Posy #28864", object(), _settings(), client)
    assert err is None and out is not None
    assert out.item_number == 28864


@pytest.mark.asyncio
async def test_name_number_local_alias_short_scan_success(monkeypatch: pytest.MonkeyPatch):
    client = type("C", (), {"get_nft": AsyncMock(return_value={})})()
    monkeypatch.setattr(
        "app.services.universal_nft_resolver.resolve_target_for_full_market",
        AsyncMock(return_value=(_target(), None)),
    )
    monkeypatch.setattr(
        "app.services.universal_nft_resolver.learn_from_successful_nft_check",
        AsyncMock(return_value=None),
    )
    out, err = await resolve_universal_nft("Pretty Posy #28864", object(), _settings(), client)
    assert err is None and out is not None
    assert out.collection_name == "Pretty Posy"


@pytest.mark.asyncio
async def test_paid_unknown_name_creates_index_job(monkeypatch: pytest.MonkeyPatch):
    client = type("C", (), {"get_nft": AsyncMock(return_value=None)})()
    monkeypatch.setattr(
        "app.services.universal_nft_resolver.resolve_target_for_full_market",
        AsyncMock(return_value=(None, "not found")),
    )
    monkeypatch.setattr(
        "app.services.universal_nft_resolver._resolve_via_toncenter",
        AsyncMock(return_value=(None, None, "not_found")),
    )
    enq = {"n": 0}

    async def _enq(*_a, **_k):
        enq["n"] += 1

    monkeypatch.setattr("app.services.universal_nft_resolver.enqueue_live_discovery", _enq)
    out, err = await resolve_universal_nft(
        "Pretty Posy #28864",
        type("U", (), {"plan": "pro"})(),
        _settings(),
        client,
        learn=False,
    )
    assert out is None and err
    assert enq["n"] == 1
    assert "расширенный поиск" in err.lower()


@pytest.mark.asyncio
async def test_live_discovery_429_returns_deferred(monkeypatch: pytest.MonkeyPatch):
    client = type("C", (), {"get_nft": AsyncMock(return_value=None)})()
    monkeypatch.setattr(
        "app.services.universal_nft_resolver.resolve_target_for_full_market",
        AsyncMock(return_value=(None, "not found")),
    )
    monkeypatch.setattr(
        "app.services.universal_nft_resolver._resolve_via_toncenter",
        AsyncMock(return_value=(None, "discovery_deferred", "discovery_deferred")),
    )
    out, err = await resolve_universal_nft(
        "Pretty Posy #28864",
        type("U", (), {"plan": "free"})(),
        _settings(),
        client,
        learn=False,
    )
    assert out is None and err
    assert "лимит запросов tonapi" in err.lower()

