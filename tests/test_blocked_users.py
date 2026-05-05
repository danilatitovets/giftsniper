import pytest

from app.bot.middlewares import AccessControlMiddleware


class _Msg:
    def __init__(self):
        self.text = "/scan"
        self.from_user = type("U", (), {"id": 123, "username": "x"})()
        self.answers = []

    async def answer(self, text: str):
        self.answers.append(text)


async def _handler(_event, _data):
    return "ok"


@pytest.mark.asyncio
async def test_blocked_user_cannot_run_commands(monkeypatch):
    msg = _Msg()
    called = {"next": False}

    class _FakeCtx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.bot.middlewares.SessionLocal", lambda: _FakeCtx())

    class _Repo:
        def __init__(self, _session):
            pass

        async def get_or_create(self, _tg, _username):
            return type("U", (), {"id": 1, "is_blocked": True})()

        async def get_or_create_with_created(self, tg, username):
            u = await self.get_or_create(tg, username)
            return u, False

    monkeypatch.setattr("app.bot.middlewares.UserRepository", _Repo)
    middleware = AccessControlMiddleware()

    async def _next(event, data):
        called["next"] = True
        return await _handler(event, data)

    result = await middleware(_next, msg, {})
    assert result is None
    assert called["next"] is False
    assert msg.answers
    assert "ограничен" in msg.answers[0].lower()
