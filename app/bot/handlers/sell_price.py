"""Full-market NFT listing hints via TonAPI only (no mock)."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import get_settings
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.i18n import text_lang_from_user
from app.services.nft_check_limits import assert_nft_daily_check_allowed, record_successful_nft_check
from app.services.real_market_collection_scan import (
    format_full_market_nft_report,
    format_progress_message,
    run_full_market_analysis_flow,
)
from app.services.tonapi_collection_client import TonAPICollectionClient

logger = logging.getLogger(__name__)

router = Router()


def _command_payload(message: Message, *commands: str) -> str:
    parts = (message.text or "").split(maxsplit=1)
    if not parts:
        return ""
    cmd = parts[0].split("@", 1)[0].lower()
    if cmd not in commands:
        return ""
    return parts[1].strip() if len(parts) > 1 else ""


async def _execute_sell_price_flow(
    message: Message,
    payload: str,
    *,
    telegram_id: int | None = None,
    username: str | None = None,
) -> None:
    settings = get_settings()
    text = payload.strip()
    if not text:
        await message.answer(
            "Используйте: /sell_price <NFT address | ссылка | Ice Cream #217467>\n"
            "Алиасы: /price_nft /value_nft"
        )
        return

    uid = telegram_id if telegram_id is not None else message.from_user.id
    uname = username if username is not None else message.from_user.username
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(uid, uname)

    if not await assert_nft_daily_check_allowed(message, uid, uname):
        return

    lang = text_lang_from_user(user)
    client = TonAPICollectionClient(settings)
    progress_msg = await message.answer(format_progress_message("", 0, 0, phase="start", lang=lang))

    async def on_progress(
        coll: str,
        loaded: int,
        listings: int,
        phase: str,
        page_limit: int = 0,
        total_apx: int | None = None,
        note: str | None = None,
    ) -> None:
        try:
            body = format_progress_message(
                coll or "",
                loaded,
                listings,
                phase=phase,
                page_limit=page_limit if page_limit > 0 else None,
                collection_total_approx=total_apx,
                page_limit_note=note,
                lang=lang,
            )
            await message.bot.edit_message_text(
                body,
                chat_id=message.chat.id,
                message_id=progress_msg.message_id,
            )
        except Exception as exc:
            logger.debug("progress edit skipped: %s", exc)

    try:
        report, err = await run_full_market_analysis_flow(
            text,
            user,
            settings,
            client,
            on_progress=on_progress,
        )
    except Exception as exc:
        logger.exception("full market analysis failed")
        err = "Ошибка при обращении к TonAPI. Попробуйте позже."
        report = None

    if err:
        try:
            await message.bot.edit_message_text(
                err[:4000],
                chat_id=message.chat.id,
                message_id=progress_msg.message_id,
            )
        except Exception:
            await message.answer(err[:4000])
        return

    if not report:
        try:
            await message.bot.edit_message_text(
                "Не удалось построить отчёт.",
                chat_id=message.chat.id,
                message_id=progress_msg.message_id,
            )
        except Exception:
            await message.answer("Не удалось построить отчёт.")
        return

    final_text = format_full_market_nft_report(report)
    if len(final_text) > 4090:
        final_text = final_text[:4087] + "…"
    try:
        await message.bot.edit_message_text(
            final_text,
            chat_id=message.chat.id,
            message_id=progress_msg.message_id,
        )
    except Exception:
        await message.answer(final_text)
    await record_successful_nft_check(uid, uname, notify_message=message)


@router.message(Command("sell_price"))
async def sell_price_cmd(message: Message) -> None:
    raw = _command_payload(message, "/sell_price")
    await _execute_sell_price_flow(message, raw)


@router.message(Command("price_nft"))
async def price_nft_cmd(message: Message) -> None:
    raw = _command_payload(message, "/price_nft")
    await _execute_sell_price_flow(message, raw)


@router.message(Command("value_nft"))
async def value_nft_cmd(message: Message) -> None:
    raw = _command_payload(message, "/value_nft")
    await _execute_sell_price_flow(message, raw)
