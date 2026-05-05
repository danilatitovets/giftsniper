import pytest
from datetime import datetime, timedelta, timezone

from app.schemas.gift import GiftCard
from app.schemas.market import MarketDataQuality, MarketFloor, SaleSchema
from app.services.analyzer import AnalyzerService
from app.sources.base import MarketSource


class DummyManualSource(MarketSource):
    name = "Manual"

    def __init__(self, floor_age_minutes: int = 0, sales_age_minutes: int | None = None):
        self.floor_age_minutes = floor_age_minutes
        self.sales_age_minutes = sales_age_minutes

    async def get_collection_floor(self, collection: str):
        self.last_quality = MarketDataQuality(sources_used=["Manual"], warnings=["Используются ручные рыночные данные"])
        dt = datetime.now(timezone.utc) - timedelta(minutes=self.floor_age_minutes)
        return MarketFloor(collection=collection, source="Manual", floor_ton=186, created_at=dt)

    async def get_trait_floor(self, collection: str, trait_type: str, trait_value: str):
        self.last_quality = MarketDataQuality(sources_used=["Manual"], warnings=["Используются ручные рыночные данные"])
        return None

    async def get_recent_sales(self, collection: str, limit: int = 20):
        self.last_quality = MarketDataQuality(sources_used=["Manual"], warnings=["Используются ручные рыночные данные"])
        if self.sales_age_minutes is None:
            return []
        dt = datetime.now(timezone.utc) - timedelta(minutes=self.sales_age_minutes)
        return [SaleSchema(external_id="s1", source="Manual", collection=collection, number=1, price_ton=200, sold_at=dt)]

    async def get_similar_listings(self, collection: str, attributes, limit: int = 20):
        self.last_quality = MarketDataQuality(sources_used=["Manual"], warnings=["Используются ручные рыночные данные"])
        return []

    async def search_underpriced(self, collection: str, filters: dict):
        return []


@pytest.mark.asyncio
async def test_deal_calculates_profit_after_fee():
    estimate = await AnalyzerService(DummyManualSource()).analyze_gift(GiftCard(collection="Ice Cream", number=1), buy_price_ton=170)
    assert estimate.expected_net_sale_ton > 0
    assert estimate.expected_profit_ton != 0


@pytest.mark.asyncio
async def test_deal_not_buy_for_flip_if_low_roi():
    estimate = await AnalyzerService(DummyManualSource()).analyze_gift(GiftCard(collection="Ice Cream", number=1), buy_price_ton=400)
    assert estimate.recommendation != "BUY_FOR_FLIP"


@pytest.mark.asyncio
async def test_deal_warns_about_stale_data():
    estimate = await AnalyzerService(DummyManualSource(floor_age_minutes=900)).analyze_gift(
        GiftCard(collection="Ice Cream", number=1), buy_price_ton=170
    )
    assert any("Floor устарел" in r for r in estimate.reasons)


@pytest.mark.asyncio
async def test_old_data_blocks_buy_for_flip():
    estimate = await AnalyzerService(DummyManualSource(floor_age_minutes=2000, sales_age_minutes=20000)).analyze_gift(
        GiftCard(collection="Ice Cream", number=1), buy_price_ton=120
    )
    assert estimate.recommendation != "BUY_FOR_FLIP"
