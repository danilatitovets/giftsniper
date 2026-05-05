from __future__ import annotations

import hashlib
import hmac
import json

from app.config import get_settings
from app.services.billing_providers.base import BillingProviderBase


class MockBillingProvider(BillingProviderBase):
    async def create_checkout(self, user, plan: str) -> str:
        return f"Mock checkout created for user={user.telegram_id} plan={plan}"

    async def verify_webhook(self, payload: dict, headers: dict) -> bool:
        secret = get_settings().mock_billing_webhook_secret
        if not secret:
            return False
        signature = str(headers.get("x-mock-signature", ""))
        body = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    async def parse_event(self, payload: dict) -> dict:
        return {
            "id": payload.get("id"),
            "type": payload.get("type"),
            "telegram_id": payload.get("telegram_id"),
            "plan": payload.get("plan"),
            "days": payload.get("days"),
            "amount": payload.get("amount"),
            "currency": payload.get("currency"),
        }

    async def map_event_to_entitlement(self, payload: dict) -> dict:
        event_type = payload.get("type")
        if event_type in {"mock.checkout.completed", "mock.subscription.renewed"}:
            return {"action": "grant", "event_type": event_type}
        if event_type == "mock.subscription.canceled":
            return {"action": "cancel", "event_type": event_type}
        if event_type == "mock.payment.failed":
            return {"action": "payment_failed", "event_type": event_type}
        return {"action": "ignored", "event_type": event_type}
