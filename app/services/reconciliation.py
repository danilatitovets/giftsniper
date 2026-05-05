from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BillingEvent, ManualPaymentRequest, User, UserEntitlement


async def find_confirmed_without_entitlement(session: AsyncSession) -> list[ManualPaymentRequest]:
    stmt = (
        select(ManualPaymentRequest)
        .outerjoin(
            UserEntitlement,
            and_(
                UserEntitlement.user_id == ManualPaymentRequest.user_id,
                UserEntitlement.status.in_(["active", "trialing", "grace"]),
            ),
        )
        .where(ManualPaymentRequest.status == "confirmed", UserEntitlement.id.is_(None))
        .order_by(ManualPaymentRequest.created_at.desc())
    )
    return list((await session.scalars(stmt)).all())


async def find_entitlement_without_payment(session: AsyncSession) -> list[UserEntitlement]:
    stmt = (
        select(UserEntitlement)
        .outerjoin(
            ManualPaymentRequest,
            and_(
                ManualPaymentRequest.user_id == UserEntitlement.user_id,
                ManualPaymentRequest.status == "confirmed",
            ),
        )
        .where(
            UserEntitlement.source == "manual_payment",
            UserEntitlement.status.in_(["active", "trialing", "grace"]),
            ManualPaymentRequest.id.is_(None),
        )
        .order_by(UserEntitlement.updated_at.desc())
    )
    return list((await session.scalars(stmt)).all())


async def find_payment_event_mismatch(session: AsyncSession) -> list[ManualPaymentRequest]:
    stmt = (
        select(ManualPaymentRequest)
        .outerjoin(
            BillingEvent,
            and_(
                BillingEvent.user_id == ManualPaymentRequest.user_id,
                BillingEvent.event_type == "manual_payment_confirmed",
                BillingEvent.status == "confirmed",
            ),
        )
        .where(ManualPaymentRequest.status == "confirmed", BillingEvent.id.is_(None))
    )
    return list((await session.scalars(stmt)).all())


async def find_expired_entitlement_with_active_plan(session: AsyncSession) -> list[User]:
    stmt = (
        select(User)
        .join(UserEntitlement, UserEntitlement.user_id == User.id)
        .where(
            UserEntitlement.status.in_(["expired", "canceled"]),
            User.plan != UserEntitlement.plan,
        )
    )
    return list((await session.scalars(stmt)).all())


def format_reconciliation_report(
    *,
    confirmed_without_entitlement: list[ManualPaymentRequest],
    entitlement_without_payment: list[UserEntitlement],
    payment_event_mismatch: list[ManualPaymentRequest],
    expired_with_active_plan: list[User],
) -> str:
    return (
        "🧮 Reconciliation Report\n"
        f"Confirmed payments without active entitlement: {len(confirmed_without_entitlement)}\n"
        f"Active manual entitlements without confirmed payment: {len(entitlement_without_payment)}\n"
        f"Confirmed payments without billing_event confirmed: {len(payment_event_mismatch)}\n"
        f"Users with plan != effective entitlement: {len(expired_with_active_plan)}\n"
        "Recommended action: inspect /admin_payment <id>, verify tx/proof, "
        "then fix entitlement or add missing billing event."
    )
