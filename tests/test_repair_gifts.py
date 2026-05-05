import pytest

from app.bot.handlers import gifts as gifts_handlers


class _Msg:
    def __init__(self):
        self.text = "/repair_gifts"
        self.from_user = type("U", (), {"id": 1, "username": "u"})()
        self.out: list[str] = []

    async def answer(self, text: str, **kwargs):
        self.out.append(text)


@pytest.mark.asyncio
async def test_repair_fills_summary(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1})()

    class _Gift:
        id = 1
        collection = "Ice Cream"
        number = 1
        nft_address = None
        collection_address = None
        normalized_collection = None
        canonical_key = None
        source_url = None
        marketplace = None
        identity_confidence = None

    class _GR:
        def __init__(self, _s):
            pass

        async def list_by_user(self, *a):
            return [_Gift()]

        async def update_gift_identity(self, *a, **kw):
            return _Gift()

        async def list_duplicates(self, *a):
            return {}

    monkeypatch.setattr(gifts_handlers, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(gifts_handlers, "UserRepository", _UR)
    monkeypatch.setattr(gifts_handlers, "GiftRepository", _GR)

    msg = _Msg()
    await gifts_handlers.repair_gifts_handler(msg)
    assert "Repair gifts" in msg.out[0]
