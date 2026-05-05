import pytest

from app.services.billing_webhooks import retry_webhook_event


class _Session:
    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_failed_event_can_be_retried(monkeypatch):
    row = type(
        "W",
        (),
        {
            "id": 1,
            "status": "failed",
            "attempts": 1,
            "provider": "mock",
            "last_error": "x",
            "sanitized_payload_json": "{}",
            "sanitized_headers_json": "{}",
        },
    )()

    class _Repo:
        def __init__(self, _s):
            pass

        async def get_by_id(self, _id):
            return row

        async def mark_dead_letter(self, *_):
            return row

    async def _process(*args, **kwargs):
        return {"ok": True, "status": "processed"}

    monkeypatch.setattr("app.services.billing_webhooks.PaymentWebhookRepository", _Repo)
    monkeypatch.setattr("app.services.billing_webhooks.process_webhook", _process)
    monkeypatch.setattr("app.services.billing_webhooks.get_settings", lambda: type("S", (), {"billing_webhook_max_attempts": 3})())
    result = await retry_webhook_event(_Session(), 1)
    assert result["status"] == "processed"


@pytest.mark.asyncio
async def test_after_max_attempts_dead_letter(monkeypatch):
    row = type(
        "W",
        (),
        {
            "id": 2,
            "status": "failed",
            "attempts": 3,
            "provider": "mock",
            "last_error": "max",
            "sanitized_payload_json": "{}",
            "sanitized_headers_json": "{}",
        },
    )()

    class _Repo:
        def __init__(self, _s):
            pass

        async def get_by_id(self, _id):
            return row

        async def mark_dead_letter(self, *_):
            return row

    monkeypatch.setattr("app.services.billing_webhooks.PaymentWebhookRepository", _Repo)
    monkeypatch.setattr("app.services.billing_webhooks.get_settings", lambda: type("S", (), {"billing_webhook_max_attempts": 3})())
    result = await retry_webhook_event(_Session(), 2)
    assert result["status"] == "dead_letter"
