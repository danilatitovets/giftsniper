import pytest

from app.bot.handlers.admin import admin_feedback_handler, feedback_handler


class _Ctx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Msg:
    def __init__(self, text):
        self.text = text
        self.from_user = type("U", (), {"id": 7, "username": "u"})()
        self.out = []

    async def answer(self, text, **kwargs):
        self.out.append(text)


@pytest.mark.asyncio
async def test_feedback_creates_item(monkeypatch):
    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1})()

    class _Repo:
        def __init__(self, _s):
            pass

        async def create_item(self, **kwargs):
            return type("F", (), {"id": 12})()

    monkeypatch.setattr("app.bot.handlers.admin.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.admin.UserRepository", _Users)
    monkeypatch.setattr("app.bot.handlers.admin.FeedbackRepository", _Repo)
    msg = _Msg("/feedback very good bot")
    await feedback_handler(msg)
    assert "Feedback #12" in msg.out[0]


@pytest.mark.asyncio
async def test_admin_feedback_lists_items(monkeypatch):
    async def _req(_):
        return type("A", (), {"id": 1, "role": "admin"})()

    class _Repo:
        def __init__(self, _s):
            pass

        async def list_items(self, limit=30):
            return [type("F", (), {"id": 1, "type": "bug", "status": "new", "user_id": 2, "created_at": "now"})()]

    monkeypatch.setattr("app.bot.handlers.admin._require_admin", _req)
    monkeypatch.setattr("app.bot.handlers.admin.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.admin.FeedbackRepository", _Repo)
    msg = _Msg("/admin_feedback")
    await admin_feedback_handler(msg)
    assert "Feedback queue" in msg.out[0]
