"""Production-grade /check market core: listings, traits, weights, outliers, confidence, report."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.config import Settings
from app.services import nft_market_pricing_core as core
from app.services.real_market_collection_scan import (
    MarketNftRow,
    TargetNftInfo,
    build_full_report,
    dedupe_scan_rows,
    extract_collection_total_approx,
    format_full_market_nft_report,
    normalize_traits_from_nft_item,
    parse_market_nft_row,
    scan_collection_listings,
)
from app.services.tonapi_collection_client import TonAPICollectionClient


def _s(**kw: object) -> Settings:
    base: dict = {
        "BOT_TOKEN": "x",
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "TONAPI_ENABLED": True,
        "TONAPI_API_KEY": "k",
    }
    base.update(kw)
    return Settings(**base)


def _row(addr: str, price: float | None, **traits: str) -> MarketNftRow:
    tnorm = {k.lower(): v for k, v in traits.items()}
    return MarketNftRow(
        name="N",
        number=1,
        address=addr,
        price_ton=Decimal(str(price)) if price is not None else None,
        for_sale=price is not None,
        model=tnorm.get("model"),
        backdrop=tnorm.get("backdrop"),
        symbol=tnorm.get("symbol"),
        traits_normalized=tnorm,
    )


def test_sale_only_no_price_in_comps():
    r = parse_market_nft_row({"address": "0:a", "metadata": {"name": "X #1"}})
    assert r.for_sale is False
    assert r.price_ton is None


def test_currency_non_ton_rejected():
    item = {
        "address": "0:j",
        "metadata": {"name": "J #1"},
        "sale": {
            "price": {"value": int(10e9), "decimals": 9, "currency": "USDT"},
            "market": {"address": "0:m"},
        },
    }
    r = parse_market_nft_row(item)
    assert r.for_sale is False


def test_target_excluded_via_sale_rows():
    tgt = TargetNftInfo(
        name="T #1",
        number=1,
        address="0:t",
        collection_name="C",
        collection_address="0:c",
        model="M",
        backdrop="B",
        symbol="S",
        traits_normalized={"model": "M"},
    )
    rows = [
        _row("0:t", 100.0, model="M"),
        _row("0:a", 5.0, model="M"),
        _row("0:b", 6.0, model="M"),
        _row("0:c", 7.0, model="M"),
    ]
    from app.services.real_market_collection_scan import _sale_rows_for_comps

    comps = _sale_rows_for_comps(tgt, rows)
    assert all(r.address != "0:t" for r in comps)


def test_dedupe_by_nft_address():
    rows = [
        _row("0:a", 1.0, model="X"),
        _row("0:a", 9.0, model="X"),
        _row("0:b", 2.0, model="Y"),
    ]
    d = dedupe_scan_rows(rows)
    assert len(d) == 2
    by = {r.address: float(r.price_ton or 0) for r in d if r.address}
    assert by["0:a"] == 9.0


def test_trait_normalization_keys_and_spaces():
    item = {
        "metadata": {
            "attributes": [
                {"trait_type": "  Model ", "trait_value": "  Alpha  "},
                {"trait_type": "PATTERN", "trait_value": "Dots"},
            ]
        }
    }
    t = normalize_traits_from_nft_item(item)
    assert t.get("model") == "Alpha"
    assert t.get("pattern") == "Dots"


def test_unknown_traits_preserved():
    t = normalize_traits_from_nft_item(
        {"metadata": {"attributes": [{"trait_type": "RareTag", "trait_value": "Gold"}]}}
    )
    assert "raretag" in t
    assert t["raretag"] == "Gold"


def test_custom_trait_weights_priority(monkeypatch: pytest.MonkeyPatch):
    registry = {
        "MyCol": {
            "trait_weights": {"pattern": 2.0, "model": 0.1},
        }
    }
    w = core.load_collection_trait_weights_override("MyCol", registry)
    assert w is not None
    assert w.get("pattern", 0) > w.get("model", 0)


def test_auto_trait_weights_requires_sample():
    rows = [_row(f"0:{i}", float(i), model="A" if i % 2 else "B") for i in range(1, 10)]
    auto = core.infer_auto_trait_weights(rows, exclude_address=None)
    assert auto == {}


def test_filter_high_tail_and_thin_floor():
    er = core.filter_outliers_enhanced([7, 9, 12, 444, 888])
    assert er.used_prices == [7, 9, 12]
    assert 444 in er.removed_high_outliers or 444 in er.removed_low_outliers
    assert 888 in er.removed_high_outliers or 888 in er.removed_low_outliers

    thin = core.filter_outliers_enhanced([1.0, 5.0, 5.2, 5.4, 5.5])
    assert 1.0 in thin.removed_low_outliers or 1.0 in thin.used_prices


def test_small_sample_filter_not_empty():
    er = core.filter_outliers_enhanced([2.0, 2.1])
    assert er.used_prices == [2.0, 2.1]


def test_report_has_market_state_and_confidence():
    tgt = TargetNftInfo(
        name="R #1",
        number=1,
        address="0:t",
        collection_name="Col",
        collection_address="0:c",
        model="M",
        backdrop="B",
        symbol="S",
        traits_normalized={"model": "M"},
    )
    rows = [_row("0:a", 5.0, model="M"), _row("0:b", 6.0, model="M"), _row("0:c", 7.0, model="M")]
    rep = build_full_report(tgt, rows, loaded_count=10, is_partial_scan=True, settings=_s(), cache_age_minutes=60.0)
    txt = format_full_market_nft_report(rep)
    assert "частичный" in txt.lower()
    assert "уверенность" in txt.lower()
    assert "листинг" in txt.lower()


def test_no_fake_examples_when_clean_outliers():
    tgt = TargetNftInfo(
        name="C #1",
        number=1,
        address="0:t",
        collection_name="Col",
        collection_address="0:c",
        model="M",
        backdrop="B",
        symbol="S",
        traits_normalized={"model": "M"},
    )
    rows = [_row("0:a", 3.0, model="M"), _row("0:b", 4.0, model="M"), _row("0:c", 5.0, model="M")]
    txt = format_full_market_nft_report(build_full_report(tgt, rows, loaded_count=3, is_partial_scan=False, settings=_s(), cache_age_minutes=None))
    assert "444" not in txt
    assert "888" not in txt


def test_settings_populate_by_name_full_market_limit():
    s = Settings(
        BOT_TOKEN="t",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        FULL_MARKET_PAGE_LIMIT=2345,
    )
    assert s.full_market_page_limit == 2345


def test_full_market_page_limit_field_default_is_10000():
    assert Settings.model_fields["full_market_page_limit"].default == 10_000


def test_extract_collection_total_from_root_total():
    assert extract_collection_total_approx({"total": 300_000, "nft_items": []}) == 300_000


def test_extract_collection_total_none_when_no_known_fields():
    assert extract_collection_total_approx({"nft_items": [{"address": "0:a", "metadata": {"name": "X"}}]}) is None


def test_extract_collection_total_from_nested_collection_next_item_index():
    assert (
        extract_collection_total_approx(
            {
                "nft_items": [
                    {"address": "0:a", "metadata": {"name": "X"}, "collection": {"next_item_index": "15000"}},
                ]
            }
        )
        == 15000
    )


def test_report_shows_loaded_from_approx_total_when_set():
    tgt = TargetNftInfo(
        name="R #1",
        number=1,
        address="0:t",
        collection_name="Col",
        collection_address="0:c",
        model="M",
        backdrop="B",
        symbol="S",
        traits_normalized={"model": "M"},
    )
    rows = [_row("0:a", 5.0, model="M"), _row("0:b", 6.0, model="M"), _row("0:c", 7.0, model="M")]
    rep = build_full_report(
        tgt,
        rows,
        loaded_count=10_000,
        is_partial_scan=True,
        settings=_s(),
        cache_age_minutes=None,
        collection_total_approx=300_000,
    )
    txt = format_full_market_nft_report(rep)
    assert "10 000" in txt and "300 000" in txt
    assert "меньше, чем NFT в коллекции" in txt or "частичный" in txt.lower()


def test_report_no_approx_suffix_when_total_unknown():
    tgt = TargetNftInfo(
        name="R #1",
        number=1,
        address="0:t",
        collection_name="Col",
        collection_address="0:c",
        model="M",
        backdrop="B",
        symbol="S",
        traits_normalized={"model": "M"},
    )
    rows = [_row("0:a", 5.0, model="M"), _row("0:b", 6.0, model="M"), _row("0:c", 7.0, model="M")]
    txt = format_full_market_nft_report(
        build_full_report(
            tgt,
            rows,
            loaded_count=100,
            is_partial_scan=False,
            settings=_s(),
            cache_age_minutes=None,
            collection_total_approx=None,
        )
    )
    assert "из ~" not in txt
    assert "100" in txt and "Просканировано" in txt


def test_progress_contains_loaded_listings_limit_source():
    from app.services.real_market_collection_scan import format_progress_message

    txt = format_progress_message(
        "Pretty Posy",
        23000,
        656,
        phase="scan",
        page_limit=1000,
        collection_total_approx=120000,
        lang="ru",
    )
    low = txt.lower()
    assert "уже проверено" in low
    assert "найдено объявлений" in low
    assert "лимит страницы" not in low
    assert "tonapi" in low


@pytest.mark.asyncio
async def test_scan_collection_listings_reads_total_from_first_page(monkeypatch: pytest.MonkeyPatch):
    st = _s(
        full_market_max_items=50,
        full_market_page_limit=100,
        full_market_min_page_limit=10,
        full_market_request_sleep_ms=0,
    )
    client = TonAPICollectionClient(st)

    async def fake_raw(self, _addr: str, *, limit: int, offset: int):
        items = [{"address": f"0:x{i}", "metadata": {"name": f"N #{i}"}} for i in range(3)]
        payload = {"nft_items": items, "total": 3}
        return [x for x in items if isinstance(x, dict)], 200, "", payload

    monkeypatch.setattr(TonAPICollectionClient, "fetch_collection_items_page_raw", fake_raw)
    rows, loaded, partial, total = await scan_collection_listings(client, st, "0:coll", on_progress=None)
    assert total == 3
    assert loaded == 3
    assert partial is False
