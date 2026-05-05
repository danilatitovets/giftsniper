from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProductEvent


class ProductEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_event(
        self,
        *,
        user_id: int | None,
        event_type: str,
        command: str | None = None,
        metadata_json: str | None = None,
    ) -> ProductEvent:
        row = ProductEvent(
            user_id=user_id,
            event_type=event_type[:64],
            command=(command or None),
            metadata_json=(metadata_json[:3900] if metadata_json else None),
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_events(self, *, event_type: str | None = None, since: datetime | None = None, limit: int = 100) -> list[ProductEvent]:
        stmt = select(ProductEvent)
        if event_type:
            stmt = stmt.where(ProductEvent.event_type == event_type)
        if since:
            stmt = stmt.where(ProductEvent.created_at >= since)
        stmt = stmt.order_by(ProductEvent.created_at.desc()).limit(limit)
        return list((await self.session.scalars(stmt)).all())

    async def count_events(self, *, event_type: str | None = None, since: datetime | None = None) -> int:
        stmt = select(func.count(ProductEvent.id))
        if event_type:
            stmt = stmt.where(ProductEvent.event_type == event_type)
        if since:
            stmt = stmt.where(ProductEvent.created_at >= since)
        return int(await self.session.scalar(stmt) or 0)
