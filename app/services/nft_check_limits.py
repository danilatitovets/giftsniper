"""Дневной лимит проверок NFT по тарифу + бонусные проверки (рефералка)."""

from __future__ import annotations

from aiogram.types import Message

from app.bot.upgrade_inline import daily_check_limit_keyboard, format_daily_checks_limit_message
from app.db.repositories.ton_payments import UserNftCheckDayRepository
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.i18n import t, text_lang_from_user
from app.services.feature_limits import checks_per_day_limit
from app.services.referrals import consume_bonus_check_if_available, get_bonus_checks


async def assert_nft_daily_check_allowed(message: Message, telegram_id: int, username: str | None) -> bool:
    """Если дневной лимит исчерпан и нет бонусных проверок — отвечает в чат и возвращает False."""
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(telegram_id, username)
        role = (getattr(user, "role", "") or "").lower()
        if role in {"admin", "owner"}:
            return True
        limit = checks_per_day_limit(user)
        used = await UserNftCheckDayRepository(session).get_count(user.id)
        if used < limit:
            return True
        bonus = await get_bonus_checks(session, user.id)
        if bonus > 0:
            return True
        lang = text_lang_from_user(user)
        await message.answer(
            format_daily_checks_limit_message(limit, lang=lang),
            reply_markup=daily_check_limit_keyboard(lang=lang),
        )
        return False


async def record_successful_nft_check(
    telegram_id: int,
    username: str | None,
    *,
    notify_message: Message | None = None,
) -> int | None:
    """Учитывает успешную проверку: дневной счётчик или списание бонуса.

    Возвращает остаток бонусных проверок, если было списание бонуса; иначе None.
    """
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(telegram_id, username)
        role = (getattr(user, "role", "") or "").lower()
        if role in {"admin", "owner"}:
            return None
        limit = checks_per_day_limit(user)
        used = await UserNftCheckDayRepository(session).get_count(user.id)
        if used < limit:
            await UserNftCheckDayRepository(session).increment(user.id)
            await session.commit()
            return None
        consumed = await consume_bonus_check_if_available(session, user.id)
        if not consumed:
            await session.rollback()
            return None
        lang = text_lang_from_user(user)
        remaining = await get_bonus_checks(session, user.id)
        await session.commit()
        if notify_message is not None:
            try:
                await notify_message.answer(t("referral.bonus_check_used", lang).format(remaining=remaining))
            except Exception:
                pass
        return remaining
