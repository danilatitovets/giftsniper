import pytest

from app.bot.handlers import gifts as gifts_handlers


class _Msg:
    def __init__(self, text: str):
        self.text = text
        self.from_user = type("U", (), {"id": 1, "username": "u"})()
        self.out: list[str] = []

    async def answer(self, text: str, **kwargs):
        self.out.append(text)


@pytest.mark.asyncio
async def test_add_duplicate_updates(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free", "role": "user", "is_blocked": False})()

    class _G:
        id = 1
        collection = "Ice Cream"
        number = 9

    class _GR:
        def __init__(self, _s):
            pass

        async def get_by_canonical_key(self, *a):
            return _G()

        async def get_by_nft_address(self, *a):
            return None

        async def get_by_collection_number(self, *a):
            return None

        async def count_by_user(self, *a):
            return 0

        async def add_or_update_gift_from_identity(self, *a, **kw):
            return _G(), "updated"

    monkeypatch.setattr(gifts_handlers, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(gifts_handlers, "UserRepository", _UR)
    monkeypatch.setattr(gifts_handlers, "GiftRepository", _GR)

    msg = _Msg("/add Ice Cream #9")
    await gifts_handlers.add_gift_handler(msg)
    assert "обновил" in msg.out[0].lower() or "уже" in msg.out[0].lower()
