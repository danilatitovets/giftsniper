"""Stage 35: /home suggests signal feedback when recent snapshot exists."""

from datetime import datetime, timedelta

import pytest

from app.bot.handlers.start import _render_home


class _Msg:
    def __init__(self):
        self.from_user = type("U", (), {"id": 42, "username": "user"})()


@pytest.mark.asyncio
async def test_home_suggests_signal_feedback_for_recent_snapshot(monkeypatch):
    class _Ctx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    snap = type(
        "S",
        (),
        {"id": 123, "created_at": datetime.utcnow() - timedelta(hours=1)},
    )()

    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type(
                "U",
                (),
                {
                    "id": 42,
                    "plan": "pro",
                    "role": "user",
                    "bankroll_ton": 100.0,
                    "goal_ton": None,
                    "command_count": 0,
                },
            )()

        async def list_universe(self, *_):
            return [type("R", (), {"is_active": True})()]

    class _Gifts:
        def __init__(self, _s):
            pass

        async def count_by_user(self, *_):
            return 2

    class _Alerts:
        def __init__(self, _s):
            pass

        async def count_alert_rules(self, *_):
            return 0

        async def list_open_incidents(self, *_):
            return []

    class _Feedback:
        def __init__(self, _s):
            pass

        async def count_by_user(self, *_):
            return 1

    class _Payments:
        def __init__(self, _s):
            pass

        async def list_stale_submitted(self, **_kwargs):
            return []

    class _Trades:
        def __init__(self, _s):
            pass

        async def count_open_for_user(self, *_):
            return 0

    class _SignalRepo:
        def __init__(self, _s):
            pass

        async def list_recent_for_user(self, *_args, **_kwargs):
            return [snap]

    monkeypatch.setattr("app.bot.handlers.start.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.start.UserRepository", _Users)
    monkeypatch.setattr("app.bot.handlers.start.GiftRepository", _Gifts)
    monkeypatch.setattr("app.bot.handlers.start.AlertRepository", _Alerts)
    monkeypatch.setattr("app.bot.handlers.start.FeedbackRepository", _Feedback)
    monkeypatch.setattr("app.bot.handlers.start.ManualPaymentRepository", _Payments)
    monkeypatch.setattr("app.bot.handlers.start.TradeJournalRepository", _Trades)
    monkeypatch.setattr("app.bot.handlers.start.SignalSnapshotRepository", _SignalRepo)

    text = await _render_home(_Msg())
    assert "signal_good 123" in text
    assert "signal_bad 123" in text
    assert "Последний signal ID: #123" in text
