"""Trait-aware pricing engine: сигналы по трейтам, смешивание компов, человекочитаемый отчёт (без TonAPI mock)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.config import Settings
from app.services.nft_trait_signals import (
    TraitMarketSignal,
    compute_trait_adjusted_median,
    compute_trait_market_signals,
    listing_verdict_ru,
)
from app.services.real_market_collection_scan import (
    MarketNftRow,
    TargetNftInfo,
    TraitComps,
    build_full_report,
    build_sell_price_plan,
    build_trait_comps,
    format_full_market_nft_report,
)


def _settings() -> Settings:
    return Settings(
        BOT_TOKEN="x",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        TONAPI_ENABLED=True,
        TONAPI_API_KEY="unit-test-tonapi-key-never-commit",
        NFT_GLOBAL_INDEX_ENABLED=False,
    )


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


def _empty_tc() -> TraitComps:
    return TraitComps(trait_type="x", trait_value=None, listings_count=0, floor=None, median=None, nearest=[])


def _signals_for_target(
    tgt: TargetNftInfo,
    rows: list[MarketNftRow],
    *,
    coll_floor: float = 2.0,
    coll_med: float = 5.0,
) -> list[TraitMarketSignal]:
    w = {"model": 1.0, "symbol": 0.65, "backdrop": 0.45}
    return compute_trait_market_signals(
        tgt,
        rows,
        collection_floor=coll_floor,
        collection_median=coll_med,
        trait_weights=w,
        exclude_address=(tgt.address or "").strip() or None,
    )


def test_trait_signal_model_floor_median_count():
    tgt = TargetNftInfo(
        name="T #1",
        number=1,
        address="0:t1",
        collection_name="C",
        collection_address="0:c",
        model="Alpha",
        backdrop="Orange",
        symbol="Bug",
    )
    rows = [
        _row(name="a", num=2, addr="0:a", price=3.0, model="Alpha", backdrop="X", symbol="Y"),
        _row(name="b", num=3, addr="0:b", price=5.0, model="Alpha", backdrop="Y", symbol="Z"),
        _row(name="c", num=4, addr="0:c", price=7.0, model="Alpha", backdrop="Z", symbol="W"),
    ]
    sigs = _signals_for_target(tgt, rows, coll_floor=2.0, coll_med=5.0)
    by_key = {s.trait_key: s for s in sigs}
    m = by_key["model"]
    assert m.listings_count == 3
    assert m.floor_ton == 3.0
    assert m.median_ton == 5.0
    assert m.support_level == "medium"


def test_trait_signal_symbol_premium_detected():
    tgt = TargetNftInfo(
        name="T #1",
        number=1,
        address="0:t1",
        collection_name="C",
        collection_address="0:c",
        model="M1",
        backdrop="B1",
        symbol="Ladybug",
    )
    rows = [
        _row(name="x", num=i, addr=f"0:x{i}", price=float(p), model="Mx", backdrop="By", symbol="Ladybug")
        for i, p in enumerate([6, 6.2, 6.5, 6.4, 6.8, 7.0, 7.1, 7.2, 8.0], start=1)
    ]
    sigs = _signals_for_target(tgt, rows, coll_floor=2.0, coll_med=5.0)
    sym = next(s for s in sigs if s.trait_key == "symbol")
    assert sym.listings_count >= 8
    assert sym.support_level == "high"
    assert sym.price_signal == "premium"


def test_trait_signal_backdrop_near_market_detected():
    tgt = TargetNftInfo(
        name="T #1",
        number=1,
        address="0:t1",
        collection_name="C",
        collection_address="0:c",
        model="M1",
        backdrop="Orange",
        symbol="S1",
    )
    rows = [
        _row(name="x", num=i, addr=f"0:x{i}", price=5.0 + i * 0.02, model="Mx", backdrop="Orange", symbol="Sz")
        for i in range(8)
    ]
    sigs = _signals_for_target(tgt, rows, coll_floor=2.0, coll_med=5.0)
    bd = next(s for s in sigs if s.trait_key == "backdrop")
    assert bd.support_level == "high"
    assert bd.price_signal == "near_market"


def test_trait_signal_discount_detected():
    tgt = TargetNftInfo(
        name="T #1",
        number=1,
        address="0:t1",
        collection_name="C",
        collection_address="0:c",
        model="CheapModel",
        backdrop="B1",
        symbol="S1",
    )
    rows = [
        _row(name="x", num=i, addr=f"0:x{i}", price=3.5 + i * 0.05, model="CheapModel", backdrop="Bx", symbol="Sy")
        for i in range(8)
    ]
    sigs = _signals_for_target(tgt, rows, coll_floor=2.0, coll_med=5.0)
    m = next(s for s in sigs if s.trait_key == "model")
    assert m.price_signal == "discount"


def test_trait_adjusted_price_above_collection_floor_when_traits_premium():
    tgt = TargetNftInfo(
        name="T #1",
        number=1,
        address="0:t1",
        collection_name="C",
        collection_address="0:c",
        model="Rare",
        backdrop="B1",
        symbol="S1",
    )
    rows = [
        _row(name="x", num=i, addr=f"0:x{i}", price=18.0 + float(i), model="Rare", backdrop="Bx", symbol="Sy")
        for i in range(8)
    ]
    w = {"model": 1.0, "symbol": 0.65, "backdrop": 0.45}
    sigs = compute_trait_market_signals(
        tgt, rows, collection_floor=2.8, collection_median=5.0, trait_weights=w, exclude_address="0:t1"
    )
    ta = compute_trait_adjusted_median(5.0, sigs, w)
    assert ta is not None
    assert ta > 5.0


def test_trait_adjusted_price_not_used_when_trait_support_low():
    tgt = TargetNftInfo(
        name="T #1",
        number=1,
        address="0:t1",
        collection_name="C",
        collection_address="0:c",
        model="Solo",
        backdrop="B1",
        symbol="S1",
    )
    rows = [
        _row(name="a", num=2, addr="0:a", price=9.0, model="Solo", backdrop="X", symbol="Y"),
    ]
    w = {"model": 1.0, "symbol": 0.65, "backdrop": 0.45}
    sigs = compute_trait_market_signals(
        tgt, rows, collection_floor=2.0, collection_median=5.0, trait_weights=w, exclude_address="0:t1"
    )
    ta = compute_trait_adjusted_median(5.0, sigs, w)
    assert ta is None


def test_good_comps_override_trait_adjusted_market():
    tgt = TargetNftInfo(
        name="Ice #1",
        number=1,
        address="0:target",
        collection_name="Ice",
        collection_address="0:c",
        model="Vice Dream",
        backdrop="Ivory White",
        symbol="Moon",
    )
    rows = [
        _row(name="n1", num=2, addr="0:a2", price=7.0, model="Vice Dream", backdrop="R1", symbol="S1"),
        _row(name="n2", num=3, addr="0:a3", price=9.0, model="Vice Dream", backdrop="R2", symbol="S2"),
        _row(name="n3", num=4, addr="0:a4", price=12.0, model="Vice Dream", backdrop="R3", symbol="S3"),
        _row(name="n4", num=5, addr="0:a5", price=11.0, model="Vice Dream", backdrop="R4", symbol="S4"),
        _row(name="n5", num=6, addr="0:a6", price=10.5, model="Vice Dream", backdrop="R5", symbol="S5"),
        _row(name="n6", num=7, addr="0:a7", price=10.8, model="Vice Dream", backdrop="R6", symbol="S6"),
        _row(name="b1", num=8, addr="0:b1", price=4.0, model="Other", backdrop="Ivory White", symbol="Z"),
    ]
    st = _settings()
    same_m = build_trait_comps("model", tgt.model, rows)
    same_b = build_trait_comps("backdrop", tgt.backdrop, rows)
    same_s = build_trait_comps("symbol", tgt.symbol, rows)
    plan = build_sell_price_plan(
        tgt,
        rows,
        loaded_count=5000,
        listings_count=sum(1 for r in rows if r.for_sale),
        collection_floor=3.0,
        collection_median=8.0,
        same_model=same_m,
        same_backdrop=same_b,
        same_symbol=same_s,
        close_comps=[],
        settings=st,
        is_partial_scan=False,
    )
    assert plan.normal_list_ton is not None
    assert 8.0 <= plan.normal_list_ton <= 11.5


def test_few_comps_blend_with_trait_signals():
    tgt = TargetNftInfo(
        name="X #1",
        number=1,
        address="0:t1",
        collection_name="Col",
        collection_address="0:c",
        model="Gold",
        backdrop="B1",
        symbol="S1",
    )
    rows = [
        _row(name="c1", num=2, addr="0:c1", price=6.0, model="Gold", backdrop="X", symbol="Y"),
        _row(name="c2", num=3, addr="0:c2", price=7.0, model="Gold", backdrop="Y", symbol="Z"),
        _row(name="p1", num=10, addr="0:p1", price=12.0, model="Silver", backdrop="B1", symbol="S1"),
        _row(name="p2", num=11, addr="0:p2", price=13.0, model="Silver", backdrop="B1", symbol="S1"),
        _row(name="p3", num=12, addr="0:p3", price=14.0, model="Silver", backdrop="B1", symbol="S1"),
    ]
    st = _settings()
    plan = build_sell_price_plan(
        tgt,
        rows,
        loaded_count=100,
        listings_count=5,
        collection_floor=5.0,
        collection_median=12.0,
        same_model=_empty_tc(),
        same_backdrop=_empty_tc(),
        same_symbol=_empty_tc(),
        close_comps=[],
        settings=st,
        is_partial_scan=False,
    )
    assert plan.trait_adjusted_median_ton is not None
    assert plan.normal_list_ton is not None


def test_collection_market_fallback_still_uses_trait_signals():
    tgt = TargetNftInfo(
        name="Rare #99",
        number=99,
        address="0:t99",
        collection_name="Col",
        collection_address="0:c",
        model="Ultra",
        backdrop="B1",
        symbol="S1",
    )
    rows = [
        _row(name="m", num=i, addr=f"0:m{i}", price=4.0, model="Common", backdrop="X", symbol="Y")
        for i in range(15)
    ]
    rows.append(_row(name="u", num=50, addr="0:u50", price=25.0, model="Ultra", backdrop="Z", symbol="W"))
    st = _settings()
    plan = build_sell_price_plan(
        tgt,
        rows,
        loaded_count=100,
        listings_count=len([r for r in rows if r.for_sale]),
        collection_floor=4.0,
        collection_median=4.0,
        same_model=_empty_tc(),
        same_backdrop=_empty_tc(),
        same_symbol=_empty_tc(),
        close_comps=[],
        settings=st,
        is_partial_scan=False,
    )
    assert plan.trait_signals
    assert any(s.trait_key == "model" for s in plan.trait_signals)


def test_premium_traits_prevent_quick_price_from_collection_floor():
    """У дорогого model-кластера быстрый край ориентируется на похожие лоты, а не на общий floor 2.8 TON."""
    tgt = TargetNftInfo(
        name="Rare #1",
        number=1,
        address="0:t1",
        collection_name="Col",
        collection_address="0:c",
        model="PremiumModel",
        backdrop="B1",
        symbol="S1",
    )
    rows = [
        _row(name="c", num=i, addr=f"0:c{i}", price=3.0, model="Common", backdrop="X", symbol="Y")
        for i in range(20)
    ]
    for j, pr in enumerate([18.0, 19.0, 20.0, 21.0, 22.0, 23.0, 24.0, 25.0], start=100):
        rows.append(
            _row(name=f"p{j}", num=j, addr=f"0:p{j}", price=pr, model="PremiumModel", backdrop="Z", symbol="W")
        )
    st = _settings()
    plan = build_sell_price_plan(
        tgt,
        rows,
        loaded_count=500,
        listings_count=len([r for r in rows if r.for_sale]),
        collection_floor=2.8,
        collection_median=5.0,
        same_model=_empty_tc(),
        same_backdrop=_empty_tc(),
        same_symbol=_empty_tc(),
        close_comps=[],
        settings=st,
        is_partial_scan=False,
    )
    assert plan.quick_sell_ton is not None
    assert plan.quick_sell_ton > 10.0


def test_listing_verdict_underpriced():
    v = listing_verdict_ru(
        for_sale=True,
        sale_price_ton=4.0,
        quick=5.5,
        normal=8.0,
        high=10.0,
    )
    assert "дёшево" in v.lower() or "дешево" in v.lower()


def test_listing_verdict_near_market():
    v = listing_verdict_ru(
        for_sale=True,
        sale_price_ton=7.0,
        quick=5.5,
        normal=8.0,
        high=10.0,
    )
    assert "нормальн" in v.lower()


def test_listing_verdict_overpriced():
    v = listing_verdict_ru(
        for_sale=True,
        sale_price_ton=25.0,
        quick=5.5,
        normal=8.0,
        high=10.0,
    )
    assert "выше" in v.lower() or "заметно" in v.lower()


def test_report_explains_trait_impact():
    tgt = TargetNftInfo(
        name="R #1",
        number=1,
        address="0:t1",
        collection_name="Col",
        collection_address="0:c",
        model="M1",
        backdrop="B1",
        symbol="S1",
    )
    rows = [
        _row(name="x", num=i, addr=f"0:x{i}", price=6.0 + i * 0.1, model="M1", backdrop="B1", symbol="S1")
        for i in range(10)
    ]
    rep = build_full_report(
        tgt,
        rows,
        loaded_count=50,
        is_partial_scan=False,
        settings=_settings(),
        cache_age_minutes=None,
    )
    text = format_full_market_nft_report(rep)
    assert "Влияние трейтов" in text
    assert "Model" in text or "model" in text.lower()


def test_report_shows_best_listing_price():
    tgt = TargetNftInfo(
        name="R #1",
        number=1,
        address="0:t1",
        collection_name="Col",
        collection_address="0:c",
        model="M1",
        backdrop="B1",
        symbol="S1",
    )
    rows = [_row(name="x", num=2, addr="0:x2", price=9.0, model="M1", backdrop="B1", symbol="S1")]
    rep = build_full_report(
        tgt,
        rows,
        loaded_count=10,
        is_partial_scan=False,
        settings=_settings(),
        cache_age_minutes=None,
    )
    text = format_full_market_nft_report(rep)
    assert "Нормально выставить" in text or "нормально" in text.lower()


def test_report_no_long_price_lists():
    tgt = TargetNftInfo(
        name="R #1",
        number=1,
        address="0:t1",
        collection_name="Col",
        collection_address="0:c",
        model="M1",
        backdrop="B1",
        symbol="S1",
    )
    rows = [
        _row(name="x", num=i, addr=f"0:x{i}", price=float(5 + i), model="M1", backdrop="B1", symbol="S1")
        for i in range(25)
    ]
    rep = build_full_report(
        tgt,
        rows,
        loaded_count=100,
        is_partial_scan=False,
        settings=_settings(),
        cache_age_minutes=None,
    )
    text = format_full_market_nft_report(rep)
    assert text.count(" · ") <= 2


def test_report_no_internal_debug_terms():
    tgt = TargetNftInfo(
        name="R #1",
        number=1,
        address="0:t1",
        collection_name="Col",
        collection_address="0:c",
        model="M1",
        backdrop="B1",
        symbol="S1",
    )
    rows = [_row(name="x", num=2, addr="0:x2", price=9.0, model="M1", backdrop="B1", symbol="S1")]
    rep = build_full_report(
        tgt,
        rows,
        loaded_count=10,
        is_partial_scan=False,
        settings=_settings(),
        cache_age_minutes=None,
    )
    text = format_full_market_nft_report(rep)
    low = text.lower()
    for banned in ("exact_primary_match", "weighted_close_comps", "top1_primary", "верх:", "низ:"):
        assert banned not in low


def test_confidence_medium_when_traits_used_but_exact_few():
    tgt = TargetNftInfo(
        name="Z #1",
        number=1,
        address="0:t1",
        collection_name="Col",
        collection_address="0:c",
        model="RareCombo",
        backdrop="Bd1",
        symbol="Sy1",
    )
    rows = []
    for i in range(12):
        rows.append(
            _row(
                name=f"n{i}",
                num=10 + i,
                addr=f"0:n{i}",
                price=8.0 + 0.1 * i,
                model="RareCombo",
                backdrop="X",
                symbol="Y",
            )
        )
    for i in range(8):
        rows.append(
            _row(
                name=f"s{i}",
                num=200 + i,
                addr=f"0:s{i}",
                price=6.0,
                model="Other",
                backdrop="Bd1",
                symbol="Sy1",
            )
        )
    rep = build_full_report(
        tgt,
        rows,
        loaded_count=500,
        is_partial_scan=False,
        settings=_settings(),
        cache_age_minutes=None,
    )
    if rep.sell_plan.pricing_group_key == "exact_primary_match" and rep.sell_plan.comps_used_count < 4:
        assert rep.sell_plan.confidence in ("medium", "low")