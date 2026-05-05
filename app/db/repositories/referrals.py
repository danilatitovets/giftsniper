from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, UserReferral


class ReferralRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count_by_referrer(self, referrer_user_id: int) -> int:
        stmt = select(func.count(UserReferral.id)).where(UserReferral.referrer_user_id == referrer_user_id)
        return int(await self.session.scalar(stmt) or 0)

    async def add_bonus_checks(self, user_id: int, delta: int) -> None:
        if delta == 0:
            return
        await self.session.execute(
            update(User).where(User.id == user_id).values(bonus_checks_available=User.bonus_checks_available + int(delta))
        )
