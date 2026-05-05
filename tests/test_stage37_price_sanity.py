"""Stage 37 — price sanity caps."""

from app.config import Settings
from app.schemas.analysis import FlipAnalysisResult
from app.services.price_sanity import apply_price_sanity_caps, detect_unrealistic_price_gap


def test_detect_unrealistic_gap():
    assert detect_unrealistic_price_gap(
        anchor_ton=8.0,
        fair_ton=120.0,
        floor_ton=8.0,
        sales_count=0,
        source_is_mock=False,
    ) is True


def test_apply_caps_unknown_collection():
    s = Settings(BOT_TOKEN="x", DATABASE_URL="postgresql+asyncpg://u:p@localhost/db")
    r = FlipAnalysisResult(
        buy_zone_min_ton=1,
        buy_zone_max_ton=200,
        quick_sell_price_ton=1,
        fair_price_ton=180,
        list_price_ton=200,
        optimistic_price_ton=220,
        stop_price_ton=1,
        marketplace_fee_percent=5,
        expected_net_sale_ton=100,
        expected_profit_ton=0,
        expected_roi_percent=0,
        liquidity_score=40,
        risk_score=40,
        confidence_score=50,
        recommendation="HOLD",
    )
    out = apply_price_sanity_caps(
        r,
        listing_hint_ton=None,
        floor_ton=None,
        sales_count=0,
        max_trait_sales=0,
        collection_known=False,
    )
    assert out.fair_price_ton <= 35
