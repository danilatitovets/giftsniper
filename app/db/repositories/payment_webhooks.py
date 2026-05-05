from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PaymentWebhookEvent


class PaymentWebhookRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_webhook_event(
        self,
        *,
        provider: str,
        provider_event_id: str | None,
        event_type: str | None,
        status: str,
        signature_valid: bool,
        user_id: int | None,
        plan: str | None,
        amount: float | None,
        currency: str | None,
        sanitized_payload_json: str | None,
        sanitized_headers_json: str | None,
    ) -> PaymentWebhookEvent:
        row = PaymentWebhookEvent(
            provider=provider,
            provider_event_id=provider_event_id,
            event_type=event_type,
            status=status,
            signature_valid=signature_valid,
            user_id=user_id,
            plan=plan,
            amount=amount,
            currency=currency,
            sanitized_payload_json=sanitized_payload_json,
            sanitized_headers_json=sanitized_headers_json,
            attempts=0,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_by_provider_event_id(self, provider: str, provider_event_id: str) -> PaymentWebhookEvent | None:
        stmt = select(PaymentWebhookEvent).where(
            PaymentWebhookEvent.provider == provider,
            PaymentWebhookEvent.provider_event_id == provider_event_id,
        )
        return await self.session.scalar(stmt)

    async def get_by_id(self, event_id: int) -> PaymentWebhookEvent | None:
        return await self.session.get(PaymentWebhookEvent, event_id)

    async def mark_processing(self, event_id: int) -> PaymentWebhookEvent | None:
        row = await self.get_by_id(event_id)
        if row is None:
            return None
        row.status = "processing"
        row.attempts += 1
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def mark_processed(self, event_id: int) -> PaymentWebhookEvent | None:
        row = await self.get_by_id(event_id)
        if row is None:
            return None
        row.status = "processed"
        row.processed_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def mark_duplicate(self, event_id: int) -> PaymentWebhookEvent | None:
        row = await self.get_by_id(event_id)
        if row is None:
            return None
        row.status = "duplicate"
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def mark_failed(self, event_id: int, error: str) -> PaymentWebhookEvent | None:
        row = await self.get_by_id(event_id)
        if row is None:
            return None
        row.status = "failed"
        row.last_error = error[:1800]
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def mark_dead_letter(self, event_id: int, error: str) -> PaymentWebhookEvent | None:
        row = await self.get_by_id(event_id)
        if row is None:
            return None
        row.status = "dead_letter"
        row.last_error = error[:1800]
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_recent_webhook_events(self, limit: int = 20) -> list[PaymentWebhookEvent]:
        stmt = select(PaymentWebhookEvent).order_by(PaymentWebhookEvent.created_at.desc()).limit(limit)
        return list((await self.session.scalars(stmt)).all())

    async def list_failed_webhook_events(self, limit: int = 20) -> list[PaymentWebhookEvent]:
        stmt = (
            select(PaymentWebhookEvent)
            .where(PaymentWebhookEvent.status.in_(["failed", "dead_letter"]))
            .order_by(PaymentWebhookEvent.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())
