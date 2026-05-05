"""Stage 37 — production must not price on mock-only."""

import pytest

from app.config import Settings
from app.schemas.gift import GiftCard
from app.schemas.market import MarketDataQuality
from app.services.analyzer import AnalyzerService
from app.services.market_data_validity import evaluate_market_data_validity
from app.sources.mock import MockMarketSource


def _prod_settings(**kw):
    base = dict(
        BOT_TOKEN="x",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db",
        PRODUCTION_MODE=True,
        ALLOW_MOCK_IN_PRODUCTION=False,
        BLOCK_TRADING_VERDICT_ON_MOCK=True,
        REQUIRE_REAL_OR_MANUAL_FOR_TRADING=True,
        MOCK_ALLOWED_FOR_DEV=True,
    )
    base.update(kw)
    return Settings(**base)


@pytest.mark.asyncio
async def test_production_mock_only_pricing_suppressed(monkeypatch):
    monkeypatch.setattr("app.services.analyzer.get_settings", lambda: _prod_settings())
    svc = AnalyzerService(MockMarketSource())
    est = await svc.analyze_gift(GiftCard(collection="UnknownGiftX", number=1), buy_price_ton=None)
    assert est.pricing_suppressed is True
    assert est.fair_price_ton == 0
    assert est.decision_type == "NEED_MORE_DATA"


def test_validity_mock_only_production():
    s = _prod_settings()
    q = MarketDataQuality(sources_used=["mock"], is_mock_data=True)
    v = evaluate_market_data_validity(
        settings=s,
        quality=q,
        stats={"real_floor": False, "manual_floor": False},
        has_floor=False,
        listings_count=0,
        sales_count=0,
        max_trait_sales=0,
    )
    assert v.pricing_allowed is False
    assert "mock" in v.reason_code or v.reason_code == "mock_blocked_production"
