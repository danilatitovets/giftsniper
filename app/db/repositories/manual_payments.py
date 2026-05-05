from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ManualPaymentRequest


class ManualPaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_payment_request(
        self,
        *,
        user_id: int,
        requested_plan: str,
        amount: float | None,
        currency: str,
        wallet_address: str,
        expires_at: datetime | None,
    ) -> ManualPaymentRequest:
        row = ManualPaymentRequest(
            user_id=user_id,
            requested_plan=requested_plan,
            amount=amount,
            currency=currency,
            wallet_address=wallet_address,
            status="pending",
            expires_at=expires_at,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_by_id(self, request_id: int) -> ManualPaymentRequest | None:
        return await self.session.get(ManualPaymentRequest, request_id)

    async def get_user_request(self, user_id: int, request_id: int) -> ManualPaymentRequest | None:
        stmt = select(ManualPaymentRequest).where(ManualPaymentRequest.user_id == user_id, ManualPaymentRequest.id == request_id)
        return await self.session.scalar(stmt)

    async def get_by_tx_hash(self, tx_hash: str) -> ManualPaymentRequest | None:
        stmt = select(ManualPaymentRequest).where(ManualPaymentRequest.tx_hash == tx_hash)
        return await self.session.scalar(stmt)

    async def submit_payment_proof(self, user_id: int, request_id: int, tx_hash_or_text: str) -> ManualPaymentRequest | None:
        row = await self.get_user_request(user_id, request_id)
        if row is None:
            return None
        row.status = "submitted"
        value = tx_hash_or_text.strip()
        if len(value) <= 255 and " " not in value:
            row.tx_hash = value
        else:
            row.proof_text = value[:3900]
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def confirm_payment_request(self, admin_user_id: int, request_id: int, note: str | None) -> ManualPaymentRequest | None:
        row = await self.get_by_id(request_id)
        if row is None:
            return None
        row.status = "confirmed"
        row.confirmed_by_user_id = admin_user_id
        row.reviewed_by_user_id = admin_user_id
        row.reviewed_at = datetime.now(timezone.utc)
        row.confirmed_at = datetime.now(timezone.utc)
        row.admin_note = note
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def reject_payment_request(self, admin_user_id: int, request_id: int, reason: str) -> ManualPaymentRequest | None:
        row = await self.get_by_id(request_id)
        if row is None:
            return None
        row.status = "rejected"
        row.confirmed_by_user_id = admin_user_id
        row.reviewed_by_user_id = admin_user_id
        row.reviewed_at = datetime.now(timezone.utc)
        row.rejected_at = datetime.now(timezone.utc)
        row.admin_note = reason[:3900]
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_pending_payment_requests(self) -> list[ManualPaymentRequest]:
        stmt = (
            select(ManualPaymentRequest)
            .where(ManualPaymentRequest.status.in_(["pending", "submitted"]))
            .order_by(ManualPaymentRequest.created_at.desc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def list_by_status(self, statuses: list[str], limit: int = 50) -> list[ManualPaymentRequest]:
        stmt = (
            select(ManualPaymentRequest)
            .where(ManualPaymentRequest.status.in_(statuses))
            .order_by(ManualPaymentRequest.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())

    async def list_stale_submitted(self, older_than: datetime, limit: int = 50) -> list[ManualPaymentRequest]:
        stmt = (
            select(ManualPaymentRequest)
            .where(ManualPaymentRequest.status == "submitted", ManualPaymentRequest.created_at <= older_than)
            .order_by(ManualPaymentRequest.created_at.asc())
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())

    async def search(self, query: str, limit: int = 50) -> list[ManualPaymentRequest]:
        q = query.strip()
        clauses = [
            ManualPaymentRequest.tx_hash.ilike(f"%{q}%"),
            ManualPaymentRequest.requested_plan.ilike(f"%{q}%"),
            ManualPaymentRequest.status.ilike(f"%{q}%"),
            ManualPaymentRequest.proof_text.ilike(f"%{q}%"),
        ]
        if q.isdigit():
            clauses.extend([ManualPaymentRequest.id == int(q), ManualPaymentRequest.user_id == int(q)])
        stmt = select(ManualPaymentRequest).where(or_(*clauses)).order_by(ManualPaymentRequest.created_at.desc()).limit(limit)
        return list((await self.session.scalars(stmt)).all())

    async def expire_pending_older_than(self, older_than: datetime) -> list[ManualPaymentRequest]:
        stmt = select(ManualPaymentRequest).where(ManualPaymentRequest.status == "pending", ManualPaymentRequest.created_at <= older_than)
        rows = list((await self.session.scalars(stmt)).all())
        for row in rows:
            row.status = "expired"
        if rows:
            await self.session.commit()
        return rows

    async def list_user_payment_requests(self, user_id: int, limit: int = 20) -> list[ManualPaymentRequest]:
        stmt = (
            select(ManualPaymentRequest)
            .where(ManualPaymentRequest.user_id == user_id)
            .order_by(ManualPaymentRequest.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())
