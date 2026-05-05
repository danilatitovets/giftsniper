import pytest

from app.bot.handlers.admin import signal_bad_handler, signal_good_handler


class _Msg:
    def __init__(self, text):
        self.text = text
        self.from_user = type("U", (), {"id": 7, "username": "u"})()
        self.out = []

    async def answer(self, text, **kwargs):
        self.out.append(text)


class _Ctx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_signal_good_bad_create_feedback(monkeypatch):
    created_types = []

    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1})()

    class _Feedback:
        def __init__(self, _s):
            pass

        async def create_item(self, **kwargs):
            created_types.append(kwargs["item_type"])
            return type("F", (), {"id": 5})()

    class _Events:
        def __init__(self, _s):
            pass

        async def create_event(self, **kwargs):
            return kwargs

    monkeypatch.setattr("app.bot.handlers.admin.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.admin.UserRepository", _Users)
    monkeypatch.setattr("app.bot.handlers.admin.FeedbackRepository", _Feedback)
    monkeypatch.setattr("app.bot.handlers.admin.ProductEventRepository", _Events)

    await signal_good_handler(_Msg("/signal_good useful"))
    await signal_bad_handler(_Msg("/signal_bad failed"))
    assert created_types == ["signal_good", "signal_bad"]
