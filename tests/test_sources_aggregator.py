from datetime import datetime, timezone

import pytest

from app.config import Settings
from app.schemas.gift import GiftCard
from app.schemas.market import ListingSchema, MarketFloor, SaleSchema
from app.services.analyzer import AnalyzerService
from app.sources.aggregator import MarketSourceAggregator
from app.sources.base import MarketSource
from app.sources.factory import create_market_source
from app.sources.mock import MockMarketSource


class FailingSource(MarketSource):
    name = "failing"

    async def get_collection_floor(self, collection: str):
        raise RuntimeError("boom")

    async def get_trait_floor(self, collection: str, trait_type: str, trait_value: str):
        raise RuntimeError("boom")

    async def get_recent_sales(self, collection: str, limit: int = 20):
        raise RuntimeError("boom")

    async def get_similar_listings(self, collection: str, attributes, limit: int = 20):
        raise RuntimeError("boom")

    async def search_underpriced(self, collection: str, filters: dict):
        raise RuntimeError("boom")


class ListingsSource(MarketSource):
    name = "listings"

    async def get_collection_floor(self, collection: str):
        return MarketFloor(collection=collection, source=self.name, floor_ton=200)

    async def get_trait_floor(self, collection: str, trait_type: str, trait_value: str):
        return None

    async def get_recent_sales(self, collection: str, limit: int = 20):
        return [
            SaleSchema(
                external_id="s1",
                source=self.name,
                collection=collection,
                number=1,
                price_ton=200,
                sold_at=datetime.now(timezone.utc),
            )
        ]

    async def get_similar_listings(self, collection: str, attributes, limit: int = 20):
        return [
            ListingSchema(
                external_id="x1",
                source="mock",
                collection=collection,
                number=1,
                price_ton=250,
                url="u1",
            ),
            ListingSchema(
                external_id="x1",
                source="mock",
                collection=collection,
                number=1,
                price_ton=250,
                url="u1",
            ),
            ListingSchema(
                external_id="x2",
                source="mock",
                collection=collection,
                number=2,
                price_ton=220,
                url="u2",
            ),
        ]

    async def search_underpriced(self, collection: str, filters: dict):
        return []


@pytest.mark.asyncio
async def test_aggregator_returns_floor_from_mock():
    agg = MarketSourceAggregator([MockMarketSource()], fallback_source=MockMarketSource())
    floor = await agg.get_collection_floor("Ice Cream")
    assert floor is not None
    assert floor.floor_ton == 186.0


@pytest.mark.asyncio
async def test_aggregator_handles_failing_source():
    agg = MarketSourceAggregator([FailingSource(), MockMarketSource()], fallback_source=MockMarketSource())
    floor = await agg.get_collection_floor("Ice Cream")
    assert floor is not None
    assert "failing" in agg.last_quality.sources_failed


@pytest.mark.asyncio
async def test_aggregator_deduplicates_and_sorts_listings():
    agg = MarketSourceAggregator([ListingsSource()], fallback_source=None)
    items = await agg.get_similar_listings("Ice Cream", [], limit=20)
    assert len(items) == 2
    assert items[0].price_ton <= items[1].price_ton


@pytest.mark.asyncio
async def test_aggregator_adds_warning_on_mock_fallback():
    agg = MarketSourceAggregator([FailingSource()], fallback_source=MockMarketSource())
    _ = await agg.get_collection_floor("Ice Cream")
    assert any("mock" in w.lower() for w in agg.last_quality.warnings)


def test_create_market_source_enable_mock_true():
    settings = Settings(
        BOT_TOKEN="x",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db",
        ENABLE_MOCK_SOURCE=True,
    )
    source = create_market_source(settings)
    assert isinstance(source, MarketSourceAggregator)
    assert source.sources[0].name == "mock"


@pytest.mark.asyncio
async def test_data_quality_reduces_confidence_in_analyzer():
    gift = GiftCard(collection="Ice Cream", number=217467)
    raw = await AnalyzerService(MockMarketSource()).analyze_gift(gift, buy_price_ton=170)
    agg = await AnalyzerService(MarketSourceAggregator([MockMarketSource()], fallback_source=MockMarketSource())).analyze_gift(
        gift, buy_price_ton=170
    )
    assert agg.confidence_score < raw.confidence_score
