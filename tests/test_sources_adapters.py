import pytest

from app.config import Settings
from app.sources.getgems import GetGemsSource
from app.sources.tonnel import TonnelSource


class FakeHTTP:
    def __init__(self, payload):
        self.payload = payload

    async def get_json(self, url: str, headers=None, params=None):
        return self.payload


def _settings(**kwargs):
    payload = {
        "BOT_TOKEN": "x",
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
    }
    payload.update(kwargs)
    return Settings(**payload)


@pytest.mark.asyncio
async def test_source_without_base_url_does_not_fail():
    source = TonnelSource(_settings(TONNEL_BASE_URL=""))
    result = await source.get_collection_floor("Ice Cream")
    assert result is None


@pytest.mark.asyncio
async def test_source_invalid_response_returns_empty():
    source = GetGemsSource(_settings(GETGEMS_BASE_URL="https://api.getgems.io/public-api"), http_client=FakeHTTP(payload={"bad": "shape"}))
    floor = await source.get_collection_floor("EQ123")
    assert floor is None
