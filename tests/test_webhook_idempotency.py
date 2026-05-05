import pytest

from app.services.billing_webhooks import process_webhook


class _Session:
    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_duplicate_provider_event_id_not_granted_twice(monkeypatch):
    called = {"grant": 0}
    payload = {"id": "evt_dup_1", "type": "mock.checkout.completed", "telegram_id": 123, "plan": "pro", "days": 30}

    existing = type("W", (), {"id": 99, "status": "processed"})()

    class _WebhookRepo:
        def __init__(self, _s):
            pass

        async def get_by_provider_event_id(self, *_):
            return existing

        async def mark_duplicate(self, _id):
            return existing

    async def _grant(*args, **kwargs):
        called["grant"] += 1
        return object()

    monkeypatch.setattr("app.services.billing_webhooks.PaymentWebhookRepository", _WebhookRepo)
    monkeypatch.setattr("app.services.billing_webhooks.grant_entitlement", _grant)
    monkeypatch.setattr("app.services.billing_webhooks.get_settings", lambda: type("S", (), {"billing_provider": "mock", "billing_default_currency": "USD", "billing_webhook_max_attempts": 3})())
    result = await process_webhook(_Session(), "mock", payload, {"x-mock-signature": "x"})
    assert result["status"] == "duplicate"
    assert called["grant"] == 0
