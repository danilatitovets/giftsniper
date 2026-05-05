from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FeedbackItem


class FeedbackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_item(
        self,
        *,
        user_id: int,
        item_type: str,
        message: str,
        signal_snapshot_id: int | None = None,
        signal_rating: str | None = None,
        outcome_hint: str | None = None,
        reviewer_note: str | None = None,
    ) -> FeedbackItem:
        row = FeedbackItem(
            user_id=user_id,
            type=item_type,
            message=message[:3900],
            status="new",
            signal_snapshot_id=signal_snapshot_id,
            signal_rating=signal_rating,
            outcome_hint=outcome_hint,
            reviewer_note=(reviewer_note[:1900] if reviewer_note else None),
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_by_id(self, item_id: int) -> FeedbackItem | None:
        return await self.session.get(FeedbackItem, item_id)

    async def list_items(self, limit: int = 30) -> list[FeedbackItem]:
        stmt = select(FeedbackItem).order_by(FeedbackItem.created_at.desc()).limit(limit)
        return list((await self.session.scalars(stmt)).all())

    async def close_item(self, item_id: int, admin_note: str | None) -> FeedbackItem | None:
        row = await self.get_by_id(item_id)
        if row is None:
            return None
        row.status = "closed"
        row.admin_note = (admin_note or "")[:1900] or row.admin_note
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def review_item(
        self,
        item_id: int,
        *,
        reviewer_user_id: int,
        priority: str | None = None,
        note: str | None = None,
    ) -> FeedbackItem | None:
        row = await self.get_by_id(item_id)
        if row is None:
            return None
        if priority:
            row.priority = priority
        row.reviewed_by_user_id = reviewer_user_id
        row.reviewed_at = datetime.now(timezone.utc)
        row.status = "reviewed"
        if note:
            row.admin_note = note[:1900]
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def set_priority(self, item_id: int, priority: str) -> FeedbackItem | None:
        row = await self.get_by_id(item_id)
        if row is None:
            return None
        row.priority = priority
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_signal_feedback(self, limit: int = 20) -> list[FeedbackItem]:
        stmt = (
            select(FeedbackItem)
            .where(
                FeedbackItem.type.in_(
                    [
                        "signal_good",
                        "signal_bad",
                        "signal_unclear",
                        "signal_outcome",
                        "signal_feedback",
                        "admin_signal_review",
                        "deal_case",
                    ]
                )
            )
            .order_by(FeedbackItem.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())

    async def calculate_sla_metrics(self) -> dict:
        now = datetime.now(timezone.utc)
        new_count = int(await self.session.scalar(select(func.count(FeedbackItem.id)).where(FeedbackItem.status == "new")) or 0)
        urgent_high_count = int(
            await self.session.scalar(select(func.count(FeedbackItem.id)).where(FeedbackItem.priority.in_(["urgent", "high"]), FeedbackItem.status != "closed"))
            or 0
        )
        oldest_new = await self.session.scalar(
            select(FeedbackItem).where(FeedbackItem.status == "new").order_by(FeedbackItem.created_at.asc()).limit(1)
        )
        closed_rows = (
            await self.session.execute(
                select(FeedbackItem.created_at, FeedbackItem.updated_at).where(FeedbackItem.status == "closed", FeedbackItem.reviewed_at.is_not(None))
            )
        ).all()
        avg_close_hours = 0.0
        if closed_rows:
            total_seconds = 0.0
            for created_at, updated_at in closed_rows:
                c = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
                u = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=timezone.utc)
                total_seconds += max((u - c).total_seconds(), 0.0)
            avg_close_hours = total_seconds / len(closed_rows) / 3600.0
        overdue_cutoff = now - timedelta(hours=48)
        overdue = int(
            await self.session.scalar(select(func.count(FeedbackItem.id)).where(FeedbackItem.status != "closed", FeedbackItem.created_at < overdue_cutoff))
            or 0
        )
        oldest_age = "n/a"
        if oldest_new is not None:
            created = oldest_new.created_at if oldest_new.created_at.tzinfo else oldest_new.created_at.replace(tzinfo=timezone.utc)
            age_hours = int((now - created).total_seconds() // 3600)
            oldest_age = f"{age_hours}h"
        return {
            "new_feedback_count": new_count,
            "urgent_high_count": urgent_high_count,
            "oldest_new_feedback_age": oldest_age,
            "average_close_time_hours": avg_close_hours,
            "overdue_feedback_48h": overdue,
        }

    async def count_new(self) -> int:
        return int(await self.session.scalar(select(func.count(FeedbackItem.id)).where(FeedbackItem.status == "new")) or 0)

    async def count_by_user(self, user_id: int) -> int:
        return int(await self.session.scalar(select(func.count(FeedbackItem.id)).where(FeedbackItem.user_id == user_id)) or 0)

    async def list_linked_feedback_for_snapshots(self, snapshot_ids: list[int]) -> list[FeedbackItem]:
        if not snapshot_ids:
            return []
        stmt = select(FeedbackItem).where(FeedbackItem.signal_snapshot_id.in_(snapshot_ids))
        return list((await self.session.scalars(stmt)).all())

    async def list_outcome_feedback(self, *, limit: int = 40) -> list[FeedbackItem]:
        stmt = (
            select(FeedbackItem)
            .where(FeedbackItem.type == "signal_outcome")
            .order_by(FeedbackItem.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())
