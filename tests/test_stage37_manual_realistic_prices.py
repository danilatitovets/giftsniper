"""Stage 37 — manual floor keeps /deal in realistic band."""

from datetime import datetime, timezone

import pytest

from app.config import Settings
from app.schemas.gift import GiftCard
from app.schemas.market import ListingSchema, MarketFloor, SaleSchema
from app.services.analyzer import AnalyzerService
from app.sources.base import MarketSource


class _ManualOnly(MarketSource):
    name = "manualtest"

    async def get_collection_floor(self, collection: str):
        return MarketFloor(
            collection=collection,
            source="Manual",
            floor_ton=8.0,
            created_at=datetime.now(timezone.utc),
        )

    async def get_trait_floor(self, collection: str, trait_type: str, trait_value: str):
        return None

    async def get_recent_sales(self, collection: str, limit: int = 20):
        return [
            SaleSchema(
                external_id="m1",
                source="Manual",
                collection=collection,
                number=57234,
                price_ton=8.0,
                sold_at=datetime.now(timezone.utc),
            )
        ]

    async def get_similar_listings(self, collection: str, attributes, limit: int = 20):
        return [
            ListingSchema(
                external_id="l1",
                source="Manual",
                collection=collection,
                number=57234,
                price_ton=7.77,
                url="",
                created_at=datetime.now(timezone.utc),
            )
        ]

    async def search_underpriced(self, collection: str, filters: dict):
        return []


@pytest.mark.asyncio
async def test_manual_market_deal_prices_not_hundreds(monkeypatch):
    monkeypatch.setattr(
        "app.services.analyzer.get_settings",
        lambda: Settings(
            BOT_TOKEN="x",
            DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db",
            PRODUCTION_MODE=True,
            ALLOW_MOCK_IN_PRODUCTION=False,
            ENABLE_MOCK_SOURCE=False,
        ),
    )
    svc = AnalyzerService(_ManualOnly())
    est = await svc.analyze_gift(GiftCard(collection="Whip Cupcake", number=57234), buy_price_ton=7.77)
    assert est.pricing_suppressed is False
    assert est.fair_price_ton < 50
    assert est.buy_zone_max_ton < 50
    assert getattr(est, "price_source_label", None) in {"manual", "mixed", "real"}
