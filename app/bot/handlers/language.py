"""Выбор языка: callback ``lang:set:xx``."""

from __future__ import annotations

import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile

from app.bot.keyboards import CB_SETTINGS_LANGUAGE, start_hub_inline_keyboard
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.i18n import LANGUAGES, language_selector_keyboard, normalize_lang, t

logger = logging.getLogger(__name__)

router = Router()
_REPO_ROOT = Path(__file__).resolve().parents[3]
_HERO_IMAGE_PATH = _REPO_ROOT / "imagen" / "hero.png"


async def _answer_start_main_with_hero(message, *, text: str, kb) -> None:
    if _HERO_IMAGE_PATH.exists():
        try:
            await message.answer_photo(
                photo=FSInputFile(str(_HERO_IMAGE_PATH)),
                caption=text[:1024],
                reply_markup=kb,
            )
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("lang:set:"))
async def language_set_callback(query: CallbackQuery) -> None:
    if not query.from_user:
        await query.answer()
        return
    raw = (query.data or "").split(":")[-1]
    code = normalize_lang(raw)
    async with SessionLocal() as session:
        user = await UserRepository(session).set_language_code(
            query.from_user.id, code, username=query.from_user.username
        )
    is_adm = user.role in {"admin", "owner"}
    title = LANGUAGES.get(code, LANGUAGES["en"])["title"]
    confirm = t("settings.language_confirm", code, title=title)
    main_text = t("start.main", code)
    kb = start_hub_inline_keyboard(lang=code)
    await query.answer()
    if query.message:
        try:
            await query.message.edit_text(confirm)
        except Exception as exc:
            logger.debug("language confirm edit_text: %s", exc)
            await query.message.answer(confirm)
        try:
            await _answer_start_main_with_hero(query.message, text=main_text, kb=kb)
        except Exception:
            pass
    else:
        if query.bot and query.from_user:
            await query.bot.send_message(
                query.from_user.id,
                f"{confirm}\n\n{main_text}",
                reply_markup=kb,
            )


@router.callback_query(F.data == CB_SETTINGS_LANGUAGE)
async def settings_language_open(query: CallbackQuery) -> None:
    await query.answer()
    txt = t("onboarding.choose_language", "en")
    kb = language_selector_keyboard()
    if query.message:
        try:
            await query.message.edit_text(txt, reply_markup=kb)
        except Exception as exc:
            logger.debug("settings language edit_text: %s", exc)
            await query.message.answer(txt, reply_markup=kb)
