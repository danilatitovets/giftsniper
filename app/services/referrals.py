from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import quote

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.referral_constants import (
    REFERRAL_BONUS_EVERY_N_REWARD,
    REFERRAL_BONUS_EVERY_N_USERS,
    REFERRAL_BONUS_PER_USER,
    REFERRAL_START_PREFIX,
)
from app.db.models import User, UserReferral
from app.db.repositories.referrals import ReferralRepository

logger = logging.getLogger(__name__)

_REF_PAYLOAD_RE = re.compile(r"^ref_(\d{1,20})$", re.ASCII)


class ReferralResult(str, Enum):
    SUCCESS = "success"
    IGNORED_EXISTING_USER = "ignored_existing_user"
    IGNORED_SELF_REFERRAL = "ignored_self_referral"
    IGNORED_INVALID_REFERRER = "ignored_invalid_referrer"
    IGNORED_DUPLICATE = "ignored_duplicate"
    IGNORED_NO_PAYLOAD = "ignored_no_payload"


@dataclass(frozen=True)
class ReferralStats:
    invited_count: int
    bonus_checks_available: int


def build_referral_link(*, telegram_id: int, bot_username: str) -> str:
    u = (bot_username or "").strip().lstrip("@")
    return f"https://t.me/{u}?start={REFERRAL_START_PREFIX}{int(telegram_id)}"


def build_referral_share_url(*, ref_link: str, share_text: str) -> str:
    return "https://t.me/share/url?url=" + quote(ref_link, safe="") + "&text=" + quote(share_text, safe="")


def parse_referrer_telegram_id_from_start_payload(payload: str) -> int | None:
    raw = (payload or "").strip()
    m = _REF_PAYLOAD_RE.match(raw)
    if not m:
        return None
    return int(m.group(1))


async def get_bonus_checks(session: AsyncSession, user_id: int) -> int:
    stmt = select(User.bonus_checks_available).where(User.id == user_id)
    v = await session.scalar(stmt)
    return int(v or 0)


async def consume_bonus_check_if_available(session: AsyncSession, user_id: int) -> bool:
    res = await session.execute(
        update(User)
        .where(User.id == user_id, User.bonus_checks_available > 0)
        .values(bonus_checks_available=User.bonus_checks_available - 1)
        .returning(User.bonus_checks_available)
    )
    row = res.first()
    ok = row is not None
    if ok:
        logger.info("bonus_check_consumed user_id=%s remaining=%s", user_id, row[0])
    return ok


async def get_referral_stats(session: AsyncSession, user_id: int) -> ReferralStats:
    invited = await ReferralRepository(session).count_by_referrer(user_id)
    bonus = await get_bonus_checks(session, user_id)
    return ReferralStats(invited_count=invited, bonus_checks_available=bonus)


async def handle_referral_start(
    session: AsyncSession,
    *,
    invited_user: User,
    start_payload: str,
    user_was_created: bool,
) -> ReferralResult:
    payload = (start_payload or "").strip()
    if not payload.startswith(REFERRAL_START_PREFIX):
        return ReferralResult.IGNORED_NO_PAYLOAD

    if not user_was_created:
        logger.info("referral_ignored_existing_user invited_user_id=%s payload=%s", invited_user.id, payload[:80])
        return ReferralResult.IGNORED_EXISTING_USER

    ref_tid = parse_referrer_telegram_id_from_start_payload(payload)
    if ref_tid is None:
        logger.info("referral_start_detected ignored_non_numeric payload=%s", payload[:80])
        return ReferralResult.IGNORED_NO_PAYLOAD

    logger.info("referral_start_detected invited_user_id=%s ref_telegram_id=%s", invited_user.id, ref_tid)

    if int(invited_user.telegram_id) == int(ref_tid):
        logger.info("referral_ignored_self invited_user_id=%s", invited_user.id)
        return ReferralResult.IGNORED_SELF_REFERRAL

    stmt = select(User).where(User.telegram_id == ref_tid)
    referrer = await session.scalar(stmt)
    if referrer is None:
        logger.info("referral_ignored_invalid_referrer ref_telegram_id=%s", ref_tid)
        return ReferralResult.IGNORED_INVALID_REFERRER

    per = int(REFERRAL_BONUS_PER_USER)
    milestone_extra = 0
    milestone_row = 0

    row = UserReferral(
        referrer_user_id=int(referrer.id),
        invited_user_id=int(invited_user.id),
        bonus_awarded_checks=per,
        milestone_awarded_checks=0,
        source_payload=payload[:512],
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
    except IntegrityError:
        await session.rollback()
        logger.info("referral_ignored_duplicate invited_user_id=%s", invited_user.id)
        return ReferralResult.IGNORED_DUPLICATE

    repo = ReferralRepository(session)
    n = await repo.count_by_referrer(int(referrer.id))
    if n > 0 and n % int(REFERRAL_BONUS_EVERY_N_USERS) == 0:
        milestone_extra = int(REFERRAL_BONUS_EVERY_N_REWARD)
        milestone_row = milestone_extra
        row.milestone_awarded_checks = milestone_row

    total_bonus = per + milestone_extra
    await repo.add_bonus_checks(int(referrer.id), total_bonus)
    logger.info(
        "referral_awarded referrer_user_id=%s invited_user_id=%s per=%s milestone=%s total=%s count=%s",
        referrer.id,
        invited_user.id,
        per,
        milestone_extra,
        total_bonus,
        n,
    )
    return ReferralResult.SUCCESS


async def award_referral_bonus(referrer_user_id: int, invited_user_id: int) -> None:
    """Зарезервировано под будущие сценарии; MVP использует handle_referral_start."""
    _ = (referrer_user_id, invited_user_id)
