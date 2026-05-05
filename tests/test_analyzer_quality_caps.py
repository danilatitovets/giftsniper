import pytest
from datetime import datetime, timedelta, timezone

from app.schemas.gift import GiftCard
from app.schemas.market import ListingSchema, MarketFloor, SaleSchema
from app.services.analyzer import AnalyzerService
from app.sources.aggregator import MarketSourceAggregator
from app.sources.base import MarketSource
from app.sources.getgems import GetGemsSource
from app.sources.mock import MockMarketSource
from app.config import Settings


class SequenceHTTP:
    def __init__(self, responses):
        self.responses = responses
        self.idx = -1

    async def get_json(self, url: str, headers=None, params=None):
        self.idx += 1
        return self.responses[self.idx]


def _settings():
    return Settings(
        BOT_TOKEN="x",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db",
        ENABLE_MOCK_SOURCE=False,
        GETGEMS_ENABLED=True,
        GETGEMS_BASE_URL="https://api.getgems.io/public-api",
    )


@pytest.mark.asyncio
async def test_mock_confidence_cap():
    estimate = await AnalyzerService(MockMarketSource()).analyze_gift(GiftCard(collection="Ice Cream", number=1), buy_price_ton=170)
    assert estimate.confidence_score <= 60


@pytest.mark.asyncio
async def test_real_floor_only_confidence_cap():
    registry = {"Ice Cream": {"aliases": ["ice cream"], "getgems": {"collection_address": "EQ_TEST"}}}
    on_sale = {"data": {"items": [{"id": "1", "price": 200, "index": 1}]}}
    history_empty = {"data": {"history": []}}
    source = MarketSourceAggregator(
        [GetGemsSource(_settings(), http_client=SequenceHTTP([on_sale, history_empty, on_sale]), registry=registry)],
        fallback_source=MockMarketSource(),
    )
    estimate = await AnalyzerService(source).analyze_gift(GiftCard(collection="Ice Cream", number=1), buy_price_ton=170)
    assert estimate.confidence_score <= 75


@pytest.mark.asyncio
async def test_buy_for_flip_not_high_confidence_without_sales():
    registry = {"Ice Cream": {"aliases": ["ice cream"], "getgems": {"collection_address": "EQ_TEST"}}}
    on_sale = {"data": {"items": [{"id": "1", "price": 220, "index": 1}, {"id": "2", "price": 260, "index": 2}]}}
    history_empty = {"data": {"history": []}}
    source = MarketSourceAggregator(
        [GetGemsSource(_settings(), http_client=SequenceHTTP([on_sale, history_empty, on_sale]), registry=registry)],
        fallback_source=MockMarketSource(),
    )
    estimate = await AnalyzerService(source).analyze_gift(GiftCard(collection="Ice Cream", number=1), buy_price_ton=150)
    if estimate.recommendation == "BUY_FOR_FLIP":
        assert estimate.confidence_score <= 75


class SalesAgeSource(MarketSource):
    name = "Manual"

    def __init__(self, sales_days: int):
        self.sales_days = sales_days

    async def get_collection_floor(self, collection: str):
        return MarketFloor(collection=collection, source="Manual", floor_ton=186, created_at=datetime.now(timezone.utc))

    async def get_trait_floor(self, collection: str, trait_type: str, trait_value: str):
        return None

    async def get_recent_sales(self, collection: str, limit: int = 20):
        dt = datetime.now(timezone.utc) - timedelta(days=self.sales_days)
        return [SaleSchema(external_id="s1", source="Manual", collection=collection, number=1, price_ton=200, sold_at=dt)]

    async def get_similar_listings(self, collection: str, attributes, limit: int = 20):
        return [
            ListingSchema(
                external_id="l1",
                source="Manual",
                collection=collection,
                number=1,
                price_ton=180,
                url="",
                created_at=datetime.now(timezone.utc),
            )
        ]

    async def search_underpriced(self, collection: str, filters: dict):
        return []


@pytest.mark.asyncio
async def test_recent_sales_within_7_days_improves_confidence():
    fresh = await AnalyzerService(SalesAgeSource(sales_days=2)).analyze_gift(GiftCard(collection="Ice Cream", number=1), buy_price_ton=170)
    old = await AnalyzerService(SalesAgeSource(sales_days=10)).analyze_gift(GiftCard(collection="Ice Cream", number=1), buy_price_ton=170)
    assert fresh.confidence_score >= old.confidence_score


@pytest.mark.asyncio
async def test_sales_older_than_7_days_lowers_confidence():
    estimate = await AnalyzerService(SalesAgeSource(sales_days=10)).analyze_gift(GiftCard(collection="Ice Cream", number=1), buy_price_ton=170)
    assert any("старше 7 дней" in r for r in estimate.reasons)
