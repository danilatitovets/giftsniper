"""Stage 30: market brain, pricing, decisions, safety strings."""

from datetime import datetime, timezone

from app.config import get_settings
from app.schemas.analysis import FlipAnalysisResult
from app.schemas.gift import GiftAttributeSchema
from app.schemas.market import MarketDataQuality, MarketFloor
from app.schemas.market_brain import CollectionMarketProfile, TraitMarketProfile
from app.services.important_traits import detect_important_traits, score_important_trait_keyword
from app.services.market_intelligence import build_collection_market_profile, build_trait_market_profile, format_market_intelligence_report
from app.services.opportunity_scoring import calculate_opportunity_score
from app.services.pricing import calculate_precision_price_plan, calculate_stop_loss_price
from app.services.rarity import calculate_trait_rarity_profile
from app.services.trait_opportunity import detect_mispriced_rare_listing


def _floor(coll: str, price: float) -> MarketFloor:
    return MarketFloor(collection=coll, source="test", floor_ton=price, listed_count=10, created_at=datetime.now(timezone.utc))


def test_collection_profile_no_sales_warns():
    profile = build_collection_market_profile("X", _floor("X", 100), [], [], get_settings(), source_quality="mock")
    assert profile.recent_sales_count == 0
    assert any("продаж" in w.lower() for w in profile.warnings)


def test_trait_premium_no_sales_warning():
    coll = CollectionMarketProfile(
        collection="X",
        collection_floor_ton=100,
        median_sale_price_ton=90,
        recent_sales_count=5,
        liquidity_score=50,
    )
    tp = build_trait_market_profile("X", "Backdrop", "Monochrome", 300.0, coll, [], [], None, get_settings())
    assert any("фейк" in w.lower() or "премиум" in w.lower() for w in tp.warnings)


def test_monochrome_important_keyword():
    attrs = [GiftAttributeSchema(trait_type="Backdrop", trait_value="Monochrome")]
    assert score_important_trait_keyword("Backdrop", "Monochrome", get_settings()) > 0
    assert len(detect_important_traits(attrs, get_settings())) == 1


def test_safe_buy_below_floor_when_no_sales():
    base = FlipAnalysisResult(
        buy_zone_min_ton=10,
        buy_zone_max_ton=80,
        quick_sell_price_ton=50,
        fair_price_ton=70,
        list_price_ton=90,
        optimistic_price_ton=100,
        stop_price_ton=40,
        marketplace_fee_percent=5,
        expected_net_sale_ton=85,
        expected_profit_ton=10,
        expected_roi_percent=15,
        liquidity_score=50,
        risk_score=40,
        confidence_score=60,
        recommendation="HOLD",
    )
    coll = CollectionMarketProfile(
        collection="X",
        collection_floor_ton=100,
        median_sale_price_ton=None,
        recent_sales_count=0,
        liquidity_score=40,
    )
    plan = calculate_precision_price_plan(
        base,
        coll,
        risk_mode="normal",
        marketplace_fee_percent=5,
        estimated_extra_costs_ton=0,
        min_profit_ton=5,
        floor=100,
        median_sale=None,
        sales_count=0,
        listing_low=95,
        combined_liquidity_adj_rarity=40,
        is_mock_or_stale=False,
    )
    assert plan.safe_buy_price_ton < 100


def test_stop_loss_not_above_safe_buy():
    safe = 100.0
    stop = calculate_stop_loss_price(safe, floor=90, quick_sell=88, volatility_score=20)
    assert stop <= safe


def test_buy_above_max_buy_weak_signal():
    sc, _ = detect_mispriced_rare_listing(
        250.0,
        trait_floor=200.0,
        trait_median_sale=220.0,
        collection_floor=180.0,
        trait_sales_n=4,
        listing_count_trait=3,
        important_score=10,
        liquidity=60.0,
    )
    assert sc < 95


def test_opportunity_score_mock_not_s_tier():
    est = FlipAnalysisResult(
        buy_zone_min_ton=1,
        buy_zone_max_ton=100,
        quick_sell_price_ton=50,
        fair_price_ton=70,
        list_price_ton=90,
        optimistic_price_ton=100,
        stop_price_ton=40,
        marketplace_fee_percent=5,
        expected_net_sale_ton=85,
        expected_profit_ton=20,
        expected_roi_percent=25,
        liquidity_score=70,
        risk_score=30,
        confidence_score=80,
        recommendation="BUY_FOR_FLIP",
        decision_type="BUY_IF_UNDER",
    )
    q = MarketDataQuality(sources_used=["mock"], is_mock_data=True)
    score = calculate_opportunity_score(
        est,
        q,
        {"label": "fresh", "has_recent_sales": True, "listing_price_ton": 80.0, "real_sales_count": 5},
    )
    assert score.final_rank_label != "S_TIER"


def test_format_reports_no_guarantee_language():
    p = CollectionMarketProfile(collection="Ice", collection_floor_ton=1.0, warnings=[])
    text = format_market_intelligence_report(p)
    assert "гарант" not in text.lower()


def test_rarity_fake_without_sales():
    tp = TraitMarketProfile(collection="X", trait_type="A", trait_value="B", trait_floor_ton=200, trait_recent_sales_count=0)
    attr = GiftAttributeSchema(trait_type="A", trait_value="B", rarity_percent=0.5)
    prof = calculate_trait_rarity_profile(attr, tp, 100.0, important_bonus=0)
    assert prof.is_fake_rarity or prof.is_rare_but_illiquid
