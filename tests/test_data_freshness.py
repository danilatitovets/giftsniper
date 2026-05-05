from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.gift import GiftCard
from app.schemas.market import ListingSchema, MarketDataQuality, MarketFloor, SaleSchema
from app.services.analyzer import AnalyzerService
from app.sources.aggregator import MarketSourceAggregator
from app.sources.base import MarketSource
from app.sources.mock import MockMarketSource


class FreshnessSource(MarketSource):
    name = "Manual"

    def __init__(self, floor_age_minutes: int, sales_age_minutes: int | None = None):
        self.floor_age_minutes = floor_age_minutes
        self.sales_age_minutes = sales_age_minutes
        self.last_quality = MarketDataQuality(sources_used=["Manual"])

    async def get_collection_floor(self, collection: str):
        dt = datetime.now(timezone.utc) - timedelta(minutes=self.floor_age_minutes)
        return MarketFloor(collection=collection, source="Manual", floor_ton=186, created_at=dt)

    async def get_trait_floor(self, collection: str, trait_type: str, trait_value: str):
        return None

    async def get_recent_sales(self, collection: str, limit: int = 20):
        if self.sales_age_minutes is None:
            return []
        dt = datetime.now(timezone.utc) - timedelta(minutes=self.sales_age_minutes)
        return [
            SaleSchema(
                external_id="s1",
                source="Manual",
                collection=collection,
                number=1,
                price_ton=200,
                sold_at=dt,
            )
        ]

    async def get_similar_listings(self, collection: str, attributes, limit: int = 20):
        dt = datetime.now(timezone.utc) - timedelta(minutes=self.floor_age_minutes)
        return [
            ListingSchema(
                external_id="l1",
                source="Manual",
                collection=collection,
                number=1,
                price_ton=180,
                url="",
                created_at=dt,
            )
        ]

    async def search_underpriced(self, collection: str, filters: dict):
        return []


@pytest.mark.asyncio
async def test_fresh_floor_no_penalty():
    estimate = await AnalyzerService(FreshnessSource(floor_age_minutes=20, sales_age_minutes=60)).analyze_gift(
        GiftCard(collection="Ice Cream", number=1),
        buy_price_ton=170,
    )
    assert estimate.confidence_score >= 40


@pytest.mark.asyncio
async def test_stale_floor_adds_penalty():
    estimate = await AnalyzerService(FreshnessSource(floor_age_minutes=240, sales_age_minutes=120)).analyze_gift(
        GiftCard(collection="Ice Cream", number=1),
        buy_price_ton=170,
    )
    assert any("Floor устарел" in r for r in estimate.reasons)


@pytest.mark.asyncio
async def test_old_floor_caps_confidence():
    estimate = await AnalyzerService(FreshnessSource(floor_age_minutes=1600, sales_age_minutes=60)).analyze_gift(
        GiftCard(collection="Ice Cream", number=1),
        buy_price_ton=170,
    )
    assert estimate.confidence_score <= 55


class FloorSource(MarketSource):
    def __init__(self, name: str, floor: float, age_minutes: int):
        self.name = name
        self.floor = floor
        self.age_minutes = age_minutes

    async def get_collection_floor(self, collection: str):
        dt = datetime.now(timezone.utc) - timedelta(minutes=self.age_minutes)
        return MarketFloor(collection=collection, source=self.name, floor_ton=self.floor, created_at=dt)

    async def get_trait_floor(self, collection: str, trait_type: str, trait_value: str):
        return None

    async def get_recent_sales(self, collection: str, limit: int = 20):
        return []

    async def get_similar_listings(self, collection: str, attributes, limit: int = 20):
        return []

    async def search_underpriced(self, collection: str, filters: dict):
        return []


@pytest.mark.asyncio
async def test_manual_fresh_beats_mock():
    agg = MarketSourceAggregator(
        sources=[FloorSource("Manual", 190, 10)],
        fallback_source=MockMarketSource(),
    )
    floor = await agg.get_collection_floor("Ice Cream")
    assert floor is not None
    assert floor.source == "Manual"


@pytest.mark.asyncio
async def test_manual_old_does_not_beat_real_fresh():
    agg = MarketSourceAggregator(
        sources=[FloorSource("Manual", 170, 2000), FloorSource("Getgems", 185, 10)],
        fallback_source=MockMarketSource(),
    )
    floor = await agg.get_collection_floor("Ice Cream")
    assert floor is not None
    assert floor.source == "Getgems"
