import pytest

from app.schemas.gift import GiftCard
from app.services.analyzer import AnalyzerService
from app.sources.mock import MockMarketSource


@pytest.mark.asyncio
async def test_analyzer_uses_actual_purchase_price_for_roi():
    svc = AnalyzerService(MockMarketSource())
    gift = GiftCard(collection="Ice Cream", number=217467)
    estimate = await svc.analyze_gift(gift, buy_price_ton=170)
    assert estimate.roi_based_on_estimated_buy_zone is False


@pytest.mark.asyncio
async def test_analyzer_estimated_roi_when_purchase_missing():
    svc = AnalyzerService(MockMarketSource())
    gift = GiftCard(collection="Ice Cream", number=217467)
    estimate = await svc.analyze_gift(gift, buy_price_ton=None)
    assert estimate.roi_based_on_estimated_buy_zone is True
