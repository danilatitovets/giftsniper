import json
from pathlib import Path

import pytest

from app.config import Settings
from app.schemas.gift import GiftCard
from app.services.analyzer import AnalyzerService
from app.sources.aggregator import MarketSourceAggregator
from app.sources.getgems import GetGemsSource
from app.sources.mock import MockMarketSource


class SequenceHTTP:
    def __init__(self, responses):
        self.responses = responses
        self.idx = -1

    async def get_json(self, url: str, headers=None, params=None):
        self.idx += 1
        return self.responses[self.idx]


def _settings(**kwargs):
    payload = {
        "BOT_TOKEN": "x",
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "ENABLE_MOCK_SOURCE": False,
        "GETGEMS_ENABLED": True,
        "GETGEMS_BASE_URL": "https://api.getgems.io/public-api",
        "GETGEMS_API_KEY": "DUMMY_KEY",
    }
    payload.update(kwargs)
    return Settings(**payload)


def _fixture(name: str):
    return json.loads((Path("tests/fixtures/getgems") / name).read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_missing_collection_address_returns_empty_not_crash():
    source = GetGemsSource(_settings(), http_client=SequenceHTTP([]), registry={"Ice Cream": {"aliases": [], "getgems": {"collection_address": ""}}})
    floor = await source.get_collection_floor("Ice Cream")
    assert floor is None
    assert any("missing" in w.lower() for w in source.last_quality.warnings)


@pytest.mark.asyncio
async def test_getgems_adapter_parses_floor_and_listings():
    registry = {"Ice Cream": {"aliases": ["ice cream"], "getgems": {"collection_address": "EQ_TEST_COLLECTION"}}}
    payload = _fixture("collection_on_sale.json")
    source = GetGemsSource(_settings(), http_client=SequenceHTTP([payload, payload]), registry=registry)
    floor = await source.get_collection_floor("Ice Cream")
    listings = await source.get_similar_listings("Ice Cream", [], limit=20)
    assert floor is not None
    assert floor.floor_ton == 198.0
    assert listings and listings[0].price_ton == 198.0


@pytest.mark.asyncio
async def test_trait_floor_none_when_attributes_unavailable():
    registry = {"Ice Cream": {"aliases": ["ice cream"], "getgems": {"collection_address": "EQ_TEST_COLLECTION"}}}
    payload = {"data": {"items": [{"id": "x", "price": 200, "index": 1}]}}
    source = GetGemsSource(_settings(), http_client=SequenceHTTP([payload]), registry=registry)
    trait_floor = await source.get_trait_floor("Ice Cream", "Symbol", "Moon")
    assert trait_floor is None


@pytest.mark.asyncio
async def test_analyzer_confidence_lower_on_partial_data():
    registry = {"Ice Cream": {"aliases": ["ice cream"], "getgems": {"collection_address": "EQ_TEST_COLLECTION"}}}
    payload = _fixture("collection_on_sale.json")
    partial_source = MarketSourceAggregator(
        [GetGemsSource(_settings(), http_client=SequenceHTTP([payload, payload, {"data": {"history": []}}]), registry=registry)],
        fallback_source=MockMarketSource(),
    )
    gift = GiftCard(collection="Ice Cream", number=217467)
    estimate = await AnalyzerService(partial_source).analyze_gift(gift, buy_price_ton=170)
    assert estimate.confidence_score < 80
