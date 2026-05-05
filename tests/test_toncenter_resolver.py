from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import Settings


def _patch_session_local_noop_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Без реального asyncpg pool: session.execute/commit awaitable для путей с моками repo."""

    sess = MagicMock()
    sess.execute = AsyncMock(return_value=MagicMock())
    sess.commit = AsyncMock()
    sess.rollback = AsyncMock()

    class _CM:
        async def __aenter__(self) -> MagicMock:
            return sess

        async def __aexit__(self, *_a: object) -> bool:
            return False

    monkeypatch.setattr("app.services.universal_nft_resolver.SessionLocal", lambda: _CM())
from app.services.toncenter_client import ToncenterClient
from app.services.universal_nft_resolver import resolve_universal_nft


def _settings(**kw: object) -> Settings:
    base: dict = {
        "BOT_TOKEN": "x",
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "TONAPI_ENABLED": True,
        "TONAPI_API_KEY": "k",
        "FULL_MARKET_SCAN_ENABLED": True,
        "NFT_GLOBAL_INDEX_ENABLED": True,
        "TONCENTER_ENABLED": True,
        "TONCENTER_API_BASE_URL": "https://toncenter.com/api/v3",
        "TONCENTER_API_KEY": "secret_key_123",
        "NFT_GLOBAL_RESOLVER_USE_TONCENTER": True,
    }
    base.update(kw)
    return Settings(**base)


def _user(plan: str = "free"):
    return type("U", (), {"plan": plan})()


def test_toncenter_client_configured():
    c = ToncenterClient(_settings())
    assert c.configured() is True
    c2 = ToncenterClient(_settings(TONCENTER_API_KEY=""))
    assert c2.configured() is False


@pytest.mark.asyncio
async def test_name_number_local_alias_then_toncenter_item(monkeypatch: pytest.MonkeyPatch):
    _patch_session_local_noop_db(monkeypatch)
    client = type("TC", (), {"get_nft": AsyncMock(return_value=None)})()
    monkeypatch.setattr(
        "app.services.universal_nft_resolver.resolve_target_for_full_market",
        AsyncMock(return_value=(None, "not found")),
    )

    class _FakeToncenter:
        def __init__(self, _s):
            pass

        def configured(self):
            return True

        async def fetch_nft_item_by_address(self, _a, **_kw):
            return None

        async def fetch_nft_item_by_collection_and_index(self, c, i):
            assert c == "EQ_COLL_X"
            assert i == 12
            return {"address": "EQ_ITEM_12", "collection_address": c, "index": 12, "name": "X #12"}

        async def fetch_nft_collections_page(self, *, limit, offset):
            return True, [], None, {}

    async def _aliases(_session, _norm):
        return [type("A", (), {"collection_address": "EQ_COLL_X"})()]

    async def _crows(_session, _norm):
        return []

    monkeypatch.setattr("app.services.universal_nft_resolver.ToncenterClient", _FakeToncenter)
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.find_aliases_by_normalized", _aliases)
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.find_collection_by_name_normalized", _crows)
    monkeypatch.setattr(
        "app.services.universal_nft_resolver.learn_from_successful_nft_check",
        AsyncMock(return_value=None),
    )
    out, err = await resolve_universal_nft("Pretty Posy #12", _user(), _settings(), client, learn=False)
    assert err is None and out is not None
    assert out.source == "local_alias_toncenter"


@pytest.mark.asyncio
async def test_name_number_no_alias_live_discovery_then_toncenter_item(monkeypatch: pytest.MonkeyPatch):
    _patch_session_local_noop_db(monkeypatch)
    client = type("TC", (), {"get_nft": AsyncMock(return_value=None)})()
    monkeypatch.setattr(
        "app.services.universal_nft_resolver.resolve_target_for_full_market",
        AsyncMock(return_value=(None, "not found")),
    )

    class _FakeToncenter:
        def __init__(self, _s):
            pass

        def configured(self):
            return True

        async def fetch_nft_item_by_address(self, _a, **_kw):
            return None

        async def fetch_nft_item_by_collection_and_index(self, c, i):
            return {"address": "EQ_ITEM_99", "collection_address": c, "index": i, "name": "Pretty Posy #99"}

        async def fetch_nft_collections_page(self, *, limit, offset):
            return True, [{"address": "EQC1", "name": "Pretty Posy"}], None, {}

    monkeypatch.setattr("app.services.universal_nft_resolver.ToncenterClient", _FakeToncenter)
    monkeypatch.setattr(
        "app.services.universal_nft_resolver.repo.find_aliases_by_normalized",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.universal_nft_resolver.repo.find_collection_by_name_normalized",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.upsert_alias", AsyncMock(return_value=None))
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.upsert_collection", AsyncMock(return_value=None))
    out, err = await resolve_universal_nft(
        "Pretty Posy #99", _user("pro"), _settings(), client, learn=False, live_discovery=True, max_pages=3
    )
    assert err is None and out is not None
    assert out.source == "live_discovery_toncenter"


@pytest.mark.asyncio
async def test_tonapi_404_then_toncenter_address_fallback(monkeypatch: pytest.MonkeyPatch):
    from app.sources.http import MarketSourceUnavailable

    client = type("TC", (), {"get_nft": AsyncMock(return_value=None)})()
    monkeypatch.setattr(
        "app.services.universal_nft_resolver.resolve_target_for_full_market",
        AsyncMock(side_effect=MarketSourceUnavailable("http error 404")),
    )

    class _FakeToncenter:
        def __init__(self, _s):
            pass

        def configured(self):
            return True

        async def fetch_nft_item_by_address(self, _a, **_kw):
            return {"address": "EQ_ITEM_A", "collection_address": "EQ_COLL_A", "index": 1, "name": "A #1"}

        async def fetch_nft_item_by_collection_and_index(self, c, i):
            return None

        async def fetch_nft_collections_page(self, *, limit, offset):
            return True, [], None, {}

    monkeypatch.setattr("app.services.universal_nft_resolver.ToncenterClient", _FakeToncenter)
    out, err = await resolve_universal_nft("EQ" + "a" * 46, _user(), _settings(), client, learn=False)
    assert err is None and out is not None
    assert out.source in {"toncenter_item", "tonapi_short_scan"}


@pytest.mark.asyncio
async def test_getgems_startapp_tonapi_404_then_toncenter_success(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    async def _get_nft(addr: str):
        calls.append(addr)
        return None

    client = type("TC", (), {"get_nft": AsyncMock(side_effect=_get_nft), "configured": True})()

    class _FakeToncenter:
        def __init__(self, _s):
            pass

        def configured(self):
            return True

        async def fetch_nft_item_by_address(self, _a, **_kw):
            return {"address": "EQ_ITEM_STARTAPP", "collection_address": "EQ_COLL_STARTAPP", "index": 7}

        async def fetch_nft_item_by_collection_and_index(self, c, i):
            return None

        async def fetch_nft_collections_page(self, *, limit, offset):
            return True, [], None, {}

    monkeypatch.setattr("app.services.universal_nft_resolver.ToncenterClient", _FakeToncenter)
    startapp = (
        "https://t.me/GetgemsNftBot/gems?startapp="
        "L2NvbGxlY3Rpb24vRVFBMEV6UllYNXdtX3E0Nl9OWDhiN0VZaHRPa1hmWGdzcjA2RVRib3YxYTdTdFpsL0VRZl90"
        "Z19naWZ0X19fX19fX19fX19fX19fX19fX184cXRGNGZBQUJ3d0wtZQ"
    )
    out, err = await resolve_universal_nft(startapp, _user(), _settings(), client, learn=False)
    assert err is None and out is not None
    assert out.nft_address == "EQ_ITEM_STARTAPP"
    assert out.source == "toncenter_item"
    assert len(calls) <= 2
    tr = out.resolver_trace or {}
    assert tr.get("tonapi_retries") == 0
    assert tr.get("tonapi_get_nft_status") == 404
    assert tr.get("toncenter_item_lookup") == "ok"


@pytest.mark.asyncio
async def test_multiple_low_confidence_candidates_not_auto_selected(monkeypatch: pytest.MonkeyPatch):
    client = type("TC", (), {"get_nft": AsyncMock(return_value=None)})()
    monkeypatch.setattr(
        "app.services.universal_nft_resolver.resolve_target_for_full_market",
        AsyncMock(return_value=(None, "not found")),
    )

    class _FakeToncenter:
        def __init__(self, _s):
            pass

        def configured(self):
            return True

        async def fetch_nft_item_by_address(self, _a, **_kw):
            return None

        async def fetch_nft_item_by_collection_and_index(self, c, i):
            return None

        async def fetch_nft_collections_page(self, *, limit, offset):
            return True, [{"address": "EQ1", "name": "Pretty Posy X"}, {"address": "EQ2", "name": "Pretty Posy Y"}], None, {}

    monkeypatch.setattr("app.services.universal_nft_resolver.ToncenterClient", _FakeToncenter)
    monkeypatch.setattr(
        "app.services.universal_nft_resolver.repo.find_aliases_by_normalized",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.universal_nft_resolver.repo.find_collection_by_name_normalized",
        AsyncMock(return_value=[]),
    )
    out, err = await resolve_universal_nft("Pretty Posy #11", _user(), _settings(), client, learn=False)
    assert out is None and err


@pytest.mark.asyncio
async def test_collection_name_exact_match_toncenter(monkeypatch: pytest.MonkeyPatch):
    client = type("TC", (), {"get_nft": AsyncMock(return_value=None)})()
    monkeypatch.setattr("app.services.universal_nft_resolver.resolve_target_for_full_market", AsyncMock(return_value=(None, "x")))

    class _FakeToncenter:
        def __init__(self, _s): ...
        def configured(self): return True
        async def fetch_nft_item_by_address(self, _a, **_kw): return None
        async def fetch_nft_item_by_collection_and_index(self, c, i): return {"address": "EQI1", "collection_address": c, "index": i}
        async def fetch_nft_collections_page(self, *, limit, offset):
            return True, [{"address": "EQC1", "name": "Pretty Posy"}], None, {}

    monkeypatch.setattr("app.services.universal_nft_resolver.ToncenterClient", _FakeToncenter)
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.find_aliases_by_normalized", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.find_collection_by_name_normalized", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.upsert_alias", AsyncMock(return_value=None))
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.upsert_collection", AsyncMock(return_value=None))
    out, err = await resolve_universal_nft("Pretty Posy #12", _user("pro"), _settings(), client, learn=False)
    assert err is None and out is not None
    assert out.source == "live_discovery_toncenter"


@pytest.mark.asyncio
async def test_collection_name_fuzzy_match_toncenter(monkeypatch: pytest.MonkeyPatch):
    client = type("TC", (), {"get_nft": AsyncMock(return_value=None)})()
    monkeypatch.setattr("app.services.universal_nft_resolver.resolve_target_for_full_market", AsyncMock(return_value=(None, "x")))

    class _FakeToncenter:
        def __init__(self, _s): ...
        def configured(self): return True
        async def fetch_nft_item_by_address(self, _a, **_kw): return None
        async def fetch_nft_item_by_collection_and_index(self, c, i): return {"address": "EQI2", "collection_address": c, "index": i}
        async def fetch_nft_collections_page(self, *, limit, offset):
            return True, [{"address": "EQC2", "name": "Pretty Posy NFT Collection"}], None, {}

    monkeypatch.setattr("app.services.universal_nft_resolver.ToncenterClient", _FakeToncenter)
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.find_aliases_by_normalized", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.find_collection_by_name_normalized", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.upsert_alias", AsyncMock(return_value=None))
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.upsert_collection", AsyncMock(return_value=None))
    out, err = await resolve_universal_nft("Pretty Posy #13", _user("pro"), _settings(), client, learn=False)
    assert err is None and out is not None
    assert out.source == "live_discovery_toncenter"


@pytest.mark.asyncio
async def test_collection_name_ambiguous_candidates_not_auto_selected(monkeypatch: pytest.MonkeyPatch):
    client = type("TC", (), {"get_nft": AsyncMock(return_value=None)})()
    monkeypatch.setattr("app.services.universal_nft_resolver.resolve_target_for_full_market", AsyncMock(return_value=(None, "x")))

    class _FakeToncenter:
        def __init__(self, _s): ...
        def configured(self): return True
        async def fetch_nft_item_by_address(self, _a, **_kw): return None
        async def fetch_nft_item_by_collection_and_index(self, c, i): return None
        async def fetch_nft_collections_page(self, *, limit, offset):
            return True, [
                {"address": "EQC3", "name": "Pretty Posy"},
                {"address": "EQC4", "name": "Pretty Posy Collection"},
            ], None, {}

    monkeypatch.setattr("app.services.universal_nft_resolver.ToncenterClient", _FakeToncenter)
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.find_aliases_by_normalized", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.find_collection_by_name_normalized", AsyncMock(return_value=[]))
    out, err = await resolve_universal_nft("Pretty Posy #14", _user("pro"), _settings(), client, learn=False)
    assert out is None and err
    assert "несколько похожих коллекций" in err.lower()


@pytest.mark.asyncio
async def test_resolve_name_number_uses_toncenter_candidate_then_item_index(monkeypatch: pytest.MonkeyPatch):
    client = type("TC", (), {"get_nft": AsyncMock(return_value=None)})()
    monkeypatch.setattr("app.services.universal_nft_resolver.resolve_target_for_full_market", AsyncMock(return_value=(None, "x")))

    class _FakeToncenter:
        def __init__(self, _s): ...
        def configured(self): return True
        async def fetch_nft_item_by_address(self, _a, **_kw): return None
        async def fetch_nft_item_by_collection_and_index(self, c, i):
            assert c == "EQC5" and i == 15
            return {"address": "EQI5", "collection_address": c, "index": i, "name": "Pretty Posy #15"}
        async def fetch_nft_collections_page(self, *, limit, offset):
            return True, [{"address": "EQC5", "name": "Pretty Posy"}], None, {}

    monkeypatch.setattr("app.services.universal_nft_resolver.ToncenterClient", _FakeToncenter)
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.find_aliases_by_normalized", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.find_collection_by_name_normalized", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.upsert_alias", AsyncMock(return_value=None))
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.upsert_collection", AsyncMock(return_value=None))
    out, err = await resolve_universal_nft("Pretty Posy #15", _user("pro"), _settings(), client, learn=False)
    assert err is None and out is not None
    assert out.nft_address == "EQI5"


@pytest.mark.asyncio
async def test_successful_candidate_learns_alias(monkeypatch: pytest.MonkeyPatch):
    client = type("TC", (), {"get_nft": AsyncMock(return_value=None)})()
    monkeypatch.setattr("app.services.universal_nft_resolver.resolve_target_for_full_market", AsyncMock(return_value=(None, "x")))

    class _FakeToncenter:
        def __init__(self, _s): ...
        def configured(self): return True
        async def fetch_nft_item_by_address(self, _a, **_kw): return None
        async def fetch_nft_item_by_collection_and_index(self, c, i): return {"address": "EQI6", "collection_address": c, "index": i}
        async def fetch_nft_collections_page(self, *, limit, offset):
            return True, [{"address": "EQC6", "name": "Pretty Posy"}], None, {}

    upsert_alias = AsyncMock(return_value=None)
    monkeypatch.setattr("app.services.universal_nft_resolver.ToncenterClient", _FakeToncenter)
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.find_aliases_by_normalized", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.find_collection_by_name_normalized", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.upsert_alias", upsert_alias)
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.upsert_collection", AsyncMock(return_value=None))
    out, err = await resolve_universal_nft("Pretty Posy #16", _user("pro"), _settings(), client, learn=False)
    assert err is None and out is not None
    assert upsert_alias.await_count >= 1


@pytest.mark.asyncio
async def test_no_random_low_confidence_match(monkeypatch: pytest.MonkeyPatch):
    client = type("TC", (), {"get_nft": AsyncMock(return_value=None)})()
    monkeypatch.setattr("app.services.universal_nft_resolver.resolve_target_for_full_market", AsyncMock(return_value=(None, "x")))

    class _FakeToncenter:
        def __init__(self, _s): ...
        def configured(self): return True
        async def fetch_nft_item_by_address(self, _a, **_kw): return None
        async def fetch_nft_item_by_collection_and_index(self, c, i): return None
        async def fetch_nft_collections_page(self, *, limit, offset):
            return True, [{"address": "EQC7", "name": "Posy Club"}, {"address": "EQC8", "name": "Pretty Garden"}], None, {}

    monkeypatch.setattr("app.services.universal_nft_resolver.ToncenterClient", _FakeToncenter)
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.find_aliases_by_normalized", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.services.universal_nft_resolver.repo.find_collection_by_name_normalized", AsyncMock(return_value=[]))
    out, err = await resolve_universal_nft("Pretty Posy #17", _user("pro"), _settings(), client, learn=False)
    assert out is None and err


@pytest.mark.asyncio
async def test_no_toncenter_key_does_not_break_resolver(monkeypatch: pytest.MonkeyPatch):
    client = type("TC", (), {"get_nft": AsyncMock(return_value=None)})()
    monkeypatch.setattr(
        "app.services.universal_nft_resolver.resolve_target_for_full_market",
        AsyncMock(return_value=(None, "no hit")),
    )
    out, err = await resolve_universal_nft("Pretty Posy #11", _user(), _settings(TONCENTER_API_KEY=""), client, learn=False)
    assert out is None and err


def test_toncenter_api_key_not_logged(caplog: pytest.LogCaptureFixture):
    key = "TOP_SECRET_TC_KEY"
    c = ToncenterClient(_settings(TONCENTER_API_KEY=key))
    caplog.set_level("INFO")
    assert key not in repr(c)
    assert key not in caplog.text


@pytest.mark.asyncio
async def test_pricing_still_uses_tonapi(monkeypatch: pytest.MonkeyPatch):
    from app.services.real_market_collection_scan import run_full_market_analysis_flow

    st = _settings(NFT_GLOBAL_INDEX_ENABLED=False)
    client = type("TC", (), {"configured": True})()
    monkeypatch.setattr(
        "app.services.real_market_collection_scan.resolve_target_for_full_market",
        AsyncMock(
            return_value=(
                type(
                    "T",
                    (),
                    {
                        "collection_name": "C",
                        "collection_address": "EQC",
                        "address": "EQI",
                        "number": 1,
                        "model": None,
                        "backdrop": None,
                        "symbol": None,
                    },
                )(),
                None,
            )
        ),
    )
    monkeypatch.setattr(
        "app.services.real_market_collection_scan.get_cached_or_scan_collection",
        AsyncMock(return_value=([], 0, False, None, None)),
    )
    rep, err = await run_full_market_analysis_flow("EQI", _user(), st, client, on_progress=None)
    assert rep is not None or err is not None


@pytest.mark.asyncio
async def test_resolve_cli_live_discovery_flag(monkeypatch: pytest.MonkeyPatch):
    from app.tools.resolve_nft_name import _run

    async def _resolve(*_a, **kwargs):
        assert kwargs.get("live_discovery") is True
        assert kwargs.get("max_pages") == 30
        return None, "x"

    monkeypatch.setattr("app.tools.resolve_nft_name.resolve_universal_nft", _resolve)
    monkeypatch.setattr("app.tools.resolve_nft_name.get_last_discovery_trace", lambda: {"final_reason": "x"})
    out = await _run("Pretty Posy #1", live_discovery=True, max_pages=30)
    assert out["source"] == "not_found"
    assert out["collection_discovery_trace"]["final_reason"] == "x"


@pytest.mark.asyncio
async def test_resolve_cli_not_found_has_collection_discovery_trace(monkeypatch: pytest.MonkeyPatch):
    from app.tools.resolve_nft_name import _run

    monkeypatch.setattr(
        "app.tools.resolve_nft_name.resolve_universal_nft",
        AsyncMock(return_value=(None, "not found")),
    )
    monkeypatch.setattr(
        "app.tools.resolve_nft_name.get_last_discovery_trace",
        lambda: {
            "input": "Pretty Posy #1",
            "toncenter_collections_checked": 3000,
            "final_reason": "no_collection_candidate",
        },
    )
    out = await _run("Pretty Posy #1", live_discovery=True, max_pages=30)
    assert out["ok"] is False
    assert out["collection_discovery_trace"]["final_reason"] == "no_collection_candidate"


@pytest.mark.asyncio
async def test_search_nft_collections_cli_returns_candidates(monkeypatch: pytest.MonkeyPatch):
    from app.tools.search_nft_collections import _run

    monkeypatch.setattr("app.tools.search_nft_collections.get_settings", lambda: _settings())
    monkeypatch.setattr("app.tools.search_nft_collections.TonAPICollectionClient", lambda _s: object())
    monkeypatch.setattr(
        "app.tools.search_nft_collections.search_nft_collections",
        AsyncMock(
            return_value={
                "ok": True,
                "query": "Pretty Posy",
                "normalized_query": "pretty posy",
                "pages_checked": 30,
                "collections_checked": 30000,
                "best_candidates": [{"name": "Pretty Posy", "address": "EQC", "score": 100, "source": "toncenter"}],
            }
        ),
    )
    out = await _run("Pretty Posy", source="toncenter", max_pages=30)
    assert out["ok"] is True
    assert out["best_candidates"]
