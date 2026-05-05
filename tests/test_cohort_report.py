import pytest

from app.bot.handlers.admin import admin_cohort_report_handler


class _Msg:
    text = "/admin_cohort_report"
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
async def test_cohort_report_flags_inactive_not_activated(monkeypatch):
    async def _req(_):
        return type("A", (), {"id": 1, "role": "admin"})()

    class _Users:
        def __init__(self, _s):
            pass

        async def list_all(self):
            from datetime import datetime, timedelta

            old = datetime.utcnow() - timedelta(days=4)
            return [
                type(
                    "U",
                    (),
                    {
                        "id": 1,
                        "telegram_id": 1,
                        "username": "u",
                        "plan": "free",
                        "created_at": datetime.utcnow(),
                        "first_seen_at": datetime.utcnow(),
                        "last_seen_at": old,
                        "command_count": 1,
                    },
                )()
            ]

    class _Feedback:
        def __init__(self, _s):
            pass

        async def count_by_user(self, *_):
            return 0

    class _Inv:
        def __init__(self, _s):
            pass

        async def has_user_redemption(self, *_):
            return False

    class _Payments:
        def __init__(self, _s):
            pass

        async def list_user_payment_requests(self, *_args, **_kwargs):
            return []

    class _Events:
        def __init__(self, _s):
            pass

        async def list_events(self, **_kwargs):
            return []

    monkeypatch.setattr("app.bot.handlers.admin._require_admin", _req)
    monkeypatch.setattr("app.bot.handlers.admin.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.admin.UserRepository", _Users)
    monkeypatch.setattr("app.bot.handlers.admin.FeedbackRepository", _Feedback)
    monkeypatch.setattr("app.bot.handlers.admin.BetaInviteRepository", _Inv)
    monkeypatch.setattr("app.bot.handlers.admin.ManualPaymentRepository", _Payments)
    monkeypatch.setattr("app.bot.handlers.admin.ProductEventRepository", _Events)
    msg = _Msg()
    await admin_cohort_report_handler(msg)
    assert "not_activated" in msg.out[0]
