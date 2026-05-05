"""Dynamic TonAPI-first NFT /check resolution: optional registry, no user-facing registry paths."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import Settings
from app.services import gift_analysis_flow
from app.services.nft_collection_resolve import (
    CollectionCandidate,
    CollectionResolutionResult,
    resolve_collection_address_by_name,
)
from app.services.real_market_collection_scan import (
    TargetNftInfo,
    resolve_target_for_full_market,
    target_from_nft_payload,
)


def _settings(tmp_path, **kw: object) -> Settings:
    reg = tmp_path / "collections.json"
    reg.write_text("{}", encoding="utf-8")
    base: dict = {
        "BOT_TOKEN": "x",
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "TONAPI_ENABLED": True,
        "TONAPI_API_KEY": "k",
        "NFT_GLOBAL_INDEX_ENABLED": False,
        "COLLECTION_REGISTRY_PATH": str(reg),
        "FULL_MARKET_SCAN_ENABLED": True,
    }
    base.update(kw)
    return Settings(**base)


def _user():
    return MagicMock()


def _banned_in_user_text(s: str) -> list[str]:
    banned = (
        "collections.json",
        "collections.example",
        "mock",
        "test",
        "заглушка",
        "legacy",
        "internal config",
        "config",
    )
    low = s.lower()
    return [b for b in banned if b in low]


_VALID_EQ = "EQDaT9n58yjHyjPNQG_ow999VINkBC81R8BRNd8URZX3DXwM"
_VALID_EQ2 = "EQDbT9n58yjHyjPNQG_ow999VINkBC81R8BRNd8URZX3DXwN"


@pytest.mark.asyncio
async def test_nft_address_does_not_require_collections_json(monkeypatch: pytest.MonkeyPatch, tmp_path):
    st = _settings(tmp_path)
    client = MagicMock()
    client.configured = True
    client.get_nft = AsyncMock(
        return_value={
            "address": _VALID_EQ,
            "metadata": {"name": "Demo #5"},
            "collection": {
                "address": _VALID_EQ2,
                "name": "Demo Coll",
            },
        }
    )
    client.fetch_nft_collections_page = AsyncMock()

    tgt, err = await resolve_target_for_full_market(_VALID_EQ, _user(), st, client)
    assert err is None
    assert tgt is not None
    assert tgt.collection_address == _VALID_EQ2
    client.fetch_nft_collections_page.assert_not_called()


@pytest.mark.asyncio
async def test_nft_url_with_address_does_not_require_collections_json(monkeypatch: pytest.MonkeyPatch, tmp_path):
    st = _settings(tmp_path)
    client = MagicMock()
    client.configured = True
    client.get_nft = AsyncMock(
        return_value={
            "address": _VALID_EQ,
            "metadata": {"name": "X #1"},
            "collection": {"address": _VALID_EQ2, "name": "X"},
        }
    )
    client.fetch_nft_collections_page = AsyncMock()

    url = f"https://getgems.io/nft/{_VALID_EQ}"
    monkeypatch.setattr(
        "app.services.gift_resolver.resolve_gift_identity",
        AsyncMock(
            return_value=(
                MagicMock(),
                MagicMock(
                    nft_address=_VALID_EQ,
                    collection="Unknown",
                    number=None,
                ),
            )
        ),
    )

    tgt, err = await resolve_target_for_full_market(url, _user(), st, client)
    assert err is None and tgt is not None
    client.fetch_nft_collections_page.assert_not_called()


@pytest.mark.asyncio
async def test_getgems_startapp_uses_second_address_for_tonapi_get_nft(monkeypatch: pytest.MonkeyPatch, tmp_path):
    st = _settings(tmp_path)
    client = MagicMock()
    client.configured = True
    coll = "EQA0EzRYX5wm_q46_NX8b7EYhtOkXfXgsr06ETbov1a7StZl"
    nft = "EQf_tg_gift____________________8qtF4fAABwwL-e"

    async def _get_nft(addr: str):
        assert addr == nft
        assert addr != coll
        return {
            "address": nft,
            "metadata": {"name": "Pretty Posy #28864"},
            "collection": {"address": coll, "name": "Pretty Posy"},
        }

    client.get_nft = AsyncMock(side_effect=_get_nft)
    client.fetch_nft_collections_page = AsyncMock()
    url = (
        "https://t.me/GetgemsNftBot/gems?startapp="
        "L2NvbGxlY3Rpb24vRVFBMEV6UllYNXdtX3E0Nl9OWDhiN0VZaHRPa1hmWGdzcjA2RVRib3YxYTdTdFpsL0VRZl90"
        "Z19naWZ0X19fX19fX19fX19fX19fX19fX184cXRGNGZBQUJ3d0wtZQ"
    )
    tgt, err = await resolve_target_for_full_market(url, _user(), st, client)
    assert err is None and tgt is not None
    assert tgt.address == nft
    assert tgt.collection_address == coll


@pytest.mark.asyncio
async def test_collection_only_link_no_get_nft_collection(monkeypatch: pytest.MonkeyPatch, tmp_path):
    st = _settings(tmp_path)
    client = MagicMock()
    client.configured = True
    client.get_nft = AsyncMock(return_value=None)
    url = (
        "https://t.me/GetgemsNftBot/gems?startapp="
        "L2NvbGxlY3Rpb24vRVFBMEV6UllYNXdtX3E0Nl9OWDhiN0VZaHRPa1hmWGdzcjA2RVRib3YxYTdTdFps"
    )
    tgt, err = await resolve_target_for_full_market(url, _user(), st, client)
    assert tgt is None and err
    assert "коллекцию" in err.lower()
    client.get_nft.assert_not_called()


@pytest.mark.asyncio
async def test_collection_number_uses_json_only_as_optional_alias(monkeypatch: pytest.MonkeyPatch, tmp_path):
    import app.services.nft_collection_resolve as nft_cr

    nft_cr._COLLECTION_ADDR_CACHE.clear()

    reg = tmp_path / "collections.json"
    reg.write_text(
        '{"Ice Cream": {"aliases": ["ice"], "tonapi": {"collection_address": "EQicejson"}}}',
        encoding="utf-8",
    )
    st = Settings(
        BOT_TOKEN="x",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        TONAPI_ENABLED=True,
        TONAPI_API_KEY="k",
        NFT_GLOBAL_INDEX_ENABLED=False,
        COLLECTION_REGISTRY_PATH=str(reg),
        FULL_MARKET_SCAN_ENABLED=True,
    )
    client = MagicMock()
    client.configured = True
    client.get_nft = AsyncMock(return_value=None)
    client.fetch_nft_collections_page = AsyncMock()

    async def _found(*a, **k):
        return TargetNftInfo(
            name="Ice Cream #3",
            number=3,
            address="EQitem",
            collection_name="Ice Cream",
            collection_address="EQicejson",
            model="M",
            backdrop="B",
            symbol="S",
        )

    monkeypatch.setattr(
        "app.services.gift_resolver.resolve_gift_identity",
        AsyncMock(
            return_value=(
                MagicMock(),
                MagicMock(nft_address=None, collection="Ice Cream", number=3),
            )
        ),
    )
    monkeypatch.setattr(
        "app.services.real_market_collection_scan.resolve_target_nft_from_collection_number",
        _found,
    )

    tgt, err = await resolve_target_for_full_market("Ice Cream #3", _user(), st, client)
    assert err is None and tgt is not None
    from app.sources.collections import load_collection_registry

    res = await resolve_collection_address_by_name(
        "Ice Cream", settings=st, client=client, registry=load_collection_registry(str(reg))
    )
    assert res.source == "collections_json"
    client.fetch_nft_collections_page.assert_not_called()


@pytest.mark.asyncio
async def test_collection_number_dynamic_resolver_success(monkeypatch: pytest.MonkeyPatch, tmp_path):
    st = _settings(tmp_path)
    client = MagicMock()
    client.configured = True
    client.get_nft = AsyncMock(return_value=None)
    client.fetch_nft_collections_page = AsyncMock(
        return_value=(
            [
                {
                    "address": "EQwhipdyn",
                    "metadata": {"name": "Whip Cupcake"},
                }
            ],
            200,
            {},
        )
    )

    monkeypatch.setattr(
        "app.services.gift_resolver.resolve_gift_identity",
        AsyncMock(
            return_value=(
                MagicMock(),
                MagicMock(nft_address=None, collection="Whip Cupcake", number=57234),
            )
        ),
    )
    monkeypatch.setattr(
        "app.services.real_market_collection_scan.resolve_target_nft_from_collection_number",
        AsyncMock(
            return_value=TargetNftInfo(
                name="Whip Cupcake #57234",
                number=57234,
                address="EQnftw",
                collection_name="Whip Cupcake",
                collection_address="EQwhipdyn",
                model=None,
                backdrop=None,
                symbol=None,
            )
        ),
    )

    tgt, err = await resolve_target_for_full_market("Whip Cupcake #57234", _user(), st, client)
    assert err is None and tgt is not None
    assert tgt.collection_address == "EQwhipdyn"


@pytest.mark.asyncio
async def test_collection_number_dynamic_resolver_not_found_user_friendly(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    st = _settings(tmp_path)
    client = MagicMock()
    client.configured = True
    client.get_nft = AsyncMock(return_value=None)
    client.fetch_nft_collections_page = AsyncMock(return_value=([], 200, {}))

    monkeypatch.setattr(
        "app.services.real_market_collection_scan.resolve_collection_address_by_name",
        AsyncMock(
            return_value=CollectionResolutionResult(
                None, "Unknown Collection", "none", "low", []
            )
        ),
    )
    monkeypatch.setattr(
        "app.services.gift_resolver.resolve_gift_identity",
        AsyncMock(
            return_value=(
                MagicMock(),
                MagicMock(nft_address=None, collection="Unknown Collection", number=123),
            )
        ),
    )

    tgt, err = await resolve_target_for_full_market("Unknown Collection #123", _user(), st, client)
    assert tgt is None and err
    assert "Unknown Collection" in err
    assert not _banned_in_user_text(err)


@pytest.mark.asyncio
async def test_multiple_collection_candidates_ask_for_address(monkeypatch: pytest.MonkeyPatch, tmp_path):
    st = _settings(tmp_path)
    client = MagicMock()
    client.configured = True

    monkeypatch.setattr(
        "app.services.real_market_collection_scan.resolve_collection_address_by_name",
        AsyncMock(
            return_value=CollectionResolutionResult(
                None,
                None,
                "tonapi",
                "low",
                [
                    CollectionCandidate("EQa", "Dup"),
                    CollectionCandidate("EQb", "Dup"),
                ],
            )
        ),
    )
    monkeypatch.setattr(
        "app.services.gift_resolver.resolve_gift_identity",
        AsyncMock(
            return_value=(
                MagicMock(),
                MagicMock(nft_address=None, collection="Dup", number=1),
            )
        ),
    )

    tgt, err = await resolve_target_for_full_market("Dup #1", _user(), st, client)
    assert tgt is None and err and err.startswith("⚠️")
    assert not _banned_in_user_text(err)


def test_no_collections_json_in_user_messages():
    msgs = [
        gift_analysis_flow.MSG_NFT_CHECK_NO_COLLECTION_ADDR,
        gift_analysis_flow.MSG_NFT_CHECK_TONAPI_UNAVAILABLE,
        gift_analysis_flow.MSG_NFT_CHECK_NO_TONAPI_KEY,
    ]
    for m in msgs:
        assert not _banned_in_user_text(m)


@pytest.mark.asyncio
async def test_tonapi_collection_address_has_priority_over_json(monkeypatch: pytest.MonkeyPatch, tmp_path):
    reg = tmp_path / "collections.json"
    reg.write_text(
        '{"Ice Cream": {"tonapi": {"collection_address": "EQfromjsononly"}}}',
        encoding="utf-8",
    )
    st = Settings(
        BOT_TOKEN="x",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        TONAPI_ENABLED=True,
        TONAPI_API_KEY="k",
        NFT_GLOBAL_INDEX_ENABLED=False,
        COLLECTION_REGISTRY_PATH=str(reg),
        FULL_MARKET_SCAN_ENABLED=True,
    )
    client = MagicMock()
    client.configured = True
    client.get_nft = AsyncMock(
        return_value={
            "address": _VALID_EQ,
            "metadata": {"name": "Ice Cream #1"},
            "collection": {"address": _VALID_EQ2, "name": "Ice Cream"},
        }
    )

    tgt, err = await resolve_target_for_full_market(_VALID_EQ, _user(), st, client)
    assert err is None and tgt
    assert tgt.collection_address == _VALID_EQ2


@pytest.mark.asyncio
async def test_nft_found_but_no_collection_address(tmp_path):
    st = _settings(tmp_path)
    client = MagicMock()
    client.configured = True
    client.get_nft = AsyncMock(
        return_value={
            "address": _VALID_EQ,
            "metadata": {"name": "Lonely #1"},
        }
    )

    tgt, err = await resolve_target_for_full_market(_VALID_EQ, _user(), st, client)
    assert tgt is None and err and "TonAPI" in err
    assert not _banned_in_user_text(err)


@pytest.mark.asyncio
async def test_existing_check_flow_not_broken(monkeypatch: pytest.MonkeyPatch, tmp_path):
    st = _settings(tmp_path)
    client = MagicMock()
    client.configured = True
    client.get_nft = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.services.gift_resolver.resolve_gift_identity",
        AsyncMock(
            return_value=(
                MagicMock(),
                MagicMock(nft_address=None, collection="Ice Cream", number=217467),
            )
        ),
    )
    monkeypatch.setattr(
        "app.services.real_market_collection_scan.resolve_collection_address_by_name",
        AsyncMock(
            return_value=CollectionResolutionResult("EQc", "Ice Cream", "collections_json", "high", [])
        ),
    )
    monkeypatch.setattr(
        "app.services.real_market_collection_scan.resolve_target_nft_from_collection_number",
        AsyncMock(
            return_value=TargetNftInfo(
                name="Ice Cream #217467",
                number=217467,
                address="",
                collection_name="Ice Cream",
                collection_address="EQc",
                model="M",
                backdrop="B",
                symbol="S",
            )
        ),
    )
    monkeypatch.setattr(
        "app.services.real_market_collection_scan.get_cached_or_scan_collection",
        AsyncMock(
            return_value=(
                [],
                0,
                False,
                None,
                None,
            )
        ),
    )

    from app.services.real_market_collection_scan import run_full_market_analysis_flow

    rep, err = await run_full_market_analysis_flow("Ice Cream #217467", _user(), st, client)
    assert err is None and rep is not None
    assert rep.target.collection_address == "EQc"


def test_target_from_nft_payload_reads_top_level_collection_address():
    eq_a = _VALID_EQ
    eq_top = _VALID_EQ2
    nft = {
        "address": eq_a,
        "metadata": {"name": "A #2"},
        "collection_address": eq_top,
    }
    t = target_from_nft_payload(nft)
    assert t is not None and t.collection_address == eq_top

    nft2 = {
        "address": eq_a,
        "metadata": {"name": "A #2"},
        "collection": {"address": eq_top, "name": "Real"},
    }
    t2 = target_from_nft_payload(nft2)
    assert t2 and t2.collection_address == eq_top
