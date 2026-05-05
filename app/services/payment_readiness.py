"""Manual payment readiness (config + read-only DB counts)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ManualPaymentRequest
from app.db.repositories.manual_payments import ManualPaymentRepository


@dataclass
class PaymentReadiness:
    manual_enabled: bool
    wallet_configured: bool
    prices_configured: bool
    admin_ids_configured: bool
    submitted_total: int
    stale_submitted_count: int


def manual_prices_configured(settings) -> bool:
    try:
        return (
            float(getattr(settings, "manual_payment_starter_ton", 0) or 0) > 0
            and float(getattr(settings, "manual_payment_pro_ton", 0) or 0) > 0
            and float(getattr(settings, "manual_payment_trader_ton", 0) or 0) > 0
        )
    except (TypeError, ValueError):
        return False


async def build_payment_readiness(session: AsyncSession, settings) -> PaymentReadiness:
    manual = bool(getattr(settings, "manual_payment_enabled", False))
    wallet = bool(str(getattr(settings, "owner_crypto_wallet_ton", "") or "").strip())
    admins = bool(str(getattr(settings, "admin_telegram_ids", "") or "").strip())
    prices = manual_prices_configured(settings)
    submitted = int(await session.scalar(select(func.count(ManualPaymentRequest.id)).where(ManualPaymentRequest.status == "submitted")) or 0)
    sla_h = int(getattr(settings, "manual_payment_submitted_sla_hours", 6) or 6)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=sla_h)
    cutoff_naive = cutoff.replace(tzinfo=None)
    stale_rows = await ManualPaymentRepository(session).list_stale_submitted(cutoff_naive, limit=500)
    stale_n = len(stale_rows)
    return PaymentReadiness(
        manual_enabled=manual,
        wallet_configured=wallet,
        prices_configured=prices,
        admin_ids_configured=admins,
        submitted_total=submitted,
        stale_submitted_count=stale_n,
    )
