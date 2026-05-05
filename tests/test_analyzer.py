import pytest

from app.schemas.gift import GiftAttributeSchema, GiftCard
from app.services.analyzer import AnalyzerService
from app.sources.mock import MockMarketSource


@pytest.mark.asyncio
async def test_analyzer_with_mock_source():
    service = AnalyzerService(MockMarketSource())
    gift = GiftCard(
        collection="Ice Cream",
        number=217467,
        attributes=[
            GiftAttributeSchema(trait_type="Symbol", trait_value="Moon", rarity_percent=0.7),
        ],
    )
    estimate = await service.analyze_gift(gift, risk_mode="normal", buy_price_ton=170)
    assert estimate.fair_price_ton > 0
    assert estimate.confidence_score >= 25
    assert estimate.expected_net_sale_ton > 0
    assert isinstance(estimate.reasons, list)
