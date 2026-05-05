from __future__ import annotations

from app.config import get_settings
from app.db.session import SessionLocal
from app.services.billing_webhooks import process_webhook


async def handle_billing_webhook(provider: str, payload: dict, headers: dict) -> dict:
    settings = get_settings()
    if not settings.billing_webhooks_enabled:
        return {"ok": False, "status": "disabled"}
    if provider == "mock" and not settings.mock_billing_enabled:
        return {"ok": False, "status": "disabled"}
    async with SessionLocal() as session:
        return await process_webhook(session, provider, payload, headers)
