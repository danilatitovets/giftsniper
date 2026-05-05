from datetime import datetime, timedelta, timezone

import pytest

from app.db.repositories.beta_invites import BetaInviteRepository
from app.bot.handlers.admin import redeem_handler


@pytest.mark.asyncio
async def test_invite_max_uses_enforced():
    repo = BetaInviteRepository(None)  # type: ignore[arg-type]
    invite = type("I", (), {"id": 1, "is_active": True, "expires_at": None, "used_count": 2, "max_uses": 2})()
    ok, reason = await repo.can_redeem(invite, 1)
    assert ok is False
    assert "исчерпан" in reason


@pytest.mark.asyncio
async def test_expired_or_disabled_invite_rejected():
    repo = BetaInviteRepository(None)  # type: ignore[arg-type]
    disabled = type("I", (), {"id": 1, "is_active": False, "expires_at": None, "used_count": 0, "max_uses": 1})()
    ok1, _ = await repo.can_redeem(disabled, 1)
    assert ok1 is False
    expired = type(
        "I",
        (),
        {"id": 1, "is_active": True, "expires_at": datetime.now(timezone.utc) - timedelta(days=1), "used_count": 0, "max_uses": 1},
    )()
    ok2, _ = await repo.can_redeem(expired, 1)
    assert ok2 is False


@pytest.mark.asyncio
async def test_redeem_invite_grants_entitlement(monkeypatch):
    class _Msg:
        text = "/redeem beta100"
        from_user = type("U", (), {"id": 11, "username": "x"})()
        out = []

        async def answer(self, text, **kwargs):
            self.out.append(text)

    class _Ctx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    called = {"grant": 0}

    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 2})()

    class _Invites:
        def __init__(self, _s):
            pass

        async def get_by_code(self, _c):
            return type("I", (), {"id": 1, "code": "beta100", "plan": "pro", "days": 14})()

        async def can_redeem(self, *_):
            return True, None

        async def redeem(self, *_):
            return object()

    class _Billing:
        def __init__(self, _s):
            pass

        async def create_billing_event(self, **kwargs):
            return kwargs

    async def _grant(*args, **kwargs):
        called["grant"] += 1

    async def _audit(*args, **kwargs):
        return None

    async def _sync(*args, **kwargs):
        return {}

    monkeypatch.setattr("app.bot.handlers.admin.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.admin.UserRepository", _Users)
    monkeypatch.setattr("app.bot.handlers.admin.BetaInviteRepository", _Invites)
    monkeypatch.setattr("app.bot.handlers.admin.BillingRepository", _Billing)
    monkeypatch.setattr("app.bot.handlers.admin.grant_entitlement", _grant)
    monkeypatch.setattr("app.bot.handlers.admin.log_audit", _audit)
    monkeypatch.setattr("app.bot.handlers.admin.sync_user_plan_from_entitlement", _sync)
    msg = _Msg()
    await redeem_handler(msg)
    assert called["grant"] == 1
