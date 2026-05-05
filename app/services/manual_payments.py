from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.db.repositories.billing import BillingRepository
from app.db.repositories.manual_payments import ManualPaymentRepository
from app.db.repositories.users import UserRepository
from app.services.audit import log_audit
from app.services.entitlements import grant_entitlement, sync_user_plan_from_entitlement


def _age_human(dt: datetime) -> str:
    base = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    mins = int((datetime.now(timezone.utc) - base).total_seconds() // 60)
    if mins < 60:
        return f"{mins}m"
    if mins < 1440:
        return f"{mins // 60}h"
    return f"{mins // 1440}d"


def _plan_price_ton(plan: str) -> float:
    settings = get_settings()
    p = plan.lower()
    if p == "starter":
        return float(settings.manual_payment_starter_ton)
    if p == "pro":
        return float(settings.manual_payment_pro_ton)
    if p == "trader":
        return float(settings.manual_payment_trader_ton)
    raise ValueError("unsupported plan")


def format_payment_instructions(request, wallet_address: str) -> str:
    return (
        "💸 Manual Crypto Payment\n"
        f"Request ID: {request.id}\n"
        f"Plan: {request.requested_plan}\n"
        f"Amount: {request.amount:.2f} {request.currency}\n"
        f"Wallet: {wallet_address}\n\n"
        "Чеклист:\n"
        "1) Отправь TON на wallet выше.\n"
        "2) Скопируй tx hash.\n"
        f"3) Отправь: /payment_sent {request.id} | <tx_hash>\n"
        "4) Дождись ручного подтверждения.\n\n"
        "Отправляй только TON на указанный TON wallet.\n"
        "Доступ не выдается автоматически.\n"
        "Если ошибся адресом/сетью, бот не может вернуть средства автоматически.\n"
        "Бот не хранит seed/private keys."
    )


def format_payment_request_admin(request) -> str:
    proof_short = (request.tx_hash or request.proof_text or "n/a")
    if len(proof_short) > 48:
        proof_short = proof_short[:45] + "..."
    return (
        f"#{request.id} user={request.user_id}\n"
        f"plan={request.requested_plan} amount={request.amount} {request.currency}\n"
        f"status={request.status} age={_age_human(request.created_at)}\n"
        f"proof={proof_short}\n"
        f"created={request.created_at}"
    )


async def create_payment_request(session, user_id: int, plan: str, amount: float | None = None, currency: str | None = None):
    settings = get_settings()
    repo = ManualPaymentRepository(session)
    value = amount if amount is not None else _plan_price_ton(plan)
    curr = currency or settings.manual_payment_default_currency
    expires = datetime.now(timezone.utc) + timedelta(days=2)
    return await repo.create_payment_request(
        user_id=user_id,
        requested_plan=plan.lower(),
        amount=value,
        currency=curr,
        wallet_address=settings.owner_crypto_wallet_ton,
        expires_at=expires,
    )


async def submit_payment_proof(session, user_id: int, request_id: int, tx_hash_or_text: str):
    repo = ManualPaymentRepository(session)
    tx = tx_hash_or_text.strip()
    if len(tx) <= 255 and " " not in tx:
        duplicate = await repo.get_by_tx_hash(tx)
        if duplicate is not None and duplicate.id != request_id:
            raise ValueError("Этот tx_hash уже используется в другой заявке.")
    return await repo.submit_payment_proof(user_id, request_id, tx_hash_or_text)


async def confirm_payment_request(session, admin_user_id: int, request_id: int, days: int, note: str | None):
    repo = ManualPaymentRepository(session)
    row = await repo.confirm_payment_request(admin_user_id, request_id, note)
    if row is None:
        return None
    expires = datetime.now(timezone.utc) + timedelta(days=days)
    await grant_entitlement(session, row.user_id, row.requested_plan, "manual_payment", expires, note)
    await BillingRepository(session).create_billing_event(
        user_id=row.user_id,
        event_type="manual_payment_confirmed",
        provider="manual_payment",
        plan=row.requested_plan,
        amount=row.amount,
        currency=row.currency,
        status="confirmed",
        metadata_json=(row.tx_hash or row.proof_text or "")[:3800],
    )
    user = await UserRepository(session).get_by_id(row.user_id)
    if user is not None:
        await sync_user_plan_from_entitlement(session, user)
    await log_audit(
        session,
        user_id=admin_user_id,
        action="manual_payment_confirmed",
        entity_type="manual_payment_request",
        entity_id=str(request_id),
        metadata_json={"days": days, "note": note, "user_id": row.user_id},
    )
    return row


async def reject_payment_request(session, admin_user_id: int, request_id: int, reason: str):
    repo = ManualPaymentRepository(session)
    row = await repo.reject_payment_request(admin_user_id, request_id, reason)
    if row is None:
        return None
    await BillingRepository(session).create_billing_event(
        user_id=row.user_id,
        event_type="manual_payment_rejected",
        provider="manual_payment",
        plan=row.requested_plan,
        amount=row.amount,
        currency=row.currency,
        status="rejected",
        metadata_json=reason[:3800],
    )
    await log_audit(
        session,
        user_id=admin_user_id,
        action="manual_payment_rejected",
        entity_type="manual_payment_request",
        entity_id=str(request_id),
        metadata_json={"reason": reason, "user_id": row.user_id},
    )
    return row


async def list_pending_payment_requests(session):
    return await ManualPaymentRepository(session).list_pending_payment_requests()


async def list_payment_requests_by_status(session, statuses: list[str], limit: int = 50):
    return await ManualPaymentRepository(session).list_by_status(statuses, limit=limit)


def _utc_naive(dt: datetime | None = None) -> datetime:
    """Колонки TIMESTAMP WITHOUT TIME ZONE: asyncpg не смешивает naive и aware."""
    d = dt or datetime.now(timezone.utc)
    if d.tzinfo is None:
        return d
    return d.astimezone(timezone.utc).replace(tzinfo=None)


async def list_stale_submitted_requests(session):
    settings = get_settings()
    older_than = _utc_naive() - timedelta(hours=settings.manual_payment_submitted_sla_hours)
    return await ManualPaymentRepository(session).list_stale_submitted(older_than)


async def search_payment_requests(session, query: str):
    return await ManualPaymentRepository(session).search(query)


async def list_user_payment_requests(session, user_id: int):
    return await ManualPaymentRepository(session).list_user_payment_requests(user_id)


async def get_payment_request(session, request_id: int):
    return await ManualPaymentRepository(session).get_by_id(request_id)


async def expire_old_pending_requests(session):
    settings = get_settings()
    older_than = _utc_naive() - timedelta(hours=settings.manual_payment_request_ttl_hours)
    repo = ManualPaymentRepository(session)
    rows = await repo.expire_pending_older_than(older_than)
    for row in rows:
        await BillingRepository(session).create_billing_event(
            user_id=row.user_id,
            event_type="manual_payment_expired",
            provider="manual_payment",
            plan=row.requested_plan,
            amount=row.amount,
            currency=row.currency,
            status="expired",
            metadata_json=f"request_id={row.id}",
        )
        await log_audit(
            session,
            user_id=row.user_id,
            action="manual_payment_expired",
            entity_type="manual_payment_request",
            entity_id=str(row.id),
        )
    return rows
