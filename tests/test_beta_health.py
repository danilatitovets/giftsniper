import pytest

from app.bot.handlers.admin import admin_beta_health_handler


class _Msg:
    text = "/admin_beta_health"
    from_user = type("U", (), {"id": 1, "username": "admin"})()

    def __init__(self):
        self.out = []

    async def answer(self, text, **kwargs):
        self.out.append(text)


class _Ctx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_beta_health_detects_low_activation_and_stale(monkeypatch):
    async def _req(_):
        return type("A", (), {"id": 1, "role": "admin"})()

    async def _act(*_args, **_kwargs):
        return {"activation_rate": 0.2, "active_users": 5}

    async def _ops(*_args, **_kwargs):
        return {"stale_submitted_48h": 4}

    class _Feedback:
        def __init__(self, _s):
            pass

        async def calculate_sla_metrics(self):
            return {"overdue_feedback_48h": 2}

    class _Alerts:
        def __init__(self, _s):
            pass

        async def count_incidents(self):
            return 2

    monkeypatch.setattr("app.bot.handlers.admin._require_admin", _req)
    monkeypatch.setattr("app.bot.handlers.admin.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.admin.calculate_activation_metrics", _act)
    monkeypatch.setattr("app.bot.handlers.admin.calculate_payment_ops_metrics", _ops)
    monkeypatch.setattr("app.bot.handlers.admin.FeedbackRepository", _Feedback)
    monkeypatch.setattr("app.bot.handlers.admin.AlertRepository", _Alerts)
    msg = _Msg()
    await admin_beta_health_handler(msg)
    assert "Beta Health" in msg.out[0]
    assert "Activation rate below 30%" in msg.out[0]
