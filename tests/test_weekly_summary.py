import pytest

from app.bot.handlers.admin import admin_weekly_summary_handler


class _Msg:
    text = "/admin_weekly_summary"
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
async def test_weekly_summary_formats_sections(monkeypatch):
    async def _req(_):
        return type("A", (), {"id": 1, "role": "admin"})()

    async def _act(*_args, **_kwargs):
        return {"period_days": 7, "new_users": 4, "active_users": 3, "activated_users": 1, "activation_rate": 0.25}

    async def _ret(*_args, **_kwargs):
        return {"retained_users": 1}

    async def _funnel(*_args, **_kwargs):
        return {"invite_redeemed": 2, "checked_gift": 2, "added_gift": 1, "upgrade_viewed": 1, "pay_started": 1, "payment_submitted": 0, "feedback_count": 1}

    async def _feature(*_args, **_kwargs):
        return {"top_commands": [("/check", 3)]}

    async def _revenue(*_args, **kwargs):
        days = kwargs.get("period_days", 7)
        return {"revenue_ton": 10.0 if days == 7 else 30.0, "payments_count": 2}

    async def _stale(*_args, **_kwargs):
        return [object()]

    class _Feedback:
        def __init__(self, _s):
            pass

        async def calculate_sla_metrics(self):
            return {"overdue_feedback_48h": 1, "new_feedback_count": 2}

    class _Alerts:
        def __init__(self, _s):
            pass

        async def count_incidents(self):
            return 3

    monkeypatch.setattr("app.bot.handlers.admin._require_admin", _req)
    monkeypatch.setattr("app.bot.handlers.admin.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.admin.calculate_activation_metrics", _act)
    monkeypatch.setattr("app.bot.handlers.admin.calculate_retention_metrics", _ret)
    monkeypatch.setattr("app.bot.handlers.admin.calculate_funnel_metrics", _funnel)
    monkeypatch.setattr("app.bot.handlers.admin.calculate_feature_usage", _feature)
    monkeypatch.setattr("app.bot.handlers.admin.calculate_revenue_summary", _revenue)
    monkeypatch.setattr("app.bot.handlers.admin.list_stale_submitted_requests", _stale)
    monkeypatch.setattr("app.bot.handlers.admin.FeedbackRepository", _Feedback)
    monkeypatch.setattr("app.bot.handlers.admin.AlertRepository", _Alerts)

    msg = _Msg()
    await admin_weekly_summary_handler(msg)
    assert "Weekly Summary" in msg.out[0]
    assert "Finance summary" in msg.out[0]
