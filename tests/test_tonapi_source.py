import logging

import pytest

from app.config import Settings
from app.sources.http import MarketSourceUnavailable
from app.sources.tonapi import TonApiSource


class FailingHTTP:
    async def get_json(self, url: str, headers=None, params=None):
        raise MarketSourceUnavailable("down")


def _settings(**kwargs):
    payload = {
        "BOT_TOKEN": "x",
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "TONAPI_ENABLED": True,
        "TONAPI_BASE_URL": "https://tonapi.io",
    }
    payload.update(kwargs)
    return Settings(**payload)


@pytest.mark.asyncio
async def test_tonapi_without_api_key_does_not_fail():
    source = TonApiSource(_settings(TONAPI_API_KEY=""))
    assert await source.get_collection_floor("Ice Cream") is None
    assert await source.get_similar_listings("Ice Cream", []) == []


@pytest.mark.asyncio
async def test_tonapi_does_not_provide_marketplace_data():
    source = TonApiSource(_settings(TONAPI_API_KEY="dummy"))
    assert await source.get_collection_floor("Ice Cream") is None
    assert await source.get_trait_floor("Ice Cream", "Symbol", "Moon") is None
    assert await source.search_underpriced("Ice Cream", {}) == []


@pytest.mark.asyncio
async def test_tonapi_invalid_response_safe_empty():
    source = TonApiSource(_settings(TONAPI_API_KEY="dummy"), http_client=FailingHTTP())
    assert await source.get_nft_by_address("EQ123") is None


@pytest.mark.asyncio
async def test_tonapi_no_secret_in_logs(caplog):
    source = TonApiSource(_settings(TONAPI_API_KEY="SECRET_TOKEN"), http_client=FailingHTTP())
    with caplog.at_level(logging.WARNING):
        _ = await source.get_nft_by_address("EQ123")
    text = "\n".join(x.message for x in caplog.records)
    assert "SECRET_TOKEN" not in text
