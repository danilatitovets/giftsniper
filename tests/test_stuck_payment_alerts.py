from datetime import datetime, timedelta, timezone

import pytest

from app.services import runtime_state
from app.services.scheduler import expire_manual_payment_requests_job


class _CtxSession:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


@pytest.mark.asyncio
async def test_stuck_payment_alert_sent_once_per_cooldown(monkeypatch):
    runtime_state.last_stuck_payment_alert_by_request.clear()
    stale = type("R", (), {"id": 12, "user_id": 3, "requested_plan": "pro", "created_at": datetime.now(timezone.utc) - timedelta(hours=7)})()
    monkeypatch.setattr("app.services.scheduler.expire_old_pending_requests", lambda _s: [])

    async def _stale(_s):
        return [stale]

    monkeypatch.setattr("app.services.scheduler.list_stale_submitted_requests", _stale)
    settings = type("S", (), {"admin_telegram_ids": "100", "admin_payment_alert_cooldown_minutes": 180})()
    bot = _Bot()

    async def _expire(_s):
        return []

    monkeypatch.setattr("app.services.scheduler.expire_old_pending_requests", _expire)

    await expire_manual_payment_requests_job(bot, lambda: _CtxSession(), settings)
    await expire_manual_payment_requests_job(bot, lambda: _CtxSession(), settings)
    assert len(bot.sent) == 1
