from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timezone

from app.config import get_settings
from app.web.billing import handle_billing_webhook


def _build_payload(args) -> dict:
    event_map = {
        "checkout.completed": "mock.checkout.completed",
        "subscription.renewed": "mock.subscription.renewed",
        "subscription.canceled": "mock.subscription.canceled",
        "payment.failed": "mock.payment.failed",
    }
    return {
        "id": f"evt_test_{int(datetime.now(timezone.utc).timestamp())}",
        "type": event_map[args.event],
        "telegram_id": args.telegram_id,
        "plan": args.plan,
        "days": args.days,
        "amount": args.amount,
        "currency": args.currency,
    }


def _sign(payload: dict, secret: str) -> str:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def _run(args):
    settings = get_settings()
    payload = _build_payload(args)
    signature = _sign(payload, settings.mock_billing_webhook_secret or "dev-secret")
    result = await handle_billing_webhook("mock", payload, {"x-mock-signature": signature})
    print(json.dumps({"payload": payload, "result": result}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--telegram-id", type=int, required=True)
    parser.add_argument("--plan", type=str, default="pro")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--event", type=str, choices=["checkout.completed", "subscription.renewed", "subscription.canceled", "payment.failed"], default="checkout.completed")
    parser.add_argument("--amount", type=float, default=19.0)
    parser.add_argument("--currency", type=str, default="USD")
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
