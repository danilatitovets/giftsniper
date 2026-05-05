from __future__ import annotations

import datetime as dt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TonPaymentConsumedTx, TonSubscriptionPayment, UserNftCheckDay


def utc_today() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


class UserNftCheckDayRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_count(self, user_id: int, day: dt.date | None = None) -> int:
        d = day or utc_today()
        stmt = select(UserNftCheckDay.checks_count).where(UserNftCheckDay.user_id == user_id, UserNftCheckDay.day == d)
        v = await self.session.scalar(stmt)
        return int(v or 0)

    async def increment(self, user_id: int, day: dt.date | None = None) -> int:
        d = day or utc_today()
        row = await self.session.scalar(
            select(UserNftCheckDay).where(UserNftCheckDay.user_id == user_id, UserNftCheckDay.day == d)
        )
        if row is None:
            row = UserNftCheckDay(user_id=user_id, day=d, checks_count=1)
            self.session.add(row)
        else:
            row.checks_count = int(row.checks_count or 0) + 1
        await self.session.commit()
        await self.session.refresh(row)
        return int(row.checks_count)


class TonSubscriptionPaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _as_utc_naive(x: dt.datetime) -> dt.datetime:
        if x.tzinfo is None:
            return x
        return x.astimezone(dt.timezone.utc).replace(tzinfo=None)

    async def create_pending(
        self,
        *,
        user_id: int,
        plan: str,
        amount_ton: float,
        amount_nano: int,
        receiver_address: str,
        comment: str,
        expires_at: dt.datetime,
    ) -> TonSubscriptionPayment:
        now = dt.datetime.utcnow()
        expires = self._as_utc_naive(expires_at)
        row = TonSubscriptionPayment(
            user_id=user_id,
            plan=plan,
            amount_ton=amount_ton,
            amount_nano=amount_nano,
            receiver_address=receiver_address,
            comment=comment,
            status="pending",
            created_at=now,
            expires_at=expires,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_by_id(self, payment_id: int) -> TonSubscriptionPayment | None:
        return await self.session.get(TonSubscriptionPayment, payment_id)

    async def get_by_id_for_user(self, payment_id: int, user_id: int) -> TonSubscriptionPayment | None:
        stmt = select(TonSubscriptionPayment).where(
            TonSubscriptionPayment.id == payment_id,
            TonSubscriptionPayment.user_id == user_id,
        )
        return await self.session.scalar(stmt)

    async def mark_expired(self, row: TonSubscriptionPayment) -> None:
        row.status = "expired"
        await self.session.commit()

    async def mark_cancelled(self, row: TonSubscriptionPayment) -> None:
        row.status = "cancelled"
        await self.session.commit()

    async def mark_paid(self, row: TonSubscriptionPayment, tx_hash: str, paid_at: dt.datetime) -> None:
        row.status = "paid"
        row.tx_hash = tx_hash
        row.paid_at = self._as_utc_naive(paid_at)
        await self.session.commit()

    async def finalize_paid_and_record_tx(self, row: TonSubscriptionPayment, tx_hash: str, paid_at: dt.datetime) -> None:
        paid = self._as_utc_naive(paid_at)
        row.status = "paid"
        row.tx_hash = tx_hash
        row.paid_at = paid
        self.session.add(TonPaymentConsumedTx(tx_hash=tx_hash, payment_id=row.id, consumed_at=paid))
        await self.session.commit()

    async def is_tx_consumed(self, tx_hash: str) -> bool:
        stmt = select(TonPaymentConsumedTx.tx_hash).where(TonPaymentConsumedTx.tx_hash == tx_hash)
        return await self.session.scalar(stmt) is not None

    async def list_recent_pending_for_receiver(
        self, receiver: str, limit: int = 50
    ) -> list[TonSubscriptionPayment]:
        stmt = (
            select(TonSubscriptionPayment)
            .where(
                TonSubscriptionPayment.receiver_address == receiver,
                TonSubscriptionPayment.status == "pending",
            )
            .order_by(TonSubscriptionPayment.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_last_paid_for_user(self, user_id: int) -> TonSubscriptionPayment | None:
        stmt = (
            select(TonSubscriptionPayment)
            .where(
                TonSubscriptionPayment.user_id == user_id,
                TonSubscriptionPayment.status == "paid",
            )
            .order_by(TonSubscriptionPayment.paid_at.desc(), TonSubscriptionPayment.id.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)
