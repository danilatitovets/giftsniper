import pytest

from app.config import Settings
from app.services import gift_analysis_flow
from app.services.gift_intake import GiftIdentity, GiftInput, GiftInputType


def _settings():
    return Settings(
        BOT_TOKEN="x",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        COLLECTION_REGISTRY_PATH="data/collections.example.json",
    )


@pytest.mark.asyncio
async def test_run_gift_check_unknown(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "risk_mode": "normal"})()

    async def _resolve(*a, **k):
        gi = GiftInput(raw_text="x", input_type=GiftInputType.unknown)
        ident = GiftIdentity(
            collection="Unknown",
            number=None,
            nft_address=None,
            collection_address=None,
            normalized_collection="",
            canonical_key="",
        )
        return gi, ident

    monkeypatch.setattr(gift_analysis_flow, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(gift_analysis_flow, "UserRepository", _Users)
    monkeypatch.setattr(gift_analysis_flow, "resolve_gift_identity", _resolve)
    out = await gift_analysis_flow.run_gift_check(1, "u", "nonsense", _settings(), short=True)
    assert out.ok is False
    assert out.error and "не смог" in out.error.lower()
