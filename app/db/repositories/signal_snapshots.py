from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FeedbackItem, SignalSnapshot, TradeJournal


class SignalSnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **fields) -> SignalSnapshot:
        row = SignalSnapshot(**fields)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_for_user(self, snapshot_id: int, user_id: int) -> SignalSnapshot | None:
        r = await self.session.execute(
            select(SignalSnapshot).where(SignalSnapshot.id == snapshot_id, SignalSnapshot.user_id == user_id)
        )
        return r.scalar_one_or_none()

    async def get_by_id(self, snapshot_id: int) -> SignalSnapshot | None:
        return await self.session.get(SignalSnapshot, snapshot_id)

    async def list_recent_for_user(self, user_id: int, *, limit: int = 10) -> list[SignalSnapshot]:
        r = await self.session.execute(
            select(SignalSnapshot)
            .where(SignalSnapshot.user_id == user_id)
            .order_by(SignalSnapshot.id.desc())
            .limit(limit)
        )
        return list(r.scalars().all())

    async def list_recent_global(self, *, limit: int = 200) -> list[SignalSnapshot]:
        r = await self.session.execute(select(SignalSnapshot).order_by(SignalSnapshot.id.desc()).limit(limit))
        return list(r.scalars().all())

    async def count_since(self, *, user_id: int | None, days: int) -> int:
        since = datetime.utcnow() - timedelta(days=days)
        stmt = select(func.count(SignalSnapshot.id)).where(SignalSnapshot.created_at >= since)
        if user_id is not None:
            stmt = stmt.where(SignalSnapshot.user_id == user_id)
        return int(await self.session.scalar(stmt) or 0)

    async def count_closed_trades_since(self, days: int) -> int:
        since = datetime.utcnow() - timedelta(days=days)
        stmt = select(func.count(TradeJournal.id)).where(
            TradeJournal.status == "sold",
            TradeJournal.sell_date.is_not(None),
            TradeJournal.sell_date >= since,
        )
        return int(await self.session.scalar(stmt) or 0)

    async def count_linked_bad_good_signals(self, days: int) -> tuple[int, int, int]:
        """Counts feedback rows with snapshot link and rating good/bad (7d window on feedback)."""
        since = datetime.utcnow() - timedelta(days=days)
        good = int(
            await self.session.scalar(
                select(func.count(FeedbackItem.id)).where(
                    FeedbackItem.signal_snapshot_id.is_not(None),
                    FeedbackItem.created_at >= since,
                    FeedbackItem.signal_rating == "good",
                )
            )
            or 0
        )
        bad = int(
            await self.session.scalar(
                select(func.count(FeedbackItem.id)).where(
                    FeedbackItem.signal_snapshot_id.is_not(None),
                    FeedbackItem.created_at >= since,
                    FeedbackItem.signal_rating == "bad",
                )
            )
            or 0
        )
        unclear = int(
            await self.session.scalar(
                select(func.count(FeedbackItem.id)).where(
                    FeedbackItem.signal_snapshot_id.is_not(None),
                    FeedbackItem.created_at >= since,
                    FeedbackItem.signal_rating == "unclear",
                )
            )
            or 0
        )
        return good, bad, unclear

    async def count_trades_linked_to_signals(self) -> int:
        stmt = select(func.count(TradeJournal.id)).where(TradeJournal.signal_snapshot_id.is_not(None))
        return int(await self.session.scalar(stmt) or 0)

    async def count_closed_trades(self) -> int:
        stmt = select(func.count(TradeJournal.id)).where(TradeJournal.status == "sold")
        return int(await self.session.scalar(stmt) or 0)
