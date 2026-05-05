"""Universal full-market pricing: comps hierarchy, outliers, traits, no hardcoded demos."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.config import Settings
from app.services.real_market_collection_scan import (
    MarketNftRow,
    TargetNftInfo,
    build_full_report,
    build_sell_price_plan,
    filter_outliers,
    format_full_market_nft_report,
    normalize_traits_from_nft_item,
    parse_market_nft_row,
    build_trait_comps,
    build_close_comps,
)


def _settings(**kw: object) -> Settings:
    base: dict = {
        "BOT_TOKEN": "x",
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "TONAPI_ENABLED": True,
        "TONAPI_API_KEY": "k",
    }
    base.update(kw)
    return Settings(**base)


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
    traits: dict[str, str] = {}
    if model:
        traits["model"] = model
    if backdrop:
        traits["backdrop"] = backdrop
    if symbol:
        traits["symbol"] = symbol
    return MarketNftRow(
        name=name,
        number=num,
        address=addr,
        price_ton=Decimal(str(price)) if price is not None else None,
        for_sale=price is not None,
        model=model,
        backdrop=backdrop,
        symbol=symbol,
        sale_market=None,
        traits_normalized=traits,
    )


def test_same_model_priority_over_collection_floor():
    tgt = TargetNftInfo(
        name="Any #1",
        number=1,
        address="0:t1",
        collection_name="AnyCol",
        collection_address="0:c",
        model="Alpha",
        backdrop="B1",
        symbol="S1",
        traits_normalized={"model": "Alpha", "backdrop": "B1", "symbol": "S1"},
    )
    rows = [
        _row(name="Any #2", num=2, addr="0:a", price=3.9, model="Alpha", backdrop="x", symbol="y"),
        _row(name="Any #3", num=3, addr="0:b", price=5.2, model="Alpha", backdrop="x", symbol="z"),
        _row(name="Any #4", num=4, addr="0:c", price=5.5, model="Alpha", backdrop="x", symbol="w"),
        _row(name="Any #5", num=5, addr="0:d", price=7.0, model="Alpha", backdrop="x", symbol="q"),
        _row(name="Any #6", num=6, addr="0:e", price=9.0, model="Alpha", backdrop="x", symbol="r"),
        _row(name="Other #1", num=10, addr="0:o", price=3.0, model="Beta", backdrop="x", symbol="y"),
    ]
    st = _settings()
    same_m = build_trait_comps("model", tgt.model, rows)
    same_b = build_trait_comps("backdrop", tgt.backdrop, rows)
    same_s = build_trait_comps("symbol", tgt.symbol, rows)
    close = build_close_comps(tgt, rows)
    plan = build_sell_price_plan(
        tgt,
        rows,
        loaded_count=5000,
        listings_count=6,
        collection_floor=3.0,
        collection_median=5.0,
        same_model=same_m,
        same_backdrop=same_b,
        same_symbol=same_s,
        close_comps=close,
        settings=st,
        is_partial_scan=False,
    )
    assert plan.pricing_group_key in ("top1_primary_match", "weighted_close_comps", "exact_primary_match")
    assert plan.quick_sell_ton is not None
    assert 3.7 <= plan.quick_sell_ton <= 3.85
    assert plan.normal_list_ton is not None
    assert 5.0 <= plan.normal_list_ton <= 6.0
    rep = build_full_report(tgt, rows, loaded_count=100, is_partial_scan=False, settings=st, cache_age_minutes=None)
    txt = format_full_market_nft_report(rep)
    assert "Model" in txt or "model" in txt.lower()


def test_outlier_filter_separates_spikes():
    fr = filter_outliers([7, 9, 12, 444, 888])
    assert fr.used_prices == [7, 9, 12]
    assert 444 in fr.outlier_prices and 888 in fr.outlier_prices
    tgt = TargetNftInfo(
        name="X #1",
        number=1,
        address="0:t",
        collection_name="Col",
        collection_address="0:c",
        model="M",
        backdrop="B",
        symbol="S",
        traits_normalized={"model": "M", "backdrop": "B", "symbol": "S"},
    )
    rows = [
        _row(name="X #2", num=2, addr="0:a", price=7.0, model="M", backdrop="b", symbol="s"),
        _row(name="X #3", num=3, addr="0:b", price=9.0, model="M", backdrop="b", symbol="s"),
        _row(name="X #4", num=4, addr="0:c", price=12.0, model="M", backdrop="b", symbol="s"),
        _row(name="X #5", num=5, addr="0:d", price=444.0, model="M", backdrop="b", symbol="s"),
        _row(name="X #6", num=6, addr="0:e", price=888.0, model="M", backdrop="b", symbol="s"),
    ]
    st = _settings()
    plan = build_sell_price_plan(
        tgt,
        rows,
        loaded_count=100,
        listings_count=5,
        collection_floor=3.0,
        collection_median=50.0,
        same_model=build_trait_comps("model", tgt.model, rows),
        same_backdrop=build_trait_comps("backdrop", tgt.backdrop, rows),
        same_symbol=build_trait_comps("symbol", tgt.symbol, rows),
        close_comps=build_close_comps(tgt, rows),
        settings=st,
        is_partial_scan=False,
    )
    assert plan.quick_sell_ton is not None
    assert 6.7 <= plan.quick_sell_ton <= 6.85
    assert plan.normal_list_ton is not None
    assert 8.5 <= plan.normal_list_ton <= 9.5
    assert plan.high_list_ton is not None
    assert 11.5 <= plan.high_list_ton <= 12.5


def test_no_hardcoded_outlier_text_when_clean():
    tgt = TargetNftInfo(
        name="Y #1",
        number=1,
        address="0:t",
        collection_name="Col",
        collection_address="0:c",
        model="M",
        backdrop="B",
        symbol="S",
        traits_normalized={"model": "M"},
    )
    rows = [
        _row(name="Y #2", num=2, addr="0:a", price=3.0, model="M", backdrop="x", symbol="y"),
        _row(name="Y #3", num=3, addr="0:b", price=4.0, model="M", backdrop="x", symbol="y"),
        _row(name="Y #4", num=4, addr="0:c", price=5.0, model="M", backdrop="x", symbol="y"),
    ]
    st = _settings()
    rep = build_full_report(tgt, rows, loaded_count=50, is_partial_scan=False, settings=st, cache_age_minutes=None)
    txt = format_full_market_nft_report(rep)
    assert "444" not in txt
    assert "888" not in txt


def test_close_comps_fallback_when_same_model_too_few():
    """Два листинга с тем же Model; пять+ с match≥50 за счёт Symbol+Backdrop+доп. трейтов без Model."""
    tgt = TargetNftInfo(
        name="Z #1",
        number=1,
        address="0:t",
        collection_name="Col",
        collection_address="0:c",
        model="Rare",
        backdrop="B",
        symbol="S",
        traits_normalized={
            "model": "Rare",
            "backdrop": "B",
            "symbol": "S",
            "edition": "Gold",
            "finish": "Matte",
        },
    )

    def mkrow(n: int, addr: str, price: float, *, model: str, backdrop: str = "B") -> MarketNftRow:
        traits = {
            "model": model,
            "backdrop": backdrop,
            "symbol": "S",
            "edition": "Gold",
            "finish": "Matte",
        }
        return MarketNftRow(
            name=f"Z #{n}",
            number=n,
            address=addr,
            price_ton=Decimal(str(price)),
            for_sale=True,
            model=model,
            backdrop=backdrop,
            symbol="S",
            sale_market=None,
            traits_normalized=traits,
        )

    rows = [
        mkrow(2, "0:a", 10.0, model="Rare"),
        mkrow(3, "0:b", 11.0, model="Rare", backdrop="B2"),
        mkrow(4, "0:c", 12.0, model="Other"),
        mkrow(5, "0:d", 13.0, model="Other"),
        mkrow(6, "0:e", 14.0, model="Other"),
        mkrow(7, "0:f", 15.0, model="Other"),
        mkrow(8, "0:g", 16.0, model="Other"),
    ]
    st = _settings()
    plan = build_sell_price_plan(
        tgt,
        rows,
        loaded_count=100,
        listings_count=7,
        collection_floor=9.0,
        collection_median=12.0,
        same_model=build_trait_comps("model", tgt.model, rows),
        same_backdrop=build_trait_comps("backdrop", tgt.backdrop, rows),
        same_symbol=build_trait_comps("symbol", tgt.symbol, rows),
        close_comps=build_close_comps(tgt, rows),
        settings=st,
        is_partial_scan=False,
    )
    assert plan.pricing_group_key == "weighted_close_comps"
    assert plan.confidence == "medium"


def test_collection_market_fallback_low_confidence():
    tgt = TargetNftInfo(
        name="Q #1",
        number=1,
        address="0:t",
        collection_name="Col",
        collection_address="0:c",
        model="OnlyMe",
        backdrop="B",
        symbol="S",
        traits_normalized={"model": "OnlyMe"},
    )
    rows = [
        _row(name="O #1", num=10, addr="0:o1", price=20.0, model="Other", backdrop="b", symbol="s"),
        _row(name="O #2", num=11, addr="0:o2", price=25.0, model="Other", backdrop="b", symbol="s"),
        _row(name="O #3", num=12, addr="0:o3", price=30.0, model="Other", backdrop="b", symbol="s"),
    ]
    st = _settings()
    plan = build_sell_price_plan(
        tgt,
        rows,
        loaded_count=50,
        listings_count=3,
        collection_floor=20.0,
        collection_median=25.0,
        same_model=build_trait_comps("model", tgt.model, rows),
        same_backdrop=build_trait_comps("backdrop", tgt.backdrop, rows),
        same_symbol=build_trait_comps("symbol", tgt.symbol, rows),
        close_comps=build_close_comps(tgt, rows),
        settings=st,
        is_partial_scan=False,
    )
    assert plan.used_collection_market_fallback or plan.pricing_group_key == "collection_market"
    assert plan.confidence == "low"


def test_exact_match_priority_over_same_model():
    tgt = TargetNftInfo(
        name="E #1",
        number=1,
        address="0:t",
        collection_name="Col",
        collection_address="0:c",
        model="M",
        backdrop="B",
        symbol="S",
        traits_normalized={"model": "M", "backdrop": "B", "symbol": "S"},
    )
    rows = [
        _row(name="E #2", num=2, addr="0:a", price=50.0, model="M", backdrop="B", symbol="S"),
        _row(name="E #3", num=3, addr="0:b", price=52.0, model="M", backdrop="B", symbol="S"),
        _row(name="E #4", num=4, addr="0:c", price=55.0, model="M", backdrop="B", symbol="S"),
        _row(name="E #5", num=5, addr="0:d", price=5.0, model="M", backdrop="X", symbol="Y"),
        _row(name="E #6", num=6, addr="0:e", price=6.0, model="M", backdrop="X", symbol="Z"),
        _row(name="E #7", num=7, addr="0:f", price=7.0, model="M", backdrop="X", symbol="W"),
    ]
    st = _settings()
    plan = build_sell_price_plan(
        tgt,
        rows,
        loaded_count=200,
        listings_count=6,
        collection_floor=5.0,
        collection_median=30.0,
        same_model=build_trait_comps("model", tgt.model, rows),
        same_backdrop=build_trait_comps("backdrop", tgt.backdrop, rows),
        same_symbol=build_trait_comps("symbol", tgt.symbol, rows),
        close_comps=build_close_comps(tgt, rows),
        settings=st,
        is_partial_scan=False,
    )
    assert plan.pricing_group_key == "exact_primary_match"
    assert plan.normal_list_ton is not None
    assert plan.normal_list_ton >= 50.0


def test_no_mock_words_in_report():
    tgt = TargetNftInfo(
        name="N #1",
        number=1,
        address="0:t",
        collection_name="Col",
        collection_address="0:c",
        model="M",
        backdrop="B",
        symbol="S",
        traits_normalized={"model": "M"},
    )
    rows = [
        _row(name="N #2", num=2, addr="0:a", price=5.0, model="M", backdrop="x", symbol="y"),
        _row(name="N #3", num=3, addr="0:b", price=6.0, model="M", backdrop="x", symbol="y"),
        _row(name="N #4", num=4, addr="0:c", price=7.0, model="M", backdrop="x", symbol="y"),
    ]
    st = _settings()
    rep = build_full_report(tgt, rows, loaded_count=10, is_partial_scan=False, settings=st, cache_age_minutes=None)
    low = format_full_market_nft_report(rep).lower()
    assert "mock" not in low
    assert "тест" not in low
    assert "заглушка" not in low


def test_sale_only_listings_in_parse():
    item = {
        "address": "0:abc",
        "metadata": {"name": "T #1", "attributes": [{"trait_type": "Model", "trait_value": "X"}]},
    }
    row = parse_market_nft_row(item)
    assert row.for_sale is False
    assert row.price_ton is None

    item2 = {
        "address": "0:abc2",
        "metadata": {"name": "T #2"},
        "sale": {"price": {"value": int(5e9), "decimals": 9}, "market": {"address": "0:m"}},
    }
    r2 = parse_market_nft_row(item2)
    assert r2.for_sale is True
    assert float(r2.price_ton or 0) == 5.0


def test_normalize_traits_variants():
    a1 = {"metadata": {"attributes": [{"trait_type": "Model", "trait_value": "A"}]}}
    assert normalize_traits_from_nft_item(a1)["model"] == "A"

    a2 = {"traits": [{"type": "Backdrop", "value": "Blue"}]}
    assert normalize_traits_from_nft_item(a2)["backdrop"] == "Blue"

    a3 = {"metadata": {"content": {"attributes": [{"name": "Symbol", "trait_value": "Star"}]}}}
    assert normalize_traits_from_nft_item(a3)["symbol"] == "Star"
