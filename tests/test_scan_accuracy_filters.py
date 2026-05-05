from app.config import get_settings
from app.schemas.analysis import FlipAnalysisResult
from app.bot.handlers.analysis import _passes_scan_filters


def _est(**kwargs):
    defaults = dict(
        buy_zone_min_ton=10,
        buy_zone_max_ton=100,
        quick_sell_price_ton=50,
        fair_price_ton=80,
        list_price_ton=90,
        optimistic_price_ton=95,
        stop_price_ton=45,
        marketplace_fee_percent=5,
        expected_net_sale_ton=85,
        expected_profit_ton=5,
        expected_roi_percent=15,
        liquidity_score=60,
        risk_score=40,
        confidence_score=70,
        recommendation="BUY_FOR_FLIP",
    )
    defaults.update(kwargs)
    return FlipAnalysisResult(**defaults)


def test_scan_rejects_strong_buy_without_sales():
    settings = get_settings()
    e = _est(decision_type="STRONG_BUY", expected_profit_ton=10, expected_roi_percent=20)
    assert not _passes_scan_filters(e, settings, "fresh", False, real_sales_count=1, listing_price_ton=50)


def test_scan_rejects_listing_above_max_buy():
    settings = get_settings()
    e = _est(decision_type="BUY_IF_UNDER", buy_zone_max_ton=80, expected_profit_ton=10, expected_roi_percent=20)
    assert not _passes_scan_filters(e, settings, "fresh", False, real_sales_count=5, listing_price_ton=100)


def test_scan_rejects_strong_buy_rare_no_trait_sales():
    settings = get_settings()
    e = _est(
        decision_type="STRONG_BUY",
        liquidity_adjusted_rarity_score=50,
        max_trait_recent_sales=0,
        expected_profit_ton=10,
        expected_roi_percent=20,
    )
    assert not _passes_scan_filters(e, settings, "fresh", False, real_sales_count=8, listing_price_ton=50)
