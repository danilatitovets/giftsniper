"""Full-market NFT listing guidance (TonAPI sale listings, no mock)."""

from __future__ import annotations

import logging
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.config import Settings
from app.services.gift_intake import GiftIdentity, GiftInput, GiftInputType
from app.services.real_market_collection_scan import (
    FullMarketNftReport,
    MarketNftRow,
    SellPricePlan,
    TargetNftInfo,
    TraitComps,
    build_full_report,
    build_sell_price_plan,
    format_full_market_nft_report,
    format_progress_message,
    resolve_target_for_full_market,
    scan_collection_listings,
)
from app.services.tonapi_collection_client import TonAPICollectionClient


def _settings(**kw: object) -> Settings:
    base: dict = {
        "BOT_TOKEN": "x",
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "TONAPI_ENABLED": True,
        "TONAPI_API_KEY": "unit-test-tonapi-key-never-commit",
        "NFT_GLOBAL_INDEX_ENABLED": False,
    }
    base.update(kw)
    return Settings(**base)


@pytest.fixture(autouse=True)
def _clear_market_cache():
    from app.services import real_market_collection_scan as rms

    rms._COLLECTION_SCAN_CACHE.clear()
    yield
    rms._COLLECTION_SCAN_CACHE.clear()


def _row(
    *,
    name: str,
    num: int,
    addr: str,
    price: float | None,
    model: str | None,
    backdrop: str | None,
    symbol: str | None,
) -> MarketNftRow:
    return MarketNftRow(
        name=name,
        number=num,
        address=addr,
        price_ton=Decimal(str(price)) if price is not None else None,
        for_sale=price is not None,
        model=model,
        backdrop=backdrop,
        symbol=symbol,
    )


def test_full_market_price_plan_icecream_sample():
    tgt = TargetNftInfo(
        name="Ice Cream #217467",
        number=217467,
        address="0:target",
        collection_name="Ice Creams",
        collection_address="0:coll",
        model="Vice Dream",
        backdrop="Ivory White",
        symbol="Moon",
    )
    rows = [
        _row(name="Cheap #1", num=1, addr="0:a1", price=3.0, model="Other", backdrop="Gray", symbol="Star"),
        _row(name="Ice Cream #315192", num=315192, addr="0:a2", price=7.0, model="Vice Dream", backdrop="Red", symbol="Sun"),
        _row(name="Ice Cream #75112", num=75112, addr="0:a3", price=9.0, model="Vice Dream", backdrop="Blue", symbol="Cloud"),
        _row(name="Ice Cream #9599", num=9599, addr="0:a4", price=12.0, model="Vice Dream", backdrop="Green", symbol="Rain"),
        _row(name="Ice Cream #x1", num=101, addr="0:a5", price=444.0, model="Vice Dream", backdrop="X", symbol="Y"),
        _row(name="Ice Cream #x2", num=102, addr="0:a6", price=888.0, model="Vice Dream", backdrop="X", symbol="Z"),
        _row(name="Ice Cream #b1", num=201, addr="0:b1", price=4.9, model="Plain", backdrop="Ivory White", symbol="A"),
        _row(name="Ice Cream #b2", num=202, addr="0:b2", price=20.0, model="Plain2", backdrop="Ivory White", symbol="B"),
        _row(name="Ice Cream #b3", num=203, addr="0:b3", price=25.0, model="Plain3", backdrop="Ivory White", symbol="C"),
        _row(name="Ice Cream #b4", num=204, addr="0:b4", price=30.0, model="Plain4", backdrop="Ivory White", symbol="D"),
        _row(name="Ice Cream #s1", num=301, addr="0:s1", price=10.0, model="M1", backdrop="B1", symbol="Moon"),
        _row(name="Ice Cream #s2", num=302, addr="0:s2", price=200.0, model="M2", backdrop="B2", symbol="Moon"),
        _row(name="Ice Cream #s3", num=303, addr="0:s3", price=333.0, model="M3", backdrop="B3", symbol="Moon"),
    ]
    settings = _settings()
    from app.services.real_market_collection_scan import build_close_comps, build_trait_comps

    list_n = sum(1 for r in rows if r.for_sale)
    same_m = build_trait_comps("model", tgt.model, rows)
    same_b = build_trait_comps("backdrop", tgt.backdrop, rows)
    same_s = build_trait_comps("symbol", tgt.symbol, rows)
    close = build_close_comps(tgt, rows)
    plan = build_sell_price_plan(
        tgt,
        rows,
        loaded_count=10000,
        listings_count=list_n,
        collection_floor=3.0,
        collection_median=10.0,
        same_model=same_m,
        same_backdrop=same_b,
        same_symbol=same_s,
        close_comps=close,
        settings=settings,
        is_partial_scan=False,
    )
    assert plan.quick_sell_ton is not None
    assert 6.7 <= plan.quick_sell_ton <= 7.05
    assert plan.normal_list_ton is not None
    assert 8.5 <= plan.normal_list_ton <= 10.5
    assert plan.high_list_ton is not None
    assert 11.5 <= plan.high_list_ton <= 14.0
    assert plan.high_list_ton not in (444.0, 888.0)
    assert plan.normal_list_ton is not None and abs(float(plan.normal_list_ton) - 4.9) > 1.0


@pytest.mark.asyncio
async def test_full_market_ignores_mock_in_production():
    from app.services.real_market_collection_scan import run_full_market_analysis_flow

    s = _settings(
        PRODUCTION_MODE=True,
        ENABLE_MOCK_SOURCE=True,
        TONAPI_API_KEY="",
    )
    client = TonAPICollectionClient(s)
    user = type("U", (), {"id": 1})()
    report, err = await run_full_market_analysis_flow(
        "0:" + "a" * 64,
        user,
        s,
        client,
        on_progress=None,
    )
    assert report is None
    assert err and "TONAPI_API_KEY" in err


@pytest.mark.asyncio
async def test_tonapi_rate_limit_retry(monkeypatch: pytest.MonkeyPatch):
    calls = {"n": 0}

    async def fake_raw(self, _addr: str, *, limit: int, offset: int):
        calls["n"] += 1
        if calls["n"] == 1:
            return [], 429, "", None
        if offset >= 5:
            return [], 200, "", None
        return (
            [{"address": f"0:x{i}", "metadata": {"name": f"Ice Cream #{i}"}} for i in range(5)],
            200,
            "",
            None,
        )

    settings = _settings(
        full_market_max_items=50,
        full_market_page_limit=100,
        full_market_request_sleep_ms=0,
        full_market_rate_limit_sleep_seconds=0.01,
        full_market_429_streak_before_reduce_limit=5,
    )
    client = TonAPICollectionClient(settings)
    prog_phases: list[str] = []

    monkeypatch.setattr(TonAPICollectionClient, "fetch_collection_items_page_raw", fake_raw)

    async def on_prog(*args: object) -> None:
        prog_phases.append(str(args[2]))

    rows, loaded, partial, _total = await scan_collection_listings(
        client,
        settings,
        "0:" + "b" * 64,
        on_progress=on_prog,
    )
    assert calls["n"] >= 2
    assert len(rows) >= 5
    assert partial is False
    assert "ratelimit" in prog_phases


@pytest.mark.asyncio
async def test_market_scan_uses_request_sleep(monkeypatch: pytest.MonkeyPatch):
    async def fake_raw(self, _addr: str, *, limit: int, offset: int):
        if offset == 0:
            return [{"address": "0:x1", "metadata": {"name": "Ice Cream #1"}} for _ in range(limit)], 200, "", None
        return [], 200, "", None

    settings = _settings(
        full_market_max_items=5000,
        full_market_page_limit=3,
        full_market_request_sleep_ms=1200,
    )
    client = TonAPICollectionClient(settings)
    monkeypatch.setattr(TonAPICollectionClient, "fetch_collection_items_page_raw", fake_raw)
    slp = AsyncMock()
    monkeypatch.setattr("app.services.real_market_collection_scan.asyncio.sleep", slp)
    await scan_collection_listings(client, settings, "0:" + "b" * 64, on_progress=None)
    assert slp.await_args_list
    assert any(abs(float(c.args[0]) - 1.2) < 0.001 for c in slp.await_args_list if c.args)


def test_full_market_report_format_contains_progress_and_real_source():
    tgt = TargetNftInfo(
        name="Ice Cream #1",
        number=1,
        address="0:t",
        collection_name="Ice Creams",
        collection_address="0:c",
        model="Vice Dream",
        backdrop="Ivory White",
        symbol="Moon",
    )
    rows = [
        _row(name="Ice Cream #2", num=2, addr="0:r2", price=7.0, model="Vice Dream", backdrop="X", symbol="Y"),
        _row(name="Ice Cream #3", num=3, addr="0:r3", price=9.0, model="Vice Dream", backdrop="X", symbol="Z"),
        _row(name="Ice Cream #4", num=4, addr="0:r4", price=12.0, model="Vice Dream", backdrop="X", symbol="W"),
    ]
    settings = _settings()
    rep = build_full_report(
        tgt,
        rows,
        loaded_count=5000,
        is_partial_scan=False,
        settings=settings,
        cache_age_minutes=None,
    )
    text = format_full_market_nft_report(rep)
    assert "TonAPI" in text
    assert "листинг" in text.lower() or "листингов" in text.lower()
    assert "Проверка NFT" in text

    prog_simple = format_progress_message(
        "Ice Creams",
        5000,
        157,
        phase="scan",
        page_limit=10_000,
        collection_total_approx=300_000,
        page_limit_note="TonAPI не принял 10 000.",
        lang="ru",
    )
    assert "Ice Creams" in prog_simple
    assert "5 000" in prog_simple
    assert "157" in prog_simple
    assert "300 000" in prog_simple
    assert "Уже проверено" in prog_simple
    assert "Найдено объявлений" in prog_simple
    low_simple = prog_simple.lower()
    assert "лимит страницы" not in low_simple
    assert "tonapi" in low_simple
    assert "из-за лимитов" not in low_simple

    prog_detail = format_progress_message(
        "Ice Creams",
        5000,
        157,
        phase="scan",
        page_limit=10_000,
        collection_total_approx=300_000,
        page_limit_note="TonAPI не принял 10 000.",
        lang="ru",
        simple_progress=False,
    )
    assert "Сканирую коллекцию" in prog_detail or "подробный" in prog_detail.lower()
    assert "лимит страницы" in prog_detail.lower()
    assert "10 000" in prog_detail

    rl_simple = format_progress_message("Ice Creams", 100, 5, phase="ratelimit", page_limit=500, lang="ru")
    assert "пауза" in rl_simple.lower() or "продолжаю" in rl_simple.lower()
    assert "100" in rl_simple and "5" in rl_simple
    assert "лимит страницы" not in rl_simple.lower()

    rl_detail = format_progress_message(
        "Ice Creams", 100, 5, phase="ratelimit", page_limit=500, lang="ru", simple_progress=False
    )
    assert "лимит страницы" in rl_detail.lower()


@pytest.mark.asyncio
async def test_resolve_by_nft_address(monkeypatch: pytest.MonkeyPatch):
    addr = "0:" + "c" * 64
    settings = _settings()
    client = TonAPICollectionClient(settings)

    async def fake_get_nft(a: str):
        assert a == addr
        return {
            "address": addr,
            "collection": {"address": "0:" + "d" * 64, "name": "Ice Creams"},
            "metadata": {
                "name": "Ice Cream #217467",
                "attributes": [
                    {"trait_type": "Model", "trait_value": "Vice Dream"},
                    {"trait_type": "Backdrop", "trait_value": "Ivory White"},
                    {"trait_type": "Symbol", "trait_value": "Moon"},
                ],
            },
        }

    monkeypatch.setattr(client, "get_nft", fake_get_nft)
    tgt, err = await resolve_target_for_full_market(addr, type("U", (), {"id": 1})(), settings, client)
    assert err is None
    assert tgt is not None
    assert tgt.collection_address
    assert tgt.model == "Vice Dream"


@pytest.mark.asyncio
async def test_resolve_by_collection_number(monkeypatch: pytest.MonkeyPatch):
    from app.services import real_market_collection_scan as rms
    from app.services import gift_resolver

    settings = _settings(collection_registry_path="data/collections.example.json")

    async def fake_resolve(user, text, st):
        gi = GiftInput(
            raw_text=text,
            input_type=GiftInputType.collection_number,
            collection="Ice Cream",
            number=217467,
        )
        ident = GiftIdentity(
            collection="Ice Cream",
            number=217467,
            nft_address=None,
            collection_address=None,
            normalized_collection="ice cream",
            canonical_key="ice cream#217467",
        )
        return gi, ident

    monkeypatch.setattr(gift_resolver, "resolve_gift_identity", fake_resolve)
    registry = {
        "Ice Cream": {
            "aliases": ["ice creams"],
            "tonapi": {"collection_address": "0:" + "e" * 64},
        }
    }
    monkeypatch.setattr(rms, "load_collection_registry", lambda path: registry)
    client = TonAPICollectionClient(settings)

    async def fake_items_raw(coll_addr: str, *, limit: int, offset: int):
        item = {
            "address": "0:nft217467",
            "index": 217467,
            "metadata": {"name": "Ice Cream #217467"},
        }
        return ([item], 200, "", {"nft_items": [item]})

    monkeypatch.setattr(client, "fetch_collection_items_page_raw", fake_items_raw)

    tgt, err = await resolve_target_for_full_market(
        "Ice Cream #217467",
        type("U", (), {"id": 1})(),
        settings,
        client,
    )
    assert err is None
    assert tgt is not None
    assert tgt.number == 217467
    assert tgt.collection_address == "0:" + "e" * 64


def test_no_api_key_leak_in_logs_or_messages(caplog: pytest.LogCaptureFixture):
    secret = "UNIT_TEST_SECRET_KEY_NO_LEAK_ZZZ"
    settings = _settings(TONAPI_API_KEY=secret)
    client = TonAPICollectionClient(settings)
    caplog.set_level(logging.INFO)
    logger = logging.getLogger("app.services.tonapi_collection_client")
    logger.warning("configured=%s", client.configured)
    assert secret not in caplog.text

    tgt = TargetNftInfo(
        name="Ice Cream #1",
        number=1,
        address="0:t",
        collection_name="Ice Creams",
        collection_address="0:c",
        model="M",
        backdrop="B",
        symbol="S",
    )
    rows = [
        _row(name="Ice Cream #2", num=2, addr="0:r2", price=7.0, model="M", backdrop="X", symbol="Y"),
        _row(name="Ice Cream #3", num=3, addr="0:r3", price=9.0, model="M", backdrop="X", symbol="Z"),
        _row(name="Ice Cream #4", num=4, addr="0:r4", price=12.0, model="M", backdrop="X", symbol="W"),
    ]
    rep = build_full_report(
        tgt,
        rows,
        loaded_count=100,
        is_partial_scan=False,
        settings=settings,
        cache_age_minutes=5.0,
    )
    text = format_full_market_nft_report(rep)
    assert secret not in text
    assert "Bearer" not in text


def test_no_mock_words_in_real_market_report():
    tgt = TargetNftInfo(
        name="Ice Cream #1",
        number=1,
        address="0:t",
        collection_name="Ice Creams",
        collection_address="0:c",
        model="Vice Dream",
        backdrop="Ivory White",
        symbol="Moon",
    )
    rows = [
        _row(name="Ice Cream #2", num=2, addr="0:r2", price=7.0, model="Vice Dream", backdrop="X", symbol="Y"),
        _row(name="Ice Cream #3", num=3, addr="0:r3", price=9.0, model="Vice Dream", backdrop="X", symbol="Z"),
        _row(name="Ice Cream #4", num=4, addr="0:r4", price=12.0, model="Vice Dream", backdrop="X", symbol="W"),
    ]
    settings = _settings()
    rep = build_full_report(
        tgt,
        rows,
        loaded_count=1000,
        is_partial_scan=False,
        settings=settings,
        cache_age_minutes=None,
    )
    text = format_full_market_nft_report(rep)
    low = text.lower()
    assert "mock" not in low
    assert "тест (mock)" not in low
    assert "безопасная покупка" not in low
    assert "максимум для покупки" not in low
    assert "источник цены" not in low


def test_no_seed_wallet_autobuy_words():
    from pathlib import Path

    roots = [
        Path("app/services/real_market_collection_scan.py"),
        Path("app/bot/handlers/sell_price.py"),
    ]
    blob = "\n".join(p.read_text(encoding="utf-8") for p in roots).lower()
    for banned in (
        "seed-фраз",
        "seed phrase",
        "mnemonic",
        "private key",
        "walletconnect",
        "wallet connect",
        "автопокуп",
        "авто-покуп",
    ):
        assert banned not in blob


def test_report_hides_invalid_collection_median_below_floor():
    tgt = TargetNftInfo(
        name="Vintage Cigar #8922",
        number=8922,
        address="0:t",
        collection_name="Vintage Cigars",
        collection_address="0:c",
        model="Warm Glow",
        backdrop="Black",
        symbol="Anchor",
    )
    plan = SellPricePlan(
        quick_sell_ton=55.0,
        normal_list_ton=90.0,
        high_list_ton=110.0,
        dont_list_below_ton=51.0,
        confidence="high",
        confidence_reason="ok",
    )
    rep = FullMarketNftReport(
        target=tgt,
        loaded_count=7600,
        listings_count=420,
        collection_floor=4.0,
        collection_median=1.0,
        same_model=TraitComps("model", "Warm Glow", 0, None, None),
        same_backdrop=TraitComps("backdrop", "Black", 0, None, None),
        same_symbol=TraitComps("symbol", "Anchor", 0, None, None),
        close_comps=[],
        sell_plan=plan,
        is_partial_scan=False,
        source_label="TonAPI, реальные листинги",
        warnings=["Медиана коллекции ниже floor — данные пересчитываются."],
    )
    text = format_full_market_nft_report(rep)
    assert "Обычная середина рынка: 1 TON" not in text
    assert "данные пересчитываются" in text.lower()


def test_price_plan_sanitizer_keeps_monotonic_order():
    from app.services import real_market_collection_scan as rms

    q, n, h, d = rms._sanitize_price_plan_monotonic(95.0, 90.0, 70.0, 96.0, p75_hint=105.0)
    assert d is not None and q is not None and n is not None and h is not None
    assert d <= q <= n <= h


def test_report_mentions_target_listing_far_above_market():
    tgt = TargetNftInfo(
        name="Vintage Cigar #8922",
        number=8922,
        address="0:t",
        collection_name="Vintage Cigars",
        collection_address="0:c",
        model="Warm Glow",
        backdrop="Black",
        symbol="Anchor",
    )
    plan = SellPricePlan(
        quick_sell_ton=56.0,
        normal_list_ton=90.0,
        high_list_ton=110.0,
        dont_list_below_ton=51.0,
        confidence="high",
        confidence_reason="ok",
        target_listing_price_ton=800.0,
    )
    rep = FullMarketNftReport(
        target=tgt,
        loaded_count=7600,
        listings_count=420,
        collection_floor=4.0,
        collection_median=70.0,
        same_model=TraitComps("model", "Warm Glow", 0, None, None),
        same_backdrop=TraitComps("backdrop", "Black", 0, None, None),
        same_symbol=TraitComps("symbol", "Anchor", 0, None, None),
        close_comps=[],
        sell_plan=plan,
        is_partial_scan=False,
        source_label="TonAPI, реальные листинги",
    )
    text = format_full_market_nft_report(rep).lower()
    assert "текущий листинг" in text
    assert "800" in text
    assert "сильно выше рынка" in text


def test_progress_has_simple_user_text():
    txt = format_progress_message("Chill Flames", 3_000, 187, phase="scan", page_limit=1_000, lang="ru")
    assert "Анализирую рынок" in txt
    assert "Chill Flames" in txt
    assert "Уже проверено" in txt
    assert "Найдено объявлений" in txt
    assert "TonAPI" in txt
    assert "3 000" in txt and "187" in txt


def test_progress_does_not_show_page_limit():
    txt = format_progress_message(
        "Ice Creams",
        100,
        12,
        phase="scan",
        page_limit=10_000,
        collection_total_approx=50_000,
        lang="ru",
    )
    assert "лимит страницы" not in txt.lower()
    assert "10 000" not in txt


def test_progress_does_not_show_tonapi_limits():
    txt = format_progress_message(
        "Ice Creams",
        1,
        2,
        phase="scan",
        page_limit=5000,
        page_limit_note="TonAPI не принял лимит",
        lang="ru",
    )
    low = txt.lower()
    assert "лимит страницы" not in low
    assert "из-за лимитов" not in low


def test_progress_uses_checked_and_found_listings_words():
    txt = format_progress_message("Pool Floats", 42, 7, phase="scan", lang="ru")
    assert "Уже проверено: 42 NFT" in txt
    assert "Найдено объявлений: 7" in txt


def test_progress_plain_title_when_collection_unknown_ru():
    txt = format_progress_message("", 0, 0, phase="start", lang="ru")
    assert txt.startswith("⏳ Анализирую рынок\n")
    assert "«" not in txt.split("\n")[0]
