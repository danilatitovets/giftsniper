import pytest

from app.bot.middlewares import AccessControlMiddleware


class _Msg:
    def __init__(self, text: str):
        self.text = text
        self.from_user = type("U", (), {"id": 100, "username": "beta"})()
        self.answers = []

    async def answer(self, text: str):
        self.answers.append(text)


@pytest.mark.asyncio
async def test_command_updates_activity_and_product_event(monkeypatch):
    touched = {"count": 0, "events": 0}

    class _Ctx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "is_blocked": False})()

        async def get_or_create_with_created(self, *a, **k):
            u = await self.get_or_create(*a, **k)
            return u, False

        async def touch_activity(self, *_):
            touched["count"] += 1

    class _Events:
        def __init__(self, _s):
            pass

        async def create_event(self, **kwargs):
            assert kwargs["event_type"] == "start"
            touched["events"] += 1

    async def _sync(*_args, **_kwargs):
        return {}

    settings = type("S", (), {"beta_mode": False, "beta_require_invite": False, "rate_limit_commands_per_minute": 20, "rate_limit_heavy_commands_per_hour": 20})()
    monkeypatch.setattr("app.bot.middlewares.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.middlewares.get_settings", lambda: settings)
    monkeypatch.setattr("app.bot.middlewares.UserRepository", _Users)
    monkeypatch.setattr("app.bot.middlewares.ProductEventRepository", _Events)
    monkeypatch.setattr("app.bot.middlewares.sync_user_plan_from_entitlement", _sync)
    middleware = AccessControlMiddleware()

    async def _next(_event, _data):
        return "ok"

    result = await middleware(_next, _Msg("/start"), {})
    assert result == "ok"
    assert touched["count"] == 1
    assert touched["events"] == 1
