"""Extra coverage: Getgems startapp parsing edge cases and Toncenter /nft/items JSON shapes."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.config import Settings
from app.services.gift_intake import GiftInputType, parse_gift_input
from app.services.toncenter_client import ToncenterClient
from app.services.universal_nft_resolver import getgems_startapp_failure_user_message, resolve_universal_nft


def test_getgems_failure_message_explains_empty_toncenter_index():
    msg = getgems_startapp_failure_user_message(
        {"toncenter_item_lookup": "not_found", "toncenter_http_ok": True, "toncenter_items_count": 0}
    )
    assert "пусто" in msg.lower() or "индекс" in msg.lower()
    assert "404" in msg


def test_getgems_failure_message_invalid_shape():
    msg = getgems_startapp_failure_user_message({"toncenter_item_lookup": "invalid_shape"})
    assert "формат" in msg.lower() or "адрес" in msg.lower()


def test_toncenter_extract_items_nft_items_shape():
    rows = ToncenterClient._extract_items({"nft_items": [{"address": "EQ_A", "index": 1}]})
    assert len(rows) == 1 and rows[0]["address"] == "EQ_A"


def test_toncenter_extract_items_items_shape():
    rows = ToncenterClient._extract_items({"items": [{"address": "EQ_B"}]})
    assert len(rows) == 1 and rows[0]["address"] == "EQ_B"


def test_toncenter_extract_items_item_shape():
    rows = ToncenterClient._extract_items({"item": {"address": "EQ_C", "collection_address": "EQ_COLL"}})
    assert len(rows) == 1 and rows[0]["address"] == "EQ_C"


def test_getgems_startapp_does_not_use_collection_as_nft():
    coll = "EQD__________________________________________0vo"
    # Same address twice in path — invalid, must not set nft_address to collection only.
    enc = __import__("base64").urlsafe_b64encode(f"/collection/{coll}/{coll}".encode()).decode().rstrip("=")
    url = f"https://t.me/GetgemsNftBot/gems?startapp={enc}"
    gi = parse_gift_input(url)
    assert gi.nft_address is None
    assert gi.collection_address == coll
    assert gi.source_hint == "getgems_startapp_invalid"


def _settings(**kw: object) -> Settings:
    base: dict = {
        "BOT_TOKEN": "x",
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "TONAPI_ENABLED": True,
        "TONAPI_API_KEY": "k",
        "FULL_MARKET_SCAN_ENABLED": True,
        "NFT_GLOBAL_INDEX_ENABLED": False,
        "TONCENTER_ENABLED": True,
        "TONCENTER_API_BASE_URL": "https://toncenter.com/api/v3",
        "TONCENTER_API_KEY": "secret",
        "NFT_GLOBAL_RESOLVER_USE_TONCENTER": True,
    }
    base.update(kw)
    return Settings(**base)


@pytest.mark.asyncio
async def test_getgems_startapp_preserves_collection_address_from_link(monkeypatch: pytest.MonkeyPatch):
    """Toncenter item without collection_address — hint from startapp must remain on ResolvedNft."""
    link_coll = "EQ_HINT_COLL______________________________________ab"
    enc = __import__("base64").urlsafe_b64encode(
        f"/collection/{link_coll}/EQ_NFT_ITEM___________________________________xy".encode()
    ).decode().rstrip("=")
    url = f"https://t.me/GetgemsNftBot/gems?startapp={enc}"

    async def _get_nft(_a: str):
        return None

    client = type("TC", (), {"get_nft": AsyncMock(side_effect=_get_nft), "configured": True})()

    class _FakeToncenter:
        def __init__(self, _s):
            pass

        def configured(self):
            return True

        async def fetch_nft_item_by_address(self, _a, **_kw):
            return {
                "address": "EQ_NFT_ITEM___________________________________xy",
                "metadata": {"name": "Gift #1"},
                "index": 1,
            }

    monkeypatch.setattr("app.services.universal_nft_resolver.ToncenterClient", _FakeToncenter)
    out, err = await resolve_universal_nft(url, type("U", (), {"plan": "free"})(), _settings(), client, learn=False)
    assert err is None and out is not None
    assert out.collection_address == link_coll


@pytest.mark.asyncio
async def test_toncenter_success_tonapi_404_still_success(monkeypatch: pytest.MonkeyPatch):
    """TonAPI returns None twice; Toncenter supplies NFT — resolve ok, source toncenter_item."""
    enc = __import__("base64").urlsafe_b64encode(
        b"/collection/EQ_COLL______________________________________aa/EQ_NFT__________________________________________bb"
    ).decode().rstrip("=")
    url = f"https://t.me/GetgemsNftBot/gems?startapp={enc}"

    client = type("TC", (), {"get_nft": AsyncMock(return_value=None), "configured": True})()

    class _FakeToncenter:
        def __init__(self, _s):
            pass

        def configured(self):
            return True

        async def fetch_nft_item_by_address(self, _a, **_kw):
            return {
                "address": "EQ_NFT__________________________________________bb",
                "collection_address": "EQ_COLL______________________________________aa",
                "metadata": {"name": "NFT bb"},
                "index": 0,
            }

    monkeypatch.setattr("app.services.universal_nft_resolver.ToncenterClient", _FakeToncenter)
    out, err = await resolve_universal_nft(url, type("U", (), {"plan": "free"})(), _settings(), client, learn=False)
    assert err is None and out is not None
    assert out.source == "toncenter_item"
    assert out.nft_raw is None
    assert client.get_nft.await_count >= 1
