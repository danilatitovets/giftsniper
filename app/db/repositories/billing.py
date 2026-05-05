from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BillingEvent, EntitlementOverride, UserEntitlement


class BillingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_entitlement(self, user_id: int) -> UserEntitlement | None:
        stmt = select(UserEntitlement).where(UserEntitlement.user_id == user_id)
        return await self.session.scalar(stmt)

    async def upsert_entitlement(
        self,
        *,
        user_id: int,
        plan: str,
        status: str,
        source: str,
        starts_at: datetime | None = None,
        expires_at: datetime | None = None,
        grace_until: datetime | None = None,
        canceled_at: datetime | None = None,
        last_checked_at: datetime | None = None,
    ) -> UserEntitlement:
        row = await self.get_entitlement(user_id)
        if row is None:
            row = UserEntitlement(user_id=user_id, plan=plan, status=status, source=source, starts_at=starts_at or datetime.now(timezone.utc))
            self.session.add(row)
        row.plan = plan
        row.status = status
        row.source = source
        if expires_at is not None:
            row.expires_at = expires_at
        if grace_until is not None or status in {"grace", "expired"}:
            row.grace_until = grace_until
        if canceled_at is not None:
            row.canceled_at = canceled_at
        if last_checked_at is not None:
            row.last_checked_at = last_checked_at
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_expiration_candidates(self) -> list[UserEntitlement]:
        stmt = select(UserEntitlement).where(UserEntitlement.status.in_(["active", "trialing", "grace", "canceled"]))
        return list((await self.session.scalars(stmt)).all())

    async def create_billing_event(
        self,
        *,
        user_id: int | None,
        event_type: str,
        provider: str | None = None,
        provider_event_id: str | None = None,
        plan: str | None = None,
        amount: float | None = None,
        currency: str | None = None,
        status: str | None = None,
        metadata_json: str | None = None,
    ) -> BillingEvent:
        row = BillingEvent(
            user_id=user_id,
            event_type=event_type,
            provider=provider,
            provider_event_id=provider_event_id,
            plan=plan,
            amount=amount,
            currency=currency,
            status=status,
            metadata_json=metadata_json,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_billing_events(self, user_id: int | None = None, limit: int = 20) -> list[BillingEvent]:
        stmt = select(BillingEvent)
        if user_id is not None:
            stmt = stmt.where(BillingEvent.user_id == user_id)
        stmt = stmt.order_by(BillingEvent.created_at.desc()).limit(limit)
        return list((await self.session.scalars(stmt)).all())

    async def get_active_override(self, user_id: int, now: datetime) -> EntitlementOverride | None:
        stmt = select(EntitlementOverride).where(
            EntitlementOverride.user_id == user_id,
            EntitlementOverride.is_active.is_(True),
        )
        rows = list((await self.session.scalars(stmt)).all())
        for row in rows:
            if row.expires_at is None or row.expires_at > now:
                return row
            row.is_active = False
        if rows:
            await self.session.commit()
        return None

    async def add_override(
        self,
        *,
        user_id: int,
        plan: str,
        reason: str | None,
        created_by_user_id: int | None,
        expires_at: datetime | None,
        is_active: bool = True,
    ) -> EntitlementOverride:
        row = EntitlementOverride(
            user_id=user_id,
            plan=plan,
            reason=reason,
            created_by_user_id=created_by_user_id,
            expires_at=expires_at,
            is_active=is_active,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_overrides(self, user_id: int, limit: int = 10) -> list[EntitlementOverride]:
        stmt = select(EntitlementOverride).where(EntitlementOverride.user_id == user_id).order_by(EntitlementOverride.created_at.desc()).limit(limit)
        return list((await self.session.scalars(stmt)).all())
