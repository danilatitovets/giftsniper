import pytest

from app.config import Settings
from app.services.gift_intake import build_canonical_gift_key
from app.services.gift_resolver import resolve_from_collection_number, resolve_gift_identity


def _settings() -> Settings:
    return Settings(
        BOT_TOKEN="x",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        COLLECTION_REGISTRY_PATH="data/collections.example.json",
    )


@pytest.mark.asyncio
async def test_resolver_collection_number():
    settings = _settings()
    ident = await resolve_from_collection_number(settings, "ice cream", 5)
    assert ident.collection == "Ice Cream"
    assert ident.number == 5
    assert "ice_cream#5" in ident.canonical_key or ident.canonical_key.endswith("#5")


@pytest.mark.asyncio
async def test_resolve_gift_identity_uses_registry():
    class U:
        id = 1

    settings = _settings()
    _, ident = await resolve_gift_identity(U(), "Ice Cream #10", settings)
    assert ident.collection == "Ice Cream"
    assert ident.number == 10


def test_canonical_key_addr():
    k = build_canonical_gift_key(collection=None, number=None, nft_address="EQx", normalized_collection="")
    assert k.startswith("addr:EQx")
