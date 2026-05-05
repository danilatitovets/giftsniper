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
async def test_import_respects_plan_limit(monkeypatch):
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

    class _GR:
        def __init__(self, _s):
            pass

        async def get_by_canonical_key(self, *a):
            return None

        async def get_by_nft_address(self, *a):
            return None

        async def get_by_collection_number(self, *a):
            return None

        async def count_by_user(self, *a):
            return 99

        async def add_or_update_gift_from_identity(self, *a, **kw):
            raise AssertionError("should not create over limit")

    monkeypatch.setattr(gifts_handlers, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(gifts_handlers, "UserRepository", _UR)
    monkeypatch.setattr(gifts_handlers, "GiftRepository", _GR)

    msg = _Msg("/import_gifts\nIce Cream #1")
    await gifts_handlers.import_gifts_handler(msg)
    assert "Пропущено" in msg.out[0] or "лимит" in msg.out[0].lower()
