import pytest

from app.bot.middlewares import AccessControlMiddleware


class _Msg:
    def __init__(self):
        self.text = "/home"
        self.from_user = type("U", (), {"id": 111, "username": "beta"})()
        self.answers = []

    async def answer(self, text: str):
        self.answers.append(text)


class _Ctx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    def add(self, *_a, **_k) -> None:
        return None


async def _next(*_args, **_kwargs):
    return "ok"


@pytest.mark.asyncio
async def test_beta_gate_blocks_new_user_without_invite(monkeypatch):
    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "is_blocked": False, "role": "user", "plan": "free"})()

        async def get_or_create_with_created(self, *a, **k):
            u = await self.get_or_create(*a, **k)
            return u, False

        async def touch_activity(self, *_):
            return None

    class _Inv:
        def __init__(self, _s):
            pass

        async def has_user_redemption(self, *_):
            return False

    class _Billing:
        def __init__(self, _s):
            pass

        async def get_entitlement(self, *_):
            return None

    settings = type("S", (), {"beta_mode": True, "beta_require_invite": True, "beta_support_username": "@s", "rate_limit_commands_per_minute": 20, "rate_limit_heavy_commands_per_hour": 20})()
    monkeypatch.setattr("app.bot.middlewares.get_settings", lambda: settings)
    monkeypatch.setattr("app.bot.middlewares.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.middlewares.UserRepository", _Users)
    monkeypatch.setattr("app.bot.middlewares.BetaInviteRepository", _Inv)
    monkeypatch.setattr("app.bot.middlewares.BillingRepository", _Billing)
    middleware = AccessControlMiddleware()
    result = await middleware(_next, _Msg(), {})
    assert result is None


@pytest.mark.asyncio
async def test_owner_admin_tester_bypass_and_redeemed_invite(monkeypatch):
    class _Users:
        role = "owner"

        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "is_blocked": False, "role": self.role, "plan": "free"})()

        async def get_or_create_with_created(self, *a, **k):
            u = await self.get_or_create(*a, **k)
            return u, False

        async def touch_activity(self, *_):
            return None

    class _Inv:
        redeemed = False

        def __init__(self, _s):
            pass

        async def has_user_redemption(self, *_):
            return self.redeemed

    class _Billing:
        def __init__(self, _s):
            pass

        async def get_entitlement(self, *_):
            return None

    settings = type("S", (), {"beta_mode": True, "beta_require_invite": True, "beta_support_username": "@s", "rate_limit_commands_per_minute": 20, "rate_limit_heavy_commands_per_hour": 20})()
    monkeypatch.setattr("app.bot.middlewares.get_settings", lambda: settings)
    monkeypatch.setattr("app.bot.middlewares.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.middlewares.UserRepository", _Users)
    monkeypatch.setattr("app.bot.middlewares.BetaInviteRepository", _Inv)
    monkeypatch.setattr("app.bot.middlewares.BillingRepository", _Billing)
    middleware = AccessControlMiddleware()
    for role in ["owner", "admin", "tester"]:
        _Users.role = role
        result = await middleware(_next, _Msg(), {})
        assert result == "ok"
    _Users.role = "user"
    _Inv.redeemed = True
    result = await middleware(_next, _Msg(), {})
    assert result == "ok"
