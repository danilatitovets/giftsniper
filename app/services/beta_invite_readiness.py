"""Beta invite readiness helpers (read-only, no external I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BetaInvite


@dataclass
class BetaInviteReadiness:
    active_rows: int
    valid_active_invites: int
    expired_still_flagged_active: int
    remaining_redemptions_capacity: int
    total_redemptions_all_time: int
    require_invite_gate: bool
    blocking_no_valid_invite: bool


def _now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def count_valid_active_invites(session: AsyncSession) -> int:
    now = _now_utc_naive()
    return int(
        await session.scalar(
            select(func.count(BetaInvite.id)).where(
                BetaInvite.is_active.is_(True),
                or_(BetaInvite.expires_at.is_(None), BetaInvite.expires_at >= now),
            )
        )
        or 0
    )


async def count_expired_still_active(session: AsyncSession) -> int:
    now = _now_utc_naive()
    return int(
        await session.scalar(
            select(func.count(BetaInvite.id)).where(
                BetaInvite.is_active.is_(True),
                BetaInvite.expires_at.is_not(None),
                BetaInvite.expires_at < now,
            )
        )
        or 0
    )


async def remaining_invite_capacity(session: AsyncSession) -> int:
    now = _now_utc_naive()
    rows = (
        await session.scalars(
            select(BetaInvite).where(
                BetaInvite.is_active.is_(True),
                or_(BetaInvite.expires_at.is_(None), BetaInvite.expires_at >= now),
            )
        )
    ).all()
    total = 0
    for row in rows:
        total += max(0, int(row.max_uses) - int(row.used_count))
    return total


async def build_beta_invite_readiness(session: AsyncSession, settings) -> BetaInviteReadiness:
    valid = await count_valid_active_invites(session)
    expired_bad = await count_expired_still_active(session)
    raw_active = int(await session.scalar(select(func.count(BetaInvite.id)).where(BetaInvite.is_active.is_(True))) or 0)
    capacity = await remaining_invite_capacity(session)
    from app.db.repositories.beta_invites import BetaInviteRepository

    redemptions = await BetaInviteRepository(session).count_redemptions()
    gate = bool(getattr(settings, "beta_require_invite", True))
    blocking = gate and valid == 0
    return BetaInviteReadiness(
        active_rows=raw_active,
        valid_active_invites=valid,
        expired_still_flagged_active=expired_bad,
        remaining_redemptions_capacity=capacity,
        total_redemptions_all_time=redemptions,
        require_invite_gate=gate,
        blocking_no_valid_invite=blocking,
    )
