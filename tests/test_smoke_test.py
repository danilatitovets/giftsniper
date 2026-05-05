import pytest

from app.bot.handlers.admin import smoke_test_handler


class _Msg:
    text = "/smoke_test"
    from_user = type("U", (), {"id": 1, "username": "admin"})()

    def __init__(self):
        self.out = []
        self.bot = None

    async def answer(self, text, **kwargs):
        self.out.append(text)


class _Ctx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_smoke_test_formats_passed_failed(monkeypatch):
    async def _req(_):
        return type("A", (), {"id": 1, "role": "admin"})()

    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    class _Product:
        def __init__(self, _s):
            pass

        async def count_events(self):
            return 0

    class _Feedback:
        def __init__(self, _s):
            pass

        async def count_new(self):
            return 0

    class _Billing:
        def __init__(self, _s):
            pass

        async def list_billing_events(self, **_kwargs):
            return []

    class _Payments:
        def __init__(self, _s):
            pass

        async def list_by_status(self, *_args, **_kwargs):
            return []

    class _Alerts:
        def __init__(self, _s):
            pass

        async def count_incidents(self):
            return 0

    async def _home(_):
        return "ok"

    async def _ent(*_args, **_kwargs):
        return {}

    monkeypatch.setattr("app.bot.handlers.admin._require_admin", _req)
    monkeypatch.setattr("app.bot.handlers.admin.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.admin.UserRepository", _Users)
    monkeypatch.setattr("app.bot.handlers.admin.ProductEventRepository", _Product)
    monkeypatch.setattr("app.bot.handlers.admin.FeedbackRepository", _Feedback)
    monkeypatch.setattr("app.bot.handlers.admin.BillingRepository", _Billing)
    monkeypatch.setattr("app.bot.handlers.admin.ManualPaymentRepository", _Payments)
    monkeypatch.setattr("app.bot.handlers.admin.AlertRepository", _Alerts)
    monkeypatch.setattr("app.bot.handlers.admin._render_home", _home)
    monkeypatch.setattr("app.bot.handlers.admin.get_effective_entitlement", _ent)
    monkeypatch.setattr("app.bot.handlers.admin.create_market_source", lambda *_args, **_kwargs: object())
    msg = _Msg()
    await smoke_test_handler(msg)
    assert "Passed checks" in msg.out[0]
