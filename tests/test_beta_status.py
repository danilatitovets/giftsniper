import pytest

from app.bot.handlers.admin import admin_beta_status_handler


class _Ctx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Msg:
    text = "/admin_beta_status"
    from_user = type("U", (), {"id": 1, "username": "a"})()

    def __init__(self):
        self.out = []

    async def answer(self, text, **kwargs):
        self.out.append(text)


@pytest.mark.asyncio
async def test_admin_beta_status_counts(monkeypatch):
    async def _req(_):
        return type("A", (), {"id": 1, "role": "admin"})()

    class _Users:
        def __init__(self, _s):
            pass

        async def count_all(self):
            return 10

        async def plans_breakdown(self):
            return {"pro": 2, "trader": 1}

    class _Invites:
        def __init__(self, _s):
            pass

        async def count_active(self):
            return 3

        async def count_redemptions(self):
            return 7

    class _Feedback:
        def __init__(self, _s):
            pass

        async def count_new(self):
            return 4

    class _Payments:
        def __init__(self, _s):
            pass

        async def list_by_status(self, *_args, **_kwargs):
            return [1, 2]

    async def _stale(_s):
        return [1]

    monkeypatch.setattr("app.bot.handlers.admin._require_admin", _req)
    monkeypatch.setattr("app.bot.handlers.admin.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.admin.UserRepository", _Users)
    monkeypatch.setattr("app.bot.handlers.admin.BetaInviteRepository", _Invites)
    monkeypatch.setattr("app.bot.handlers.admin.FeedbackRepository", _Feedback)
    monkeypatch.setattr("app.bot.handlers.admin.ManualPaymentRepository", _Payments)
    monkeypatch.setattr("app.bot.handlers.admin.list_stale_submitted_requests", _stale)
    monkeypatch.setattr("app.bot.handlers.admin.get_settings", lambda: type("S", (), {"manual_payment_submitted_sla_hours": 6})())
    msg = _Msg()
    await admin_beta_status_handler(msg)
    assert "total users: 10" in msg.out[0]
    assert "invites redeemed: 7" in msg.out[0]
