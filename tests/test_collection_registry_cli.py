import pytest

from app.config import Settings
from scripts.check_collection_registry import inspect_registry


@pytest.mark.asyncio
async def test_registry_missing_address_does_not_crash():
    settings = Settings(
        BOT_TOKEN="x",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db",
        COLLECTION_REGISTRY_PATH="data/collections.example.json",
        ENABLE_MOCK_SOURCE=True,
    )
    lines = await inspect_registry(settings)
    assert any("Ice Cream" in line for line in lines)
