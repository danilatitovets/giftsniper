import hashlib
import hmac
import json

import pytest

from app.services.billing_providers.mock import MockBillingProvider


def _sign(payload: dict, secret: str) -> str:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_verify_signature_valid(monkeypatch):
    monkeypatch.setattr("app.services.billing_providers.mock.get_settings", lambda: type("S", (), {"mock_billing_webhook_secret": "abc"})())
    provider = MockBillingProvider()
    payload = {"id": "evt_1", "type": "mock.checkout.completed"}
    ok = await provider.verify_webhook(payload, {"x-mock-signature": _sign(payload, "abc")})
    assert ok is True


@pytest.mark.asyncio
async def test_verify_signature_invalid(monkeypatch):
    monkeypatch.setattr("app.services.billing_providers.mock.get_settings", lambda: type("S", (), {"mock_billing_webhook_secret": "abc"})())
    provider = MockBillingProvider()
    payload = {"id": "evt_1", "type": "mock.checkout.completed"}
    ok = await provider.verify_webhook(payload, {"x-mock-signature": "bad"})
    assert ok is False
