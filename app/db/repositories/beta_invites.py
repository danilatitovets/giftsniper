from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BetaInvite, BetaInviteRedemption


class BetaInviteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_invite(
        self,
        *,
        code: str,
        plan: str = "pro",
        days: int = 14,
        max_uses: int = 1,
        created_by_user_id: int | None = None,
    ) -> BetaInvite:
        row = BetaInvite(
            code=code.lower().strip(),
            plan=plan.lower().strip(),
            days=days,
            max_uses=max_uses,
            created_by_user_id=created_by_user_id,
            is_active=True,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_by_code(self, code: str) -> BetaInvite | None:
        stmt = select(BetaInvite).where(BetaInvite.code == code.lower().strip())
        return await self.session.scalar(stmt)

    async def list_active(self, limit: int = 100) -> list[BetaInvite]:
        stmt = (
            select(BetaInvite)
            .where(BetaInvite.is_active.is_(True))
            .order_by(BetaInvite.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())

    async def disable_invite(self, code: str) -> bool:
        row = await self.get_by_code(code)
        if row is None:
            return False
        row.is_active = False
        await self.session.commit()
        return True

    async def can_redeem(self, invite: BetaInvite, user_id: int) -> tuple[bool, str | None]:
        if not invite.is_active:
            return False, "Invite code отключен."
        now = datetime.now(timezone.utc)
        exp = invite.expires_at if invite.expires_at and invite.expires_at.tzinfo else (
            invite.expires_at.replace(tzinfo=timezone.utc) if invite.expires_at else None
        )
        if exp and exp < now:
            return False, "Invite code истек."
        if invite.used_count >= invite.max_uses:
            return False, "Invite code исчерпан."
        stmt = select(BetaInviteRedemption).where(BetaInviteRedemption.invite_id == invite.id, BetaInviteRedemption.user_id == user_id)
        existing = await self.session.scalar(stmt)
        if existing is not None:
            return False, "Вы уже активировали этот invite code."
        return True, None

    async def redeem(self, invite: BetaInvite, user_id: int) -> BetaInviteRedemption:
        invite.used_count += 1
        redemption = BetaInviteRedemption(invite_id=invite.id, user_id=user_id)
        self.session.add(redemption)
        await self.session.commit()
        await self.session.refresh(redemption)
        return redemption

    async def count_active(self) -> int:
        return int(await self.session.scalar(select(func.count(BetaInvite.id)).where(BetaInvite.is_active.is_(True))) or 0)

    async def count_redemptions(self) -> int:
        return int(await self.session.scalar(select(func.count(BetaInviteRedemption.id))) or 0)

    async def has_user_redemption(self, user_id: int) -> bool:
        stmt = select(BetaInviteRedemption.id).where(BetaInviteRedemption.user_id == user_id).limit(1)
        return (await self.session.scalar(stmt)) is not None
