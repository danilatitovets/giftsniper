import pytest

from app.bot.handlers.admin import admin_feedback_review_handler, admin_feedback_sla_handler


class _Msg:
    def __init__(self, text: str):
        self.text = text
        self.from_user = type("U", (), {"id": 9, "username": "admin"})()
        self.out = []

    async def answer(self, text, **kwargs):
        self.out.append(text)


class _Ctx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_feedback_review_sets_reviewed(monkeypatch):
    async def _req(_):
        return type("A", (), {"id": 42, "role": "admin"})()

    class _Repo:
        def __init__(self, _s):
            pass

        async def review_item(self, *_args, **_kwargs):
            return type("F", (), {"id": 7, "priority": "high"})()

    monkeypatch.setattr("app.bot.handlers.admin._require_admin", _req)
    monkeypatch.setattr("app.bot.handlers.admin.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.admin.FeedbackRepository", _Repo)
    msg = _Msg("/admin_feedback_review 7 | high | looked")
    await admin_feedback_review_handler(msg)
    assert "reviewed" in msg.out[0]


@pytest.mark.asyncio
async def test_feedback_sla_detects_overdue(monkeypatch):
    async def _req(_):
        return type("A", (), {"id": 42, "role": "admin"})()

    class _Repo:
        def __init__(self, _s):
            pass

        async def calculate_sla_metrics(self):
            return {
                "new_feedback_count": 3,
                "urgent_high_count": 2,
                "oldest_new_feedback_age": "53h",
                "average_close_time_hours": 12.0,
                "overdue_feedback_48h": 1,
            }

    monkeypatch.setattr("app.bot.handlers.admin._require_admin", _req)
    monkeypatch.setattr("app.bot.handlers.admin.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.admin.FeedbackRepository", _Repo)
    msg = _Msg("/admin_feedback_sla")
    await admin_feedback_sla_handler(msg)
    assert "Overdue feedback >48h: 1" in msg.out[0]
