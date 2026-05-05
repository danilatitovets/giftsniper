from __future__ import annotations

from app.web.billing import handle_billing_webhook

try:
    from fastapi import FastAPI, Request
except Exception:  # pragma: no cover
    FastAPI = None  # type: ignore
    Request = object  # type: ignore


def create_web_app():
    if FastAPI is None:
        return None
    app = FastAPI(title="GiftSniper Webhook Skeleton")

    @app.post("/webhooks/billing/{provider}")
    async def billing_webhook(provider: str, request: Request):
        payload = await request.json()
        headers = dict(request.headers)
        result = await handle_billing_webhook(provider, payload, headers)
        return {"ok": bool(result.get("ok")), "status": result.get("status", "ignored")}

    return app
