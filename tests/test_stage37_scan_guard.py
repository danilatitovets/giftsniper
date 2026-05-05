"""Stage 37 — mock listings stripped in production scan prep."""

from app.config import Settings
from app.schemas.market import ListingSchema
from app.services.market_data_validity import filter_mock_listings_for_production


def test_filter_mock_listings_production():
    s = Settings(
        BOT_TOKEN="x",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        PRODUCTION_MODE=True,
        ALLOW_MOCK_IN_PRODUCTION=False,
        BLOCK_TRADING_VERDICT_ON_MOCK=True,
    )
    rows = [
        ListingSchema(external_id="1", source="mock", collection="X", number=1, price_ton=5, url=""),
        ListingSchema(external_id="2", source="Manual", collection="X", number=2, price_ton=6, url=""),
    ]
    out = filter_mock_listings_for_production(s, rows)
    assert len(out) == 1
    assert out[0].source.lower() == "manual"
