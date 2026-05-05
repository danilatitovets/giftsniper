"""MVP: карусель тарифов и оплата TON на кошелёк с проверкой через TonAPI."""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.exc import IntegrityError

from app.bot.upgrade_inline import (
    CB_PAY_CANCEL,
    CB_PAY_CHECK,
    CB_PAY_REFRESH,
    CB_UPGRADE_BACK,
    CB_UPGRADE_BUY,
    CB_UPGRADE_NEXT,
    CB_UPGRADE_OPEN,
    CB_UPGRADE_PREV,
)
from app.config import get_settings
from app.db.repositories.billing import BillingRepository
from app.db.repositories.gifts import GiftRepository
from app.db.repositories.ton_payments import TonSubscriptionPaymentRepository, UserNftCheckDayRepository
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.i18n import localized_carousel_body, normalize_lang, t, text_lang_from_user
from app.services.entitlements import get_effective_entitlement, grant_entitlement, sync_user_plan_from_entitlement
from app.services.feature_limits import checks_per_day_limit, get_plan_limits, normalize_plan_for_limits
from app.services.plan_catalog import (
    PLAN_ORDER,
    get_sellable_plan,
    plan_duration_days,
    plan_price_ton,
    ton_decimal_to_nano,
)
from app.services.plan_catalog import generate_invoice_comment as make_invoice_comment
from app.services.ton_payment_verify import match_incoming_payment

logger = logging.getLogger(__name__)

router = Router()


def _format_ton_amount_from_nano(nano: int) -> str:
    x = int(nano) / 1_000_000_000
    s = f"{x:.6f}".rstrip("0").rstrip(".")
    return s if s else "0"


class InvoiceCreateError(Exception):
    pass


class InvoiceConfigError(InvoiceCreateError):
    pass


class InvoicePlanError(InvoiceCreateError):
    pass


class InvoiceStorageError(InvoiceCreateError):
    pass


_TON_ADDR_RE = re.compile(r"^(?:[EUk]Q[a-zA-Z0-9_-]{20,}|0:[0-9a-fA-F]{64})$")


def _is_receiver_address_valid(addr: str) -> bool:
    return bool(_TON_ADDR_RE.match((addr or "").strip()))


def _carousel_neighbor_key(plan_key: str, delta: int) -> str | None:
    try:
        idx = PLAN_ORDER.index(plan_key)
    except ValueError:
        return None
    nidx = idx + delta
    if nidx < 0 or nidx >= len(PLAN_ORDER):
        return None
    return PLAN_ORDER[nidx]


def _carousel_keyboard(plan_key: str, *, current_user_plan: str, lang: str) -> InlineKeyboardMarkup:
    uplan = normalize_plan_for_limits(current_user_plan)
    lg = normalize_lang(lang)
    row_nav: list[InlineKeyboardButton] = []
    prev = _carousel_neighbor_key(plan_key, -1)
    nxt = _carousel_neighbor_key(plan_key, 1)
    row_nav.append(
        InlineKeyboardButton(
            text="⬅️",
            callback_data=f"{CB_UPGRADE_PREV}:{plan_key}" if prev else "upgrade:noop",
        )
    )
    if plan_key == "free":
        mid = t("upgrade.nav_current_plan", lg) if uplan == "free" else "Free"
        row_nav.append(InlineKeyboardButton(text=mid, callback_data="upgrade:noop"))
    else:
        pay_txt = t("upgrade.pay_renew_short", lg) if uplan == plan_key else t("upgrade.pay_buy_short", lg)
        row_nav.append(InlineKeyboardButton(text=pay_txt, callback_data=f"{CB_UPGRADE_BUY}:{plan_key}"))
    row_nav.append(
        InlineKeyboardButton(
            text="➡️",
            callback_data=f"{CB_UPGRADE_NEXT}:{plan_key}" if nxt else "upgrade:noop",
        )
    )
    rows: list[list[InlineKeyboardButton]] = [row_nav]
    rows.append([InlineKeyboardButton(text=t("upgrade.back_button", lg), callback_data=CB_UPGRADE_BACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _payment_keyboard(payment_id: int, lang: str) -> InlineKeyboardMarkup:
    lg = normalize_lang(lang)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("payment.btn_check", lg), callback_data=f"{CB_PAY_CHECK}:{payment_id}"),
                InlineKeyboardButton(text=t("payment.btn_refresh", lg), callback_data=f"{CB_PAY_REFRESH}:{payment_id}"),
            ],
            [InlineKeyboardButton(text=t("payment.btn_cancel", lg), callback_data=f"{CB_PAY_CANCEL}:{payment_id}")],
        ]
    )


def _billing_keyboard(*, show_renew: bool, lang: str) -> InlineKeyboardMarkup:
    lg = normalize_lang(lang)
    row = [InlineKeyboardButton(text=t("upgrade.billing_upgrade", lg), callback_data=CB_UPGRADE_OPEN)]
    if show_renew:
        row.append(InlineKeyboardButton(text=t("upgrade.billing_renew", lg), callback_data=CB_UPGRADE_OPEN))
    row.append(InlineKeyboardButton(text=t("upgrade.billing_back", lg), callback_data=CB_UPGRADE_BACK))
    return InlineKeyboardMarkup(inline_keyboard=[row])


def _default_carousel_plan(user_plan: str) -> str:
    low = normalize_plan_for_limits(user_plan)
    if low in PLAN_ORDER:
        return low
    return "free"


def _message_has_photo(message: Message) -> bool:
    ph = getattr(message, "photo", None)
    return isinstance(ph, (list, tuple)) and len(ph) > 0


async def _edit_carousel_message(message: Message, text: str, kb: InlineKeyboardMarkup) -> bool:
    """Правка того же сообщения: для фото — caption, иначе text. Caption ≤ 1024."""
    try:
        if _message_has_photo(message):
            if len(text) > 1024:
                return False
            await message.edit_caption(caption=text, reply_markup=kb)
        else:
            await message.edit_text(text, reply_markup=kb)
        return True
    except Exception:
        logger.debug("carousel edit failed", exc_info=True)
        return False


async def send_upgrade_carousel_message(
    message: Message,
    *,
    start_plan_key: str | None = None,
    edit_message: Message | None = None,
) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        cur = (user.plan or "free").lower()
        lang = text_lang_from_user(user)
    plan_key = start_plan_key or _default_carousel_plan(cur)
    if plan_key not in PLAN_ORDER:
        plan_key = "free"
    text = localized_carousel_body(plan_key, settings, lang)
    kb = _carousel_keyboard(plan_key, current_user_plan=cur, lang=lang)
    if edit_message:
        if await _edit_carousel_message(edit_message, text, kb):
            return
        logger.debug("edit_message failed or caption too long, sending new message")
    await message.answer(text, reply_markup=kb)


@router.message(Command("upgrade"))
async def upgrade_command(message: Message) -> None:
    await send_upgrade_carousel_message(message, start_plan_key="free")


@router.message(Command("billing"))
async def billing_command(message: Message) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        await sync_user_plan_from_entitlement(session, user)
        ent = await get_effective_entitlement(session, user)
        used_checks = await UserNftCheckDayRepository(session).get_count(user.id)
        gifts_count = await GiftRepository(session).count_by_user(user.id)
        last_paid = await TonSubscriptionPaymentRepository(session).get_last_paid_for_user(user.id)
        lang = text_lang_from_user(user)
    plan = (ent.get("plan") or "free").lower()
    limits = get_plan_limits(plan)
    max_checks = checks_per_day_limit(user)
    max_wl = int(limits.get("max_gifts", 0))
    exp = ent.get("expires_at")
    exp_s = "—"
    if exp:
        e = exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
        exp_s = e.strftime("%d.%m.%Y")
    body = (
        t("billing.title", lang)
        + "\n\n"
        + t("billing.plan", lang, plan=plan.capitalize())
        + "\n"
        + t("billing.active_until", lang, date=exp_s)
        + "\n\n"
        + t("billing.limits_section", lang)
        + "\n"
        + t("billing.limits_checks", lang, used=used_checks, max=max_checks)
        + "\n"
        + t("billing.limits_watchlist", lang, used=gifts_count, max=max_wl)
        + "\n\n"
        + t("billing.payment_note", lang)
        + "\n"
        + t("billing.no_autorenew", lang)
    )
    if last_paid is not None:
        paid_dt = last_paid.paid_at or last_paid.created_at
        paid_s = "—"
        if paid_dt:
            p = paid_dt if paid_dt.tzinfo else paid_dt.replace(tzinfo=timezone.utc)
            paid_s = p.strftime("%d.%m.%Y")
        body += (
            "\n\n"
            + "Последний платёж:\n"
            + f"{float(last_paid.amount_ton):g} TON\n"
            + "Статус: оплачен\n"
            + f"Дата: {paid_s}"
        )
    _ = settings
    show_renew = plan in {"pro", "sniper"}
    await message.answer(body, reply_markup=_billing_keyboard(show_renew=show_renew, lang=lang))


@router.callback_query(F.data == CB_UPGRADE_OPEN)
async def cb_upgrade_open(query: CallbackQuery) -> None:
    await query.answer()
    if query.message:
        await send_upgrade_carousel_message(query.message, start_plan_key="free", edit_message=query.message)


@router.callback_query(F.data == "upgrade:noop")
async def cb_upgrade_noop(query: CallbackQuery) -> None:
    await query.answer()


@router.callback_query(F.data.startswith(f"{CB_UPGRADE_PREV}:"))
async def cb_upgrade_prev(query: CallbackQuery) -> None:
    cur = query.data.split(":", 2)[-1]
    prev_k = _carousel_neighbor_key(cur, -1)
    if prev_k is None:
        await query.answer()
        return
    await query.answer()
    if query.message:
        settings = get_settings()
        async with SessionLocal() as session:
            user = await UserRepository(session).get_or_create(query.from_user.id, query.from_user.username)
            uplan = (user.plan or "free").lower()
            lang = text_lang_from_user(user)
        text = localized_carousel_body(prev_k, settings, lang)
        kb = _carousel_keyboard(prev_k, current_user_plan=uplan, lang=lang)
        if not await _edit_carousel_message(query.message, text, kb):
            await query.message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith(f"{CB_UPGRADE_NEXT}:"))
async def cb_upgrade_next(query: CallbackQuery) -> None:
    cur = query.data.split(":", 2)[-1]
    nxt = _carousel_neighbor_key(cur, 1)
    if nxt is None:
        await query.answer()
        return
    await query.answer()
    if query.message:
        settings = get_settings()
        async with SessionLocal() as session:
            user = await UserRepository(session).get_or_create(query.from_user.id, query.from_user.username)
            uplan = (user.plan or "free").lower()
            lang = text_lang_from_user(user)
        text = localized_carousel_body(nxt, settings, lang)
        kb = _carousel_keyboard(nxt, current_user_plan=uplan, lang=lang)
        if not await _edit_carousel_message(query.message, text, kb):
            await query.message.answer(text, reply_markup=kb)


@router.callback_query(F.data == CB_UPGRADE_BACK)
async def cb_upgrade_back(query: CallbackQuery) -> None:
    await query.answer()
    if query.message and query.from_user:
        async with SessionLocal() as session:
            user = await UserRepository(session).get_or_create(query.from_user.id, query.from_user.username)
            lang = text_lang_from_user(user)
        await query.message.answer(t("upgrade.ok_menu", lang))


@router.callback_query(F.data.startswith(f"{CB_UPGRADE_BUY}:"))
async def cb_upgrade_buy(query: CallbackQuery) -> None:
    plan = query.data.split(":")[-1].lower()
    if plan not in {"pro", "sniper"}:
        async with SessionLocal() as session:
            user = await UserRepository(session).get_or_create(query.from_user.id, query.from_user.username)
            lang = text_lang_from_user(user)
        await query.answer(t("upgrade.unavailable", lang), show_alert=True)
        return
    settings = get_settings()
    if not settings.ton_payment_enabled:
        async with SessionLocal() as session:
            user = await UserRepository(session).get_or_create(query.from_user.id, query.from_user.username)
            lang = text_lang_from_user(user)
        await query.answer(t("payment.payment_disabled", lang), show_alert=True)
        return
    recv = (settings.ton_payment_receiver_address or "").strip()
    if not recv:
        async with SessionLocal() as session:
            user = await UserRepository(session).get_or_create(query.from_user.id, query.from_user.username)
            lang = text_lang_from_user(user)
        await query.answer("Оплата временно недоступна. Мы уже проверяем настройки.", show_alert=True)
        logger.error("invoice_create_failed reason=missing_receiver plan=%s telegram_id=%s", plan, query.from_user.id)
        return
    if not _is_receiver_address_valid(recv):
        async with SessionLocal() as session:
            user = await UserRepository(session).get_or_create(query.from_user.id, query.from_user.username)
            lang = text_lang_from_user(user)
        await query.answer("Оплата временно недоступна. Мы уже проверяем настройки.", show_alert=True)
        logger.error(
            "invoice_create_failed reason=invalid_receiver plan=%s telegram_id=%s receiver=%s",
            plan,
            query.from_user.id,
            recv,
        )
        return
    await query.answer()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(query.from_user.id, query.from_user.username)
        lang = text_lang_from_user(user)
        repo = TonSubscriptionPaymentRepository(session)
        logger.info(
            "invoice_create_started plan=%s user_id=%s telegram_id=%s",
            plan,
            user.id,
            query.from_user.id,
        )
        try:
            spec = get_sellable_plan(plan, settings)
            if spec is None:
                raise InvoicePlanError("invalid_or_non_sellable_plan")
            short = secrets.token_hex(3).upper()[:6]
            comment = make_invoice_comment(plan, short)
            ttl = int(settings.ton_payment_invoice_ttl_minutes or 30)
            expires = datetime.now(timezone.utc) + timedelta(minutes=ttl)
            pay = await repo.create_pending(
                user_id=user.id,
                plan=plan,
                amount_ton=float(spec.price_ton),
                amount_nano=ton_decimal_to_nano(spec.price_ton),
                receiver_address=recv,
                comment=comment,
                expires_at=expires,
            )
        except InvoicePlanError:
            logger.warning(
                "invoice_create_failed reason=bad_plan plan=%s user_id=%s telegram_id=%s",
                plan,
                user.id,
                query.from_user.id,
            )
            if query.message:
                await query.message.answer("Такой тариф не найден. Попробуй выбрать тариф заново.")
            return
        except Exception:
            logger.exception(
                "Failed to create TON invoice user_id=%s telegram_id=%s plan=%s",
                user.id,
                query.from_user.id,
                plan,
            )
            if query.message:
                await query.message.answer("Не удалось сохранить счёт. Попробуй позже.")
            return
    logger.info(
        "invoice_created payment_id=%s user_id=%s telegram_id=%s plan=%s",
        pay.id,
        user.id,
        query.from_user.id,
        plan,
    )
    pid = pay.id
    lg = normalize_lang(lang)
    price = float(pay.amount_ton)
    text = (
        t("payment.instruction_title", lg, plan=plan.capitalize())
        + "\n\n"
        + t("payment.send_amount", lg, amount=f"{price:g}")
        + "\n"
        + t("payment.to_address", lg)
        + f"\n`{recv}`\n\n"
        + t("payment.comment_line", lg)
        + f"\n`{comment}`\n\n"
        + t("payment.notes_header", lg)
        + "\n"
        + t("payment.note_comment", lg)
        + "\n"
        + t("payment.note_ton_only", lg)
        + "\n"
        + t("payment.note_activate", lg)
        + "\n"
        + t("payment.note_no_wallet", lg)
        + "\n\n"
        + t("payment.after_pay_hint", lg)
    )
    if query.message:
        await query.message.answer(text, parse_mode="Markdown", reply_markup=_payment_keyboard(pid, lang))


async def _finalize_payment_if_matched(
    payment_id: int, telegram_id: int, username: str | None, *, lang: str | None = None
) -> tuple[str, bool]:
    settings = get_settings()
    if not settings.tonapi_enabled or not str(settings.tonapi_api_key or "").strip():
        return "Проверка оплаты временно недоступна.", False
    now = datetime.now(timezone.utc)
    recv: str = ""
    nano: int = 0
    comment: str = ""
    plan: str = ""
    uid: int = 0
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(telegram_id, username)
        lg = text_lang_from_user(user) if lang is None else normalize_lang(lang)
        repo = TonSubscriptionPaymentRepository(session)
        pay = await repo.get_by_id_for_user(payment_id, user.id)
        if pay is None:
            return t("payment.invoice_not_found", lg), False
        if pay.status == "paid":
            await sync_user_plan_from_entitlement(session, user)
            exp = user.plan_expires_at
            exp_s = "—"
            if exp:
                e = exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
                exp_s = e.strftime("%d.%m.%Y")
            return (
                t("payment.already_confirmed", lg, plan=pay.plan.capitalize(), date=exp_s),
                True,
            )
        if pay.status != "pending":
            if pay.status == "cancelled":
                return "Этот счёт отменён.", False
            if pay.status == "expired":
                return "Счёт истёк. Создай новый.", False
            return t("payment.invoice_invalid", lg), False
        exp = pay.expires_at
        if exp is None:
            return t("payment.invoice_error", lg), False
        exp_aware = exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
        if exp_aware < now:
            await repo.mark_expired(pay)
            return t("payment.invoice_expired", lg), False
        recv = pay.receiver_address
        nano = int(pay.amount_nano)
        comment = pay.comment
        plan = pay.plan
        uid = user.id

    async def _is_tx_consumed(h: str) -> bool:
        async with SessionLocal() as s2:
            return await TonSubscriptionPaymentRepository(s2).is_tx_consumed(h)

    match = await match_incoming_payment(
        settings,
        receiver_address=recv,
        expected_nano=nano,
        expected_comment=comment,
        is_tx_consumed=_is_tx_consumed,
        created_at=getattr(pay, "created_at", None),
        expires_at=getattr(pay, "expires_at", None),
    )
    if match.status == "underpaid":
        need = _format_ton_amount_from_nano(match.expected_nano)
        got = _format_ton_amount_from_nano(match.actual_nano)
        return (
            "❌ Платёж найден, но сумма меньше нужной.\n"
            f"Нужно: {need} TON\n"
            f"Получено: {got} TON",
            False,
        )
    if match.status != "paid" or not match.tx_hash:
        logger.info("payment_not_found payment_id=%s user_id=%s", payment_id, uid)
        return t("payment.not_found", lg), False
    tx_hash = match.tx_hash
    async with SessionLocal() as session:
        repo = TonSubscriptionPaymentRepository(session)
        if await repo.is_tx_consumed(tx_hash):
            logger.info("payment_reused_tx payment_id=%s tx_hash=%s", payment_id, tx_hash)
            return t("payment.tx_already_used", lg), True
        pay = await repo.get_by_id_for_user(payment_id, uid)
        if pay is None or pay.status != "pending":
            return t("payment.invoice_unavailable", lg), False
        try:
            await repo.finalize_paid_and_record_tx(pay, tx_hash, datetime.now(timezone.utc))
        except IntegrityError:
            await session.rollback()
            logger.info("payment_reused_tx_integrity payment_id=%s tx_hash=%s", payment_id, tx_hash)
            return t("payment.tx_already_used", lg), True
        user = await UserRepository(session).get_by_id(uid)
        if user is None:
            return t("payment.user_error", lg), False
        eff = await get_effective_entitlement(session, user)
        base = now
        cur_exp = eff.get("expires_at")
        if cur_exp is not None:
            ce = cur_exp if cur_exp.tzinfo else cur_exp.replace(tzinfo=timezone.utc)
            if ce > base:
                base = ce
        days = plan_duration_days(plan, settings)
        new_exp = base + timedelta(days=days)
        await grant_entitlement(session, user.id, plan, "ton_payment", new_exp, f"ton_tx:{tx_hash[:20]}")
        logger.info("entitlement_activated user_id=%s plan=%s payment_id=%s", user.id, plan, payment_id)
        meta = json.dumps(
            {
                "tx_hash": tx_hash,
                "expected_amount_nano": int(match.expected_nano),
                "actual_amount_nano": int(match.actual_nano),
            },
            ensure_ascii=False,
        )
        await BillingRepository(session).create_billing_event(
            user_id=user.id,
            event_type="ton_payment_confirmed",
            provider="ton_manual",
            plan=plan,
            amount=float(pay.amount_ton),
            currency="TON",
            status="paid",
            metadata_json=meta[:3900],
        )
        logger.info("billing_event_created user_id=%s plan=%s payment_id=%s", user.id, plan, payment_id)
        await sync_user_plan_from_entitlement(session, user)
        exp_s = new_exp.strftime("%d.%m.%Y")
    lim = get_plan_limits(plan)
    checks = lim.get("checks_per_day", "?")
    wl = lim.get("max_gifts", "?")
    logger.info("payment_confirmed payment_id=%s plan=%s user_id=%s", payment_id, plan, uid)
    return (
        t("payment.found_header", lg)
        + t("payment.found_until", lg, plan=plan.capitalize(), date=exp_s)
        + t("payment.found_features", lg, checks=checks, wl=wl),
        True,
    )


@router.callback_query(F.data.startswith(f"{CB_PAY_CHECK}:"))
async def cb_pay_check(query: CallbackQuery) -> None:
    pid = int(query.data.rsplit(":", 1)[-1])
    text, _ok = await _finalize_payment_if_matched(
        pid, query.from_user.id, query.from_user.username, lang=None
    )
    await query.answer()
    if query.message:
        await query.message.answer(text)


@router.callback_query(F.data.startswith(f"{CB_PAY_REFRESH}:"))
async def cb_pay_refresh(query: CallbackQuery) -> None:
    pid = int(query.data.rsplit(":", 1)[-1])
    settings = get_settings()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(query.from_user.id, query.from_user.username)
        pay = await TonSubscriptionPaymentRepository(session).get_by_id_for_user(pid, user.id)
        lang = text_lang_from_user(user)
    if not pay:
        await query.answer(t("payment.invoice_not_found", lang), show_alert=True)
        return
    recv = (settings.ton_payment_receiver_address or "").strip()
    price = float(pay.amount_ton)
    lg = normalize_lang(lang)
    text = (
        t("payment.instruction_title", lg, plan=pay.plan.capitalize())
        + "\n\n"
        + t("payment.send_amount", lg, amount=f"{price:g}")
        + "\n"
        + t("payment.to_address", lg)
        + f"\n`{recv}`\n\n"
        + t("payment.comment_line", lg)
        + f"\n`{pay.comment}`\n\n"
        + t("payment.after_pay_hint", lg)
    )
    await query.answer(t("payment.refresh_ok", lang))
    if query.message:
        try:
            await query.message.edit_text(
                text, parse_mode="Markdown", reply_markup=_payment_keyboard(pid, lang)
            )
        except Exception:
            await query.message.answer(text, parse_mode="Markdown", reply_markup=_payment_keyboard(pid, lang))


@router.callback_query(F.data.startswith(f"{CB_PAY_CANCEL}:"))
async def cb_pay_cancel(query: CallbackQuery) -> None:
    pid = int(query.data.rsplit(":", 1)[-1])
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(query.from_user.id, query.from_user.username)
        lang = text_lang_from_user(user)
        repo = TonSubscriptionPaymentRepository(session)
        pay = await repo.get_by_id_for_user(pid, user.id)
        if pay and pay.status == "pending":
            await repo.mark_cancelled(pay)
    await query.answer(t("payment.cancel_toast", lang))
    if query.message:
        await query.message.answer(t("payment.cancelled", lang))
