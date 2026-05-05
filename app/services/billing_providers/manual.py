from __future__ import annotations

from app.services.billing_providers.base import BillingProviderBase


class ManualBillingProvider(BillingProviderBase):
    async def create_checkout(self, user, plan: str) -> str:
        return (
            f"Manual upgrade request\n"
            f"User: {user.telegram_id}\n"
            f"Requested plan: {plan}\n"
            "Для апгрейда напишите администратору и дождитесь подтверждения."
        )

    async def verify_webhook(self, payload: dict, headers: dict) -> bool:
        return False

    async def parse_event(self, payload: dict) -> dict:
        return {"id": payload.get("id"), "type": payload.get("type", "manual.noop")}

    async def map_event_to_entitlement(self, payload: dict) -> dict:
        return {"action": "ignored", "reason": "manual provider has no webhook flow"}
