from app.config import get_settings
from app.schemas.market_brain import CollectionMarketProfile
from app.services.market_intelligence import build_trait_market_profile


def test_trait_premium_confirmed_only_with_sales():
    settings = get_settings()
    coll = CollectionMarketProfile(
        collection="C",
        collection_floor_ton=100,
        liquidity_score=60,
        recent_sales_count=5,
    )
    listings = []
    sales = []

    # No trait-matching sales/listings → premium not confirmed by trades
    tp = build_trait_market_profile(
        "C",
        "Backdrop",
        "Monochrome",
        250.0,
        coll,
        [],
        [],
        None,
        settings,
    )
    assert tp.trait_premium_confirmed is False
    assert tp.trait_recent_sales_count == 0
