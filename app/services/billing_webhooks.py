from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.db.repositories.audit import AuditLogRepository
from app.db.repositories.billing import BillingRepository
from app.db.repositories.payment_webhooks import PaymentWebhookRepository
from app.db.repositories.users import UserRepository
from app.services.entitlements import cancel_entitlement, grant_entitlement, sync_user_plan_from_entitlement
from app.services.billing_providers.mock import MockBillingProvider


def sanitize_webhook_payload(payload: dict) -> str:
    safe = dict(payload)
    for key in ["card", "token", "secret", "password", "private_key", "seed"]:
        if key in safe:
            safe[key] = "***"
    return json.dumps(safe, ensure_ascii=True, sort_keys=True)[:3900]


def sanitize_webhook_headers(headers: dict) -> str:
    safe = {}
    for k, v in headers.items():
        lk = str(k).lower()
        if "authorization" in lk or "cookie" in lk or "secret" in lk:
            safe[lk] = "***"
        else:
            safe[lk] = str(v)[:200]
    return json.dumps(safe, ensure_ascii=True, sort_keys=True)[:3900]


def extract_provider_event_id(provider: str, payload: dict) -> str | None:
    _ = provider
    return payload.get("id")


def map_provider_event_to_billing_event(provider: str, payload: dict) -> dict:
    _ = provider
    return {
        "event_type": payload.get("type"),
        "plan": payload.get("plan"),
        "amount": payload.get("amount"),
        "currency": payload.get("currency"),
    }


async def handle_duplicate_event(webhook_repo: PaymentWebhookRepository, row_id: int) -> None:
    await webhook_repo.mark_duplicate(row_id)


async def apply_billing_event_to_entitlement(session, mapped_event: dict, payload: dict) -> tuple[str, int | None]:
    users_repo = UserRepository(session)
    billing_repo = BillingRepository(session)
    telegram_id = payload.get("telegram_id")
    if not telegram_id:
        return "ignored", None
    user = await users_repo.get_by_telegram_id(int(telegram_id))
    if user is None:
        return "ignored", None
    action = mapped_event.get("action")
    if action == "grant":
        days = int(payload.get("days") or 30)
        expires = datetime.now(timezone.utc) + timedelta(days=days)
        await grant_entitlement(session, user.id, payload.get("plan") or "starter", "provider", expires, "mock provider event")
        await AuditLogRepository(session).create(
            user_id=user.id,
            action="billing_webhook_grant",
            entity_type="user",
            entity_id=str(user.id),
            metadata_json={"event_type": mapped_event.get("event_type")},
        )
        return "processed", user.id
    if action == "cancel":
        await cancel_entitlement(session, user.id, "provider cancellation")
        await AuditLogRepository(session).create(
            user_id=user.id,
            action="billing_webhook_cancel",
            entity_type="user",
            entity_id=str(user.id),
            metadata_json={"event_type": mapped_event.get("event_type")},
        )
        return "processed", user.id
    if action == "payment_failed":
        await billing_repo.create_billing_event(
            user_id=user.id,
            event_type="payment_failed",
            provider=get_settings().billing_provider,
            provider_event_id=payload.get("id"),
            plan=payload.get("plan"),
            amount=float(payload.get("amount") or 0) or None,
            currency=payload.get("currency"),
            status="failed",
            metadata_json="mock payment failed",
        )
        return "ignored", user.id
    return "ignored", user.id


async def process_webhook(session, provider: str, payload: dict, headers: dict) -> dict:
    settings = get_settings()
    webhook_repo = PaymentWebhookRepository(session)
    billing_repo = BillingRepository(session)
    provider_impl = MockBillingProvider() if provider == "mock" else None
    if provider_impl is None:
        return {"ok": False, "status": "ignored", "reason": "provider not supported"}

    provider_event_id = extract_provider_event_id(provider, payload)
    if provider_event_id:
        existing = await webhook_repo.get_by_provider_event_id(provider, provider_event_id)
        if existing and existing.status in {"processed", "duplicate"}:
            await handle_duplicate_event(webhook_repo, existing.id)
            return {"ok": True, "status": "duplicate"}

    parsed = await provider_impl.parse_event(payload)
    sanitized_payload = sanitize_webhook_payload(payload)
    sanitized_headers = sanitize_webhook_headers(headers)
    signature_valid = await provider_impl.verify_webhook(payload, headers)
    event_row = await webhook_repo.create_webhook_event(
        provider=provider,
        provider_event_id=provider_event_id,
        event_type=parsed.get("type"),
        status="received",
        signature_valid=signature_valid,
        user_id=None,
        plan=parsed.get("plan"),
        amount=float(parsed.get("amount") or 0) or None,
        currency=parsed.get("currency"),
        sanitized_payload_json=sanitized_payload,
        sanitized_headers_json=sanitized_headers,
    )
    if not signature_valid:
        await webhook_repo.mark_failed(event_row.id, "invalid signature")
        return {"ok": False, "status": "failed"}

    try:
        row = await webhook_repo.mark_processing(event_row.id)
        mapped = await provider_impl.map_event_to_entitlement(payload)
        mapped_billing = map_provider_event_to_billing_event(provider, payload)
        status, user_id = await apply_billing_event_to_entitlement(session, mapped, payload)
        await billing_repo.create_billing_event(
            user_id=user_id,
            event_type=mapped_billing["event_type"] or "unknown",
            provider=provider,
            provider_event_id=provider_event_id,
            plan=mapped_billing["plan"],
            amount=float(mapped_billing["amount"] or 0) or None,
            currency=mapped_billing["currency"] or settings.billing_default_currency,
            status=status,
            metadata_json="from webhook",
        )
        if user_id is not None:
            user = await UserRepository(session).get_by_id(user_id)
            if user is not None:
                await sync_user_plan_from_entitlement(session, user)
        await webhook_repo.mark_processed(row.id)
        return {"ok": True, "status": "processed"}
    except Exception as exc:
        failed = await webhook_repo.mark_failed(event_row.id, str(exc))
        if failed and failed.attempts >= settings.billing_webhook_max_attempts:
            await webhook_repo.mark_dead_letter(event_row.id, str(exc))
            return {"ok": False, "status": "dead_letter"}
        return {"ok": False, "status": "failed"}


async def retry_webhook_event(session, event_id: int) -> dict:
    settings = get_settings()
    repo = PaymentWebhookRepository(session)
    row = await repo.get_by_id(event_id)
    if row is None:
        return {"ok": False, "status": "not_found"}
    if row.status not in {"failed", "dead_letter"}:
        return {"ok": False, "status": "not_retryable"}
    if row.attempts >= settings.billing_webhook_max_attempts:
        await repo.mark_dead_letter(event_id, row.last_error or "max attempts reached")
        return {"ok": False, "status": "dead_letter"}
    payload = json.loads(row.sanitized_payload_json or "{}")
    headers = json.loads(row.sanitized_headers_json or "{}")
    return await process_webhook(session, row.provider, payload, headers)
