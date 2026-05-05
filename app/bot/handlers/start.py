import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, Message

from app.bot.handlers.analysis import execute_check_payload
from app.bot.handlers.gifts import send_empty_watchlist_message, send_watchlist_message
from app.bot.handlers.ton_upgrade import send_upgrade_carousel_message
from app.bot.handlers.settings import send_mvp_settings_screen
from app.bot.keyboards import (
    CB_REF_REFRESH,
    CB_START_BACK,
    CB_START_CHECK,
    CB_START_FEATURES,
    CB_START_HELP,
    CB_START_MYLIST,
    CB_START_REFERRAL,
    CB_START_UPGRADE,
    CB_UX_CLOSE_MESSAGE,
    CB_EMPTY_WL_BACK,
    CB_EMPTY_WL_CHECK,
    CB_EMPTY_WL_WATCH,
    CB_NFT_CHECK_BACK,
    CB_NFT_CHECK_CANCEL,
    CB_SETTINGS_STUB_BACK,
    CB_SETTINGS_STUB_CHECK,
    CB_SETTINGS_STUB_WATCHLIST,
    FEATURES_MENU_LABELS,
    HELP_MENU_LABELS,
    MAIN_MENU_ALL_LABELS,
    NFT_CHECK_MENU_LABELS,
    SETTINGS_MENU_LABELS,
    UPGRADE_MENU_LABELS,
    WATCHLIST_MENU_LABELS,
    deserialize_inline_keyboard,
    main_menu_keyboard,
    nft_check_prompt_inline_keyboard,
    serialize_inline_keyboard,
    start_hub_back_only_keyboard,
    start_hub_features_nav_keyboard,
    start_hub_help_nav_keyboard,
    referral_program_inline_keyboard,
    start_hub_inline_keyboard,
    start_info_inline_keyboard,
)
from app.bot.messages import EXAMPLES_TEXT, HOW_IT_WORKS_TEXT, QUICK_START_TEXT, build_commands_text
from app.bot.states import CheckNftFlow
from app.bot.ux import format_next_action, format_plan_badge
from app.config import get_settings
from app.referral_constants import (
    REFERRAL_BONUS_EVERY_N_REWARD,
    REFERRAL_BONUS_EVERY_N_USERS,
    REFERRAL_BONUS_PER_USER,
    REFERRAL_START_PREFIX,
)
from app.db.repositories.alerts import AlertRepository
from app.db.repositories.feedback import FeedbackRepository
from app.db.repositories.gifts import GiftRepository
from app.db.repositories.manual_payments import ManualPaymentRepository
from app.db.repositories.signal_snapshots import SignalSnapshotRepository
from app.db.repositories.trade_journal import TradeJournalRepository
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.i18n import language_selector_keyboard, normalize_lang, t, text_lang_from_user
from app.services import runtime_state
from app.services.feature_limits import can_use_feature, get_plan_limits
from app.services.referrals import build_referral_link, build_referral_share_url, get_referral_stats, handle_referral_start

router = Router()


def _public_bot_username(message: Message) -> str:
    s = get_settings()
    u = (s.public_bot_username or "").strip().lstrip("@")
    if u:
        return u
    try:
        return (message.bot.username or "bot").strip().lstrip("@")
    except Exception:
        return "bot"


async def _referral_screen_parts(message: Message, *, lang: str, user_id: int, telegram_id: int) -> tuple[str, InlineKeyboardMarkup]:
    bot_u = _public_bot_username(message)
    link = build_referral_link(telegram_id=int(telegram_id), bot_username=bot_u)
    share_url = build_referral_share_url(ref_link=link, share_text=t("referral.share_text", lang))
    async with SessionLocal() as session:
        stats = await get_referral_stats(session, user_id)
    body = t("referral.program_body", lang).format(
        link=link,
        per=int(REFERRAL_BONUS_PER_USER),
        every_n=int(REFERRAL_BONUS_EVERY_N_USERS),
        milestone=int(REFERRAL_BONUS_EVERY_N_REWARD),
        invited=int(stats.invited_count),
        bonus=int(stats.bonus_checks_available),
    )
    kb = referral_program_inline_keyboard(lang=lang, ref_link=link, share_url=share_url)
    return body, kb


class ExcludePendingDealPriceMessageFilter(BaseFilter):
    """Пока ждём TON после «💰 Сделка», не отправлять «5» в /check как ссылку на NFT."""

    async def __call__(self, message: Message) -> bool:
        if not message.from_user:
            return True
        if runtime_state.pending_deal_get(message.from_user.id) is None:
            return True
        raw = (message.text or "").strip()
        return re.fullmatch(r"[0-9]+([.,][0-9]+)?\s*(ton)?", raw, flags=re.I) is None
_REPO_ROOT = Path(__file__).resolve().parents[3]
_HERO_IMAGE_PATH = _REPO_ROOT / "imagen" / "hero.png"


def _nft_check_restore_payload(message: Message) -> dict[str, Any]:
    """Текст + inline-клавиатура сообщения для «Назад» (без новых сообщений)."""
    empty: dict[str, Any] = {
        "nft_check_restore_body": None,
        "nft_check_restore_kb": None,
        "nft_check_restore_parse": None,
    }
    if (
        message.photo
        or message.video
        or message.animation
        or message.document
        or message.sticker
        or message.audio
        or message.voice
    ):
        return empty
    body = message.html_text or message.text
    cap_h = getattr(message, "caption_html", None)
    if body is None and message.caption:
        body = cap_h or message.caption
    if not body:
        return empty
    parse_mode = "HTML" if (message.html_text or cap_h) else None
    kb = serialize_inline_keyboard(message.reply_markup)
    return {
        "nft_check_restore_body": body,
        "nft_check_restore_kb": kb,
        "nft_check_restore_parse": parse_mode,
    }


async def enter_nft_check_waiting_on_message(message: Message, *, state: FSMContext, lang: str) -> None:
    """Переход в ожидание ввода NFT: по возможности правим то же сообщение, иначе отправляем новое."""
    snap = _nft_check_restore_payload(message)
    await state.set_state(CheckNftFlow.waiting_input)
    await state.update_data(**snap)
    if (
        message.photo
        or message.video
        or message.animation
        or message.document
        or message.sticker
        or message.audio
        or message.voice
    ):
        await message.answer(
            t("check.waiting_input", lang),
            reply_markup=nft_check_prompt_inline_keyboard(lang=lang),
        )
        return
    try:
        await message.edit_text(
            t("check.waiting_input", lang),
            reply_markup=nft_check_prompt_inline_keyboard(lang=lang),
            parse_mode=None,
        )
    except TelegramBadRequest:
        await state.update_data(
            nft_check_restore_body=None,
            nft_check_restore_kb=None,
            nft_check_restore_parse=None,
        )
        await message.answer(
            t("check.waiting_input", lang),
            reply_markup=nft_check_prompt_inline_keyboard(lang=lang),
        )


def _message_has_photo(message: Message) -> bool:
    ph = getattr(message, "photo", None)
    return isinstance(ph, (list, tuple)) and len(ph) > 0


async def _edit_start_message_content(
    message: Message,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
) -> None:
    if _message_has_photo(message):
        await message.edit_caption(caption=text[:1024], reply_markup=reply_markup)
    else:
        await message.edit_text(text[:4000], reply_markup=reply_markup, parse_mode=None)


async def enter_hub_nft_check_waiting_on_message(message: Message, *, state: FSMContext, lang: str) -> None:
    """Ожидание ссылки с экрана /start (hub): то же сообщение, только «Назад» в хаб."""
    await state.set_state(CheckNftFlow.waiting_input)
    await state.update_data(
        nft_check_restore_body=None,
        nft_check_restore_kb=None,
        nft_check_restore_parse=None,
    )
    body = t("start.hub_check_prompt", lang)
    kb = start_hub_back_only_keyboard(lang=lang)
    try:
        await _edit_start_message_content(message, text=body, reply_markup=kb)
    except TelegramBadRequest:
        await message.answer(body, reply_markup=kb)


async def _send_start_main_with_hero(
    message: Message,
    *,
    text: str,
    lang: str,
    is_admin: bool,
) -> None:
    _ = is_admin
    kb = start_hub_inline_keyboard(lang=lang)
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


async def _render_home(message: Message) -> str:
    async with SessionLocal() as session:
        users = UserRepository(session)
        gifts = GiftRepository(session)
        alerts = AlertRepository(session)
        feedback = FeedbackRepository(session)
        payments = ManualPaymentRepository(session)
        trades = TradeJournalRepository(session)
        user = await users.get_or_create(message.from_user.id, message.from_user.username)
        gift_count = await gifts.count_by_user(user.id)
        universe_rows = await users.list_universe(user.id)
        universe_count = len([x for x in universe_rows if x.is_active])
        active_alerts = await alerts.count_alert_rules(user.id)
        open_incidents = len(await alerts.list_open_incidents(user.id))
        open_trades = await trades.count_open_for_user(user.id)
        settings = get_settings()
        stale_submitted = []
        try:
            stale_cutoff = datetime.utcnow() - timedelta(hours=settings.manual_payment_submitted_sla_hours)
            stale_submitted = await payments.list_stale_submitted(limit=10, older_than=stale_cutoff)
        except Exception:
            stale_submitted = []
        try:
            has_feedback = (await feedback.count_by_user(user.id)) > 0
        except Exception:
            has_feedback = False
        last_snap = None
        try:
            snaps = await SignalSnapshotRepository(session).list_recent_for_user(user.id, limit=1)
            last_snap = snaps[0] if snaps else None
        except Exception:
            last_snap = None
    plan_limits = get_plan_limits(user.plan)
    watchlist_limit = int(plan_limits.get("max_gifts", 0))
    universe_limit = int(plan_limits.get("max_universe_collections", 0))
    bank_line = f"Банк: {user.bankroll_ton:.2f} TON\n" if user.bankroll_ton is not None else "Банк: не задан\n"
    goal_line = f"Цель: {user.goal_ton:.2f} TON\n" if user.goal_ton is not None else "Цель: не задана\n"
    snap_line = f"Последний signal ID: #{last_snap.id}\n" if last_snap else "Последний signal: нет\n"
    trades_line = f"Открытых сделок (журнал): {open_trades}\n"

    next_actions: list[str] = []
    if gift_count == 0:
        next_actions.append("Пришли ссылку на NFT или: /check <ссылка>")
    if user.bankroll_ton is None:
        next_actions.append("Задай банк: /bank_set 300")
    if gift_count > 0 and universe_count == 0 and user.plan == "free":
        next_actions.append("Добавь коллекцию в universe или расширь план; на Free попробуй /lite_plan 300")
    if (
        gift_count > 0
        and user.bankroll_ton is not None
        and can_use_feature(user, "capital_plan")
        and universe_count > 0
    ):
        next_actions.append("План на бюджет: /flip_plan 300 (на Free: /lite_plan 300)")
    elif gift_count > 0 and user.bankroll_ton is not None and user.plan == "free":
        next_actions.append("План по watchlist: /lite_plan 300")
    if user.plan == "free" and not can_use_feature(user, "scan_universe") and universe_count >= universe_limit:
        next_actions.append("Для universe scan нужен Pro: /upgrade (или /lite_plan по watchlist)")
    if user.plan == "free" and watchlist_limit > 0 and gift_count >= watchlist_limit:
        next_actions.append("Лимит watchlist на Free — /upgrade или удали лишнее из /list")
    if stale_submitted:
        next_actions.append("Ожидает подтверждения оплаты — /my_payments")
    if open_incidents > 0 and bool(plan_limits.get("incidents")):
        next_actions.append("Проверь /incidents")
    if bool(plan_limits.get("scan_universe")) and universe_count > 0 and user.plan in {"pro", "trader"}:
        next_actions.append("Найти сделки: /deals или /scan_universe")
    if int(getattr(user, "command_count", 0) or 0) >= int(get_settings().beta_feedback_reminder_command_threshold) and not has_feedback:
        next_actions.append("Оставь короткий /feedback — это помогает бете")
    if last_snap is not None:
        age = (datetime.utcnow() - last_snap.created_at).total_seconds()
        if age < 86400:
            next_actions.append(
                f"Оцени сигнал: /signal_good {last_snap.id} или /signal_bad {last_snap.id}"
            )
    if open_trades > 0:
        next_actions.append(f"Закрой сделку при продаже: /trade_sell <id> | цена (открыто: {open_trades})")
    if not next_actions:
        next_actions.append("Открой /examples или /menu")

    incidents_line = f"Открытых инцидентов: {open_incidents}\n" if bool(plan_limits.get("incidents")) else ""
    return (
        "🏠 GiftSniper Home\n\n"
        f"План: {user.plan.capitalize()}\n"
        f"Бейдж: {format_plan_badge(user.plan)}\n"
        f"Watchlist: {gift_count}/{watchlist_limit}\n"
        f"Universe (активных): {universe_count}/{universe_limit}\n"
        f"Активных alerts: {active_alerts}\n"
        f"{incidents_line}"
        f"{bank_line}{goal_line}"
        f"{snap_line}{trades_line}\n"
        "Дальше:\n"
        + "\n".join(format_next_action(x) for x in next_actions[:8])
    )


@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext, user_created_this_request: bool = False) -> None:
    await state.clear()
    parts = (message.text or "").split(maxsplit=1)
    deep = parts[1].strip() if len(parts) > 1 else ""
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        if deep.startswith(REFERRAL_START_PREFIX):
            await handle_referral_start(
                session,
                invited_user=user,
                start_payload=deep,
                user_was_created=user_created_this_request,
            )
    is_adm = user.role in {"admin", "owner"}
    lc = getattr(user, "language_code", None)
    if lc is None or not str(lc).strip():
        await message.answer(
            t("onboarding.choose_language", "en"),
            reply_markup=language_selector_keyboard(),
        )
        return
    lang = normalize_lang(str(lc))
    await _send_start_main_with_hero(
        message,
        text=t("start.main", lang),
        lang=lang,
        is_admin=is_adm,
    )


@router.message(Command("ref"))
async def ref_command_handler(message: Message) -> None:
    if not message.from_user:
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
    lang = text_lang_from_user(user)
    body, kb = await _referral_screen_parts(
        message, lang=lang, user_id=int(user.id), telegram_id=int(message.from_user.id)
    )
    await message.answer(body, reply_markup=kb)


@router.callback_query(F.data == CB_START_REFERRAL)
async def start_referral_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.message or not callback.from_user:
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(callback.from_user.id, callback.from_user.username)
    lang = text_lang_from_user(user)
    body, kb = await _referral_screen_parts(
        callback.message, lang=lang, user_id=int(user.id), telegram_id=int(callback.from_user.id)
    )
    try:
        await callback.message.answer(body, reply_markup=kb)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == CB_REF_REFRESH)
async def ref_refresh_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.message or not callback.from_user:
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(callback.from_user.id, callback.from_user.username)
    lang = text_lang_from_user(user)
    body, kb = await _referral_screen_parts(
        callback.message, lang=lang, user_id=int(user.id), telegram_id=int(callback.from_user.id)
    )
    try:
        await callback.message.edit_text(body, reply_markup=kb)
    except TelegramBadRequest:
        await callback.message.answer(body, reply_markup=kb)


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
    lang = text_lang_from_user(user)
    await message.answer(t("help.main", lang))


@router.message(Command("examples"))
async def examples_handler(message: Message) -> None:
    await message.answer(EXAMPLES_TEXT)


@router.message(Command("how_it_works"))
async def how_it_works_handler(message: Message) -> None:
    await message.answer(HOW_IT_WORKS_TEXT)


@router.message(Command("quick_start"))
async def quick_start_handler(message: Message) -> None:
    await message.answer(QUICK_START_TEXT)


@router.message(Command("commands"))
async def commands_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
    await message.answer(build_commands_text(is_admin=user.role in {"admin", "owner"}))


@router.message(Command("menu"))
async def menu_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
    lang = text_lang_from_user(user)
    await message.answer(
        t("settings.open_menu", lang),
        reply_markup=main_menu_keyboard(lang=lang, is_admin=user.role in {"admin", "owner"}),
    )


@router.message(Command("home"))
async def home_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
    lang = text_lang_from_user(user)
    await message.answer(
        await _render_home(message),
        reply_markup=main_menu_keyboard(lang=lang, is_admin=user.role in {"admin", "owner"}),
    )


@router.message(F.text.in_(NFT_CHECK_MENU_LABELS))
async def nft_check_menu_handler(message: Message, state: FSMContext) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
    lang = text_lang_from_user(user)
    await state.set_state(CheckNftFlow.waiting_input)
    await state.update_data(
        nft_check_restore_body=None,
        nft_check_restore_kb=None,
        nft_check_restore_parse=None,
    )
    await message.answer(t("check.waiting_input", lang), reply_markup=nft_check_prompt_inline_keyboard(lang=lang))


@router.message(F.text.in_(WATCHLIST_MENU_LABELS))
async def menu_watchlist_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not message.from_user:
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        n = await GiftRepository(session).count_by_user(user.id)
    if n == 0:
        await send_empty_watchlist_message(message)
    else:
        await send_watchlist_message(message)


@router.message(F.text.in_(SETTINGS_MENU_LABELS))
async def menu_settings_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await send_mvp_settings_screen(message)


@router.message(F.text.in_(HELP_MENU_LABELS))
async def menu_help_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
    lang = text_lang_from_user(user)
    await message.answer(t("start.help_short_text", lang), reply_markup=start_info_inline_keyboard(lang=lang, with_upgrade=False))


@router.message(F.text.in_(FEATURES_MENU_LABELS))
async def menu_features_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
    lang = text_lang_from_user(user)
    await message.answer(t("start.features_text", lang), reply_markup=start_info_inline_keyboard(lang=lang, with_upgrade=True))


@router.message(F.text.in_(UPGRADE_MENU_LABELS))
async def menu_upgrade_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await send_upgrade_carousel_message(message, start_plan_key="pro")


@router.callback_query(F.data == CB_START_MYLIST)
async def start_my_list_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message and callback.from_user:
        await send_watchlist_message(callback.message)


@router.callback_query(F.data == CB_UX_CLOSE_MESSAGE)
async def ux_close_message_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass


@router.callback_query(F.data == CB_START_CHECK)
async def start_check_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message or not callback.from_user:
        await callback.answer()
        return
    async with SessionLocal() as session:
        u = await UserRepository(session).get_or_create(callback.from_user.id, callback.from_user.username)
    lang = text_lang_from_user(u)
    await enter_hub_nft_check_waiting_on_message(callback.message, state=state, lang=lang)
    await callback.answer()


@router.callback_query(F.data == CB_START_UPGRADE)
async def start_upgrade_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        await send_upgrade_carousel_message(
            callback.message,
            start_plan_key="pro",
            edit_message=callback.message,
        )


@router.callback_query(F.data == CB_START_FEATURES)
async def start_features_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message and callback.from_user:
        async with SessionLocal() as session:
            u = await UserRepository(session).get_or_create(callback.from_user.id, callback.from_user.username)
        lang = text_lang_from_user(u)
        try:
            await _edit_start_message_content(
                callback.message,
                text=t("start.hub_features", lang),
                reply_markup=start_hub_features_nav_keyboard(lang=lang),
            )
        except TelegramBadRequest:
            await callback.message.answer(
                t("start.hub_features", lang),
                reply_markup=start_hub_features_nav_keyboard(lang=lang),
            )


@router.callback_query(F.data == CB_START_HELP)
async def start_help_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message and callback.from_user:
        async with SessionLocal() as session:
            u = await UserRepository(session).get_or_create(callback.from_user.id, callback.from_user.username)
        lang = text_lang_from_user(u)
        try:
            await _edit_start_message_content(
                callback.message,
                text=t("start.hub_help", lang),
                reply_markup=start_hub_help_nav_keyboard(lang=lang),
            )
        except TelegramBadRequest:
            await callback.message.answer(
                t("start.hub_help", lang),
                reply_markup=start_hub_help_nav_keyboard(lang=lang),
            )


@router.callback_query(F.data == CB_START_BACK)
async def start_back_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message and callback.from_user:
        async with SessionLocal() as session:
            u = await UserRepository(session).get_or_create(callback.from_user.id, callback.from_user.username)
        lang = text_lang_from_user(u)
        hub_text = t("start.main", lang)
        hub_kb = start_hub_inline_keyboard(lang=lang)
        try:
            await _edit_start_message_content(callback.message, text=hub_text, reply_markup=hub_kb)
        except TelegramBadRequest:
            await _send_start_main_with_hero(
                callback.message,
                text=hub_text,
                lang=lang,
                is_admin=u.role in {"admin", "owner"},
            )


@router.message(
    StateFilter(CheckNftFlow.waiting_input),
    F.text,
    ~F.text.startswith("/"),
    ~F.text.in_(MAIN_MENU_ALL_LABELS),
    ExcludePendingDealPriceMessageFilter(),
)
async def nft_check_waiting_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await execute_check_payload(message, (message.text or "").strip())


@router.callback_query(F.data == CB_NFT_CHECK_BACK)
async def nft_check_back_callback(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    if not callback.message or not callback.from_user:
        await callback.answer()
        return
    async with SessionLocal() as session:
        u = await UserRepository(session).get_or_create(callback.from_user.id, callback.from_user.username)
    lang = text_lang_from_user(u)
    body = data.get("nft_check_restore_body")
    kb_raw = data.get("nft_check_restore_kb")
    pm = data.get("nft_check_restore_parse")
    if body is not None and kb_raw is not None:
        try:
            await callback.message.edit_text(
                body,
                reply_markup=deserialize_inline_keyboard(kb_raw),
                parse_mode=pm,
            )
            await callback.answer()
            return
        except TelegramBadRequest:
            pass
    try:
        await callback.message.edit_text(t("nft.flow_check_closed", lang), reply_markup=None)
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data == CB_NFT_CHECK_CANCEL)
async def nft_check_cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if not callback.message or not callback.from_user:
        await callback.answer()
        return
    async with SessionLocal() as session:
        u = await UserRepository(session).get_or_create(
            callback.from_user.id, callback.from_user.username if callback.from_user else None
        )
    lang = text_lang_from_user(u)
    try:
        await callback.message.edit_text(t("nft.flow_cancelled", lang), reply_markup=None)
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data == CB_EMPTY_WL_CHECK)
async def empty_watchlist_check_callback(callback: CallbackQuery, state: FSMContext) -> None:
    async with SessionLocal() as session:
        u = await UserRepository(session).get_or_create(
            callback.from_user.id, callback.from_user.username if callback.from_user else None
        )
    lang = text_lang_from_user(u)
    await callback.answer()
    if callback.message:
        await enter_nft_check_waiting_on_message(callback.message, state=state, lang=lang)


@router.callback_query(F.data == CB_EMPTY_WL_WATCH)
async def empty_watchlist_watch_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message and callback.from_user:
        async with SessionLocal() as session:
            u = await UserRepository(session).get_or_create(callback.from_user.id, callback.from_user.username)
        lang = text_lang_from_user(u)
        await callback.message.answer(t("watch.add_hint", lang))


@router.callback_query(F.data == CB_EMPTY_WL_BACK)
async def empty_watchlist_back_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message and callback.from_user:
        async with SessionLocal() as session:
            u = await UserRepository(session).get_or_create(callback.from_user.id, callback.from_user.username)
        lang = text_lang_from_user(u)
        await callback.message.answer(t("upgrade.ok_menu", lang))


@router.callback_query(F.data == CB_SETTINGS_STUB_CHECK)
async def settings_stub_check_callback(callback: CallbackQuery, state: FSMContext) -> None:
    async with SessionLocal() as session:
        u = await UserRepository(session).get_or_create(
            callback.from_user.id, callback.from_user.username if callback.from_user else None
        )
    lang = text_lang_from_user(u)
    await callback.answer()
    if callback.message:
        await enter_nft_check_waiting_on_message(callback.message, state=state, lang=lang)


@router.callback_query(F.data == CB_SETTINGS_STUB_WATCHLIST)
async def settings_stub_watchlist_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if not callback.message or not callback.from_user:
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(callback.from_user.id, callback.from_user.username)
        n = await GiftRepository(session).count_by_user(user.id)
    if n == 0:
        await send_empty_watchlist_message(callback.message)
    else:
        await send_watchlist_message(callback.message)


@router.callback_query(F.data == CB_SETTINGS_STUB_BACK)
async def settings_stub_back_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message and callback.from_user:
        async with SessionLocal() as session:
            u = await UserRepository(session).get_or_create(callback.from_user.id, callback.from_user.username)
        lang = text_lang_from_user(u)
        await callback.message.answer(t("upgrade.ok_menu", lang))
