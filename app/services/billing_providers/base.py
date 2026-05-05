from __future__ import annotations


class BillingProviderBase:
    async def create_checkout(self, user, plan: str) -> str:
        raise NotImplementedError

    async def verify_webhook(self, payload: dict, headers: dict) -> bool:
        raise NotImplementedError

    async def parse_event(self, payload: dict) -> dict:
        raise NotImplementedError

    async def map_event_to_entitlement(self, payload: dict) -> dict:
        raise NotImplementedError
