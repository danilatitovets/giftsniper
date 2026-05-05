import pytest
import hashlib
import hmac
import json

from app.services.billing_webhooks import process_webhook


class _Session:
    async def commit(self):
        return None


def _sign(payload: dict, secret: str) -> str:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_valid_mock_checkout_grants_pro(monkeypatch):
    called = {"grant": 0}
    payload = {"id": "evt_test_1", "type": "mock.checkout.completed", "telegram_id": 123, "plan": "pro", "days": 30, "amount": 19, "currency": "USD"}

    class _WebhookRepo:
        def __init__(self, _s):
            pass

        async def get_by_provider_event_id(self, *_):
            return None

        async def create_webhook_event(self, **kwargs):
            return type("W", (), {"id": 1, "attempts": 0, **kwargs})()

        async def mark_processing(self, _id):
            return type("W", (), {"id": 1, "attempts": 1})()

        async def mark_processed(self, _id):
            return None

        async def mark_failed(self, _id, _e):
            return type("W", (), {"id": 1, "attempts": 1})()

    class _BillingRepo:
        def __init__(self, _s):
            pass

        async def create_billing_event(self, **kwargs):
            return object()

    class _UsersRepo:
        def __init__(self, _s):
            pass

        async def get_by_telegram_id(self, _tid):
            return type("U", (), {"id": 1, "telegram_id": 123, "is_blocked": False, "plan": "free"})()

        async def get_by_id(self, _uid):
            return type("U", (), {"id": 1, "telegram_id": 123, "is_blocked": False, "plan": "free"})()

    class _AuditRepo:
        def __init__(self, _s):
            pass

        async def create(self, **kwargs):
            return object()

    async def _grant(*args, **kwargs):
        called["grant"] += 1
        return object()

    async def _sync(*args, **kwargs):
        return {}

    monkeypatch.setattr("app.services.billing_webhooks.PaymentWebhookRepository", _WebhookRepo)
    monkeypatch.setattr("app.services.billing_webhooks.BillingRepository", _BillingRepo)
    monkeypatch.setattr("app.services.billing_webhooks.UserRepository", _UsersRepo)
    monkeypatch.setattr("app.services.billing_webhooks.AuditLogRepository", _AuditRepo)
    monkeypatch.setattr("app.services.billing_webhooks.grant_entitlement", _grant)
    monkeypatch.setattr("app.services.billing_webhooks.sync_user_plan_from_entitlement", _sync)
    monkeypatch.setattr("app.services.billing_webhooks.get_settings", lambda: type("S", (), {"billing_provider": "mock", "billing_default_currency": "USD", "billing_webhook_max_attempts": 3})())
    monkeypatch.setattr("app.services.billing_providers.mock.get_settings", lambda: type("S", (), {"mock_billing_webhook_secret": "abc"})())
    result = await process_webhook(_Session(), "mock", payload, {"x-mock-signature": _sign(payload, "abc")})
    assert result["status"] == "processed"
    assert called["grant"] == 1


@pytest.mark.asyncio
async def test_invalid_signature_does_not_grant(monkeypatch):
    payload = {"id": "evt_test_2", "type": "mock.checkout.completed", "telegram_id": 123, "plan": "pro", "days": 30}

    class _WebhookRepo:
        def __init__(self, _s):
            pass

        async def get_by_provider_event_id(self, *_):
            return None

        async def create_webhook_event(self, **kwargs):
            return type("W", (), {"id": 7, "attempts": 0, **kwargs})()

        async def mark_failed(self, _id, _e):
            return type("W", (), {"id": 7, "attempts": 1})()

    monkeypatch.setattr("app.services.billing_webhooks.PaymentWebhookRepository", _WebhookRepo)
    monkeypatch.setattr("app.services.billing_webhooks.get_settings", lambda: type("S", (), {"billing_provider": "mock", "billing_default_currency": "USD", "billing_webhook_max_attempts": 3})())
    monkeypatch.setattr("app.services.billing_providers.mock.get_settings", lambda: type("S", (), {"mock_billing_webhook_secret": "abc"})())
    result = await process_webhook(_Session(), "mock", payload, {"x-mock-signature": "bad"})
    assert result["status"] == "failed"
