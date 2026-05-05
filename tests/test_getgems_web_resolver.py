"""Getgems __NEXT_DATA__ web resolver and Getgems startapp integration tests."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot.handlers import passive_gift
from app.config import Settings
from app.services.getgems_web_next_data import (
    extract_nft_image_url_from_gql_nft_item,
    parse_getgems_next_data_bundle,
    resolve_getgems_startapp_via_web,
    ton_listing_price_from_sale_fix,
    traits_dict_from_nft_item_attributes,
)
from app.services.real_market_collection_scan import TargetNftInfo, run_full_market_analysis_flow
from app.services.universal_nft_resolver import (
    ResolvedNft,
    getgems_startapp_failure_user_message,
    resolve_universal_nft,
)


def _next_data_html(obj: dict) -> str:
    blob = json.dumps(obj, ensure_ascii=False)
    return f'<!doctype html><html><body><script id="__NEXT_DATA__" type="application/json">{blob}</script></body></html>'


def _sample_gql_cache(coll: str, raw: str) -> dict:
    return {
        "props": {
            "pageProps": {
                "gqlCache": {
                    f"NftItem:{raw}": {
                        "__typename": "NftItem",
                        "address": raw,
                        "name": "Pool Float #162345",
                        "attributes": [
                            {"traitType": "Model", "value": "Toucan"},
                            {"traitType": "Backdrop", "value": "Aquamarine"},
                            {"traitType": "Symbol", "value": "Origami"},
                        ],
                        "content": {
                            "image": {
                                "sized": "https://img.example/preview.png",
                            },
                        },
                    },
                    f"NftCollection:{coll}": {
                        "__typename": "NftCollection",
                        "address": coll,
                        "name": "Pool Floats",
                    },
                    f"NftSaleFixPrice:{raw}": {
                        "__typename": "NftSaleFixPrice",
                        "address": raw,
                        "fullPrice": "4290000000",
                        "currency": "TON",
                    },
                }
            }
        }
    }


@pytest.mark.asyncio
async def test_getgems_startapp_web_next_data_resolves_item(monkeypatch: pytest.MonkeyPatch):
    coll = "EQD1YFp12AGEgX6C3uiWh751EcRxPZo6GtBmHziY29jcbQzS"
    raw = "EQf_tg_gift_______________________8SLj_JAAJ6KYUn"
    html = _next_data_html(_sample_gql_cache(coll, raw))

    async def _fetch(_url: str, *, timeout: float):
        return 200, html

    monkeypatch.setattr(
        "app.services.getgems_web_next_data.fetch_getgems_html_status_body",
        AsyncMock(side_effect=_fetch),
    )
    st = Settings.model_construct(bot_token="x", database_url="sqlite:///./t.db")
    payload, trace = await resolve_getgems_startapp_via_web(coll, raw, st)
    assert payload is not None
    assert payload["nft_name"] == "Pool Float #162345"
    assert trace.get("getgems_item_found") is True
    assert trace.get("getgems_web_status") == 200


def test_getgems_web_next_data_extracts_collection_name():
    coll = "EQCOLL"
    raw = "EQRAW"
    nd = _sample_gql_cache(coll, raw)
    bundle, flags = parse_getgems_next_data_bundle(nd, collection_address=coll, raw_ref=raw)
    assert bundle
    coll_obj = bundle["nft_collection"]
    assert coll_obj["name"] == "Pool Floats"


def test_getgems_web_next_data_extracts_traits():
    coll = "EQCOLL"
    raw = "EQRAW"
    nd = _sample_gql_cache(coll, raw)
    bundle, _ = parse_getgems_next_data_bundle(nd, collection_address=coll, raw_ref=raw)
    assert bundle
    t = traits_dict_from_nft_item_attributes(bundle["nft_item"])
    assert t["Model"] == "Toucan"
    assert t["Backdrop"] == "Aquamarine"


def test_getgems_web_next_data_extracts_image():
    item = {
        "content": {
            "image": {
                "image": {"baseUrl": "https://cdn.example/nft.webp"},
            }
        }
    }
    assert extract_nft_image_url_from_gql_nft_item(item) == "https://cdn.example/nft.webp"


def test_getgems_web_next_data_extracts_ton_listing_price():
    sale = {"__typename": "NftSaleFixPrice", "fullPrice": "4290000000", "currency": "TON"}
    assert ton_listing_price_from_sale_fix(sale) == pytest.approx(4.29)


@pytest.mark.asyncio
async def test_getgems_web_success_after_tonapi_404_and_toncenter_empty(monkeypatch: pytest.MonkeyPatch):
    coll = "EQD1YFp12AGEgX6C3uiWh751EcRxPZo6GtBmHziY29jcbQzS"
    raw = "EQf_tg_gift_______________________8SLj_JAAJ6KYUn"
    html = _next_data_html(_sample_gql_cache(coll, raw))

    async def _fetch(_url: str, *, timeout: float):
        return 200, html

    monkeypatch.setattr(
        "app.services.getgems_web_next_data.fetch_getgems_html_status_body",
        AsyncMock(side_effect=_fetch),
    )

    class _Ton:
        configured = True

        async def get_nft(self, _a):
            return None

    class _Toncenter:
        def __init__(self, _s):
            pass

        def configured(self):
            return True

        async def fetch_nft_item_by_address(self, _a, **_kw):
            return None

    monkeypatch.setattr("app.services.universal_nft_resolver.ToncenterClient", _Toncenter)
    url = "https://t.me/GetgemsNftBot/gems?startapp=" + __import__("base64").b64encode(
        f"/collection/{coll}/{raw}".encode()
    ).decode()
    st = Settings.model_construct(
        bot_token="x",
        database_url="sqlite:///./t.db",
        toncenter_enabled=True,
        toncenter_api_key="k",
    )
    out, err = await resolve_universal_nft(url, MagicMock(), st, _Ton(), learn=False)
    assert err is None and out is not None
    assert out.source == "getgems_web"
    assert out.nft_address == raw
    assert out.collection_address == coll


@pytest.mark.asyncio
async def test_getgems_web_preview_has_action_buttons(monkeypatch: pytest.MonkeyPatch):
    from aiogram.fsm.context import FSMContext

    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_a, **_k):
            return type("U", (), {"id": 1, "plan": "free"})()

    tgt = TargetNftInfo(
        name="Pool Float #162345",
        number=162345,
        address="EQREF",
        collection_name="Pool Floats",
        collection_address="EQCOLL",
        model="Toucan",
        backdrop="Aquamarine",
        symbol="Origami",
        address_kind="getgems_gift_ref",
    )
    res = ResolvedNft(
        original_payload="https://t.me/x",
        nft_address=tgt.address,
        collection_address=tgt.collection_address,
        nft_name=tgt.name,
        collection_name=tgt.collection_name,
        item_number=tgt.number,
        image_url="https://img.png",
        traits={"model": tgt.model, "backdrop": tgt.backdrop, "symbol": tgt.symbol},
        sale_price_ton=4.29,
        for_sale=True,
        source="getgems_web",
        learned=False,
        target=tgt,
        nft_raw={},
        preview_trait_lines=[("Model", "Toucan"), ("Backdrop", "Aquamarine")],
        user_source_label="Getgems / TonAPI",
        external_sale_hint=False,
    )

    monkeypatch.setattr(passive_gift, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive_gift, "UserRepository", _UR)
    monkeypatch.setattr(
        passive_gift,
        "resolve_universal_nft",
        lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(res, None))),
    )
    monkeypatch.setattr(passive_gift, "TonAPICollectionClient", lambda _s: object())
    monkeypatch.setattr(
        passive_gift,
        "extract_nft_preview_media",
        lambda *_a, **_k: type("M", (), {"url": None, "kind": "none", "mime_type": None, "source_field": None})(),
    )
    monkeypatch.setattr(passive_gift.runtime_state, "nft_action_session_put", lambda *_a, **_k: "sid1")

    class _Msg:
        def __init__(self):
            self.text = "https://t.me/GetgemsNftBot/gems?startapp=abc"
            self.from_user = type("U", (), {"id": 1, "username": "u"})()
            self.chat = type("C", (), {"id": 1})()
            self.bot = type("B", (), {"edit_message_text": AsyncMock()})()
            self.out: list[str] = []

        async def answer(self, t="", **_k):
            self.out.append(t)
            return type("R", (), {"message_id": 1})()

    m = _Msg()
    fsm = MagicMock(spec=FSMContext)
    fsm.clear = AsyncMock()
    await passive_gift.passive_gift_text(m, fsm)
    from app.bot.handlers.passive_gift import _resolved_nft_keyboard

    kb2 = _resolved_nft_keyboard("sid1")
    flat = [b.text for row in kb2.inline_keyboard for b in row]
    assert "🔎 Проверить рынок" in flat
    assert "💎 Цена листинга" in flat
    assert "✅ Добавить в список" in flat


@pytest.mark.asyncio
async def test_getgems_web_market_scan_uses_collection_address_from_startapp(monkeypatch: pytest.MonkeyPatch):
    coll = "EQCOLLSCAN"
    raw = "EQRAWSNIP"
    captured: dict[str, str] = {}

    async def _gc(_client, _settings, collection_address, on_progress=None):
        captured["collection_address"] = collection_address
        return [], 0, False, None, None

    monkeypatch.setattr(
        "app.services.real_market_collection_scan.get_cached_or_scan_collection",
        _gc,
    )

    tgt = TargetNftInfo(
        name="Pool Float #1",
        number=1,
        address=raw,
        collection_name="Pool Floats",
        collection_address=coll,
        model="A",
        backdrop="B",
        symbol="C",
        traits_normalized={"model": "A", "backdrop": "B", "symbol": "C"},
        address_kind="getgems_gift_ref",
    )
    st = Settings.model_construct(
        bot_token="x",
        database_url="sqlite:///./t.db",
        tonapi_enabled=True,
        tonapi_api_key="k",
        full_market_scan_enabled=True,
        tonapi_base_url="https://tonapi.io",
    )
    client = MagicMock()
    client.configured = True
    await run_full_market_analysis_flow(
        "unused",
        MagicMock(),
        st,
        client,
        pre_resolved_target=tgt,
    )
    assert captured.get("collection_address") == coll


@pytest.mark.asyncio
async def test_getgems_web_market_scan_uses_target_traits(monkeypatch: pytest.MonkeyPatch):
    coll = "EQC"
    tgt = TargetNftInfo(
        name="X #2",
        number=2,
        address="EQR",
        collection_name="Col",
        collection_address=coll,
        model="M1",
        backdrop="B1",
        symbol="S1",
        traits_normalized={"model": "M1", "backdrop": "B1", "symbol": "S1"},
        address_kind="getgems_gift_ref",
    )
    st = Settings.model_construct(
        bot_token="x",
        database_url="sqlite:///./t.db",
        tonapi_enabled=True,
        tonapi_api_key="k",
        full_market_scan_enabled=True,
    )
    client = MagicMock()
    client.configured = True

    async def _gc(_client, _settings, collection_address, on_progress=None):
        assert tgt.model == "M1" and tgt.backdrop == "B1" and tgt.symbol == "S1"
        return [], 0, False, None, None

    monkeypatch.setattr("app.services.real_market_collection_scan.get_cached_or_scan_collection", _gc)
    await run_full_market_analysis_flow("x", MagicMock(), st, client, pre_resolved_target=tgt)


@pytest.mark.asyncio
async def test_getgems_web_does_not_retry_tonapi_404_many_times(monkeypatch: pytest.MonkeyPatch):
    calls: list[int] = []

    async def _get_nft(_self, _addr):
        calls.append(1)
        return None

    coll = "EQD1YFp12AGEgX6C3uiWh751EcRxPZo6GtBmHziY29jcbQzS"
    raw = "EQf_tg_gift_______________________8SLj_JAAJ6KYUn"
    html = _next_data_html(_sample_gql_cache(coll, raw))

    async def _fetch(_url: str, *, timeout: float):
        return 200, html

    monkeypatch.setattr(
        "app.services.getgems_web_next_data.fetch_getgems_html_status_body",
        AsyncMock(side_effect=_fetch),
    )

    class _Toncenter:
        def __init__(self, _s):
            pass

        def configured(self):
            return False

    monkeypatch.setattr("app.services.universal_nft_resolver.ToncenterClient", _Toncenter)
    st = Settings.model_construct(bot_token="x", database_url="sqlite:///./t.db")
    client = type("TC", (), {"get_nft": _get_nft, "configured": True})()
    enc = __import__("base64").b64encode(f"/collection/{coll}/{raw}".encode()).decode()
    await resolve_universal_nft(
        f"https://t.me/GetgemsNftBot/gems?startapp={enc}", MagicMock(), st, client, learn=False
    )
    assert len(calls) == 1


def test_getgems_web_failure_friendly_error():
    msg = getgems_startapp_failure_user_message(
        {"getgems_web_attempted": True, "getgems_item_found": False},
    )
    assert "Не смог получить конкретный NFT" in msg
    assert "Mini App" in msg


def test_getgems_web_error_has_no_mock_legacy_collections_json_raw_ref():
    msg = getgems_startapp_failure_user_message(
        {"getgems_web_attempted": True, "getgems_item_found": False},
    )
    low = msg.lower()
    assert "mock" not in low
    assert "legacy" not in low
    assert "collections.json" not in low
    assert "raw_ref" not in low


@pytest.mark.asyncio
async def test_getgems_web_trace_contains_next_data_success(monkeypatch: pytest.MonkeyPatch):
    coll = "EQD1YFp12AGEgX6C3uiWh751EcRxPZo6GtBmHziY29jcbQzS"
    raw = "EQf_tg_gift_______________________8SLj_JAAJ6KYUn"
    html = _next_data_html(_sample_gql_cache(coll, raw))

    async def _fetch(_url: str, *, timeout: float):
        return 200, html

    monkeypatch.setattr(
        "app.services.getgems_web_next_data.fetch_getgems_html_status_body",
        AsyncMock(side_effect=_fetch),
    )

    class _Toncenter:
        def __init__(self, _s):
            pass

        def configured(self):
            return False

    monkeypatch.setattr("app.services.universal_nft_resolver.ToncenterClient", _Toncenter)

    async def _get_nft(_self, _addr):
        return None

    st = Settings.model_construct(bot_token="x", database_url="sqlite:///./t.db")
    client = type("TC", (), {"get_nft": _get_nft, "configured": True})()
    enc = __import__("base64").b64encode(f"/collection/{coll}/{raw}".encode()).decode()
    out, err = await resolve_universal_nft(
        f"https://t.me/GetgemsNftBot/gems?startapp={enc}",
        MagicMock(),
        st,
        client,
        learn=False,
    )
    assert err is None and out is not None
    tr = out.resolver_trace or {}
    assert tr.get("getgems_next_data_found") is True
    assert tr.get("final_source") == "getgems_web"
