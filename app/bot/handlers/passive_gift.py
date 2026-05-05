from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import get_settings
from app.db.repositories.gifts import GiftRepository
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.bot.keyboards import (
    my_list_after_add_inline_keyboard,
    my_list_limit_inline_keyboard,
    my_list_session_expired_inline_keyboard,
)
from app.bot.upgrade_inline import format_watchlist_limit_message
from app.services.gift_cards import format_unknown_gift_input_help
from app.services.gift_intake import GiftInputType, parse_gift_input, smells_like_gift_link
from app.services.gift_resolver import resolve_gift_identity
from app.services import runtime_state
from app.services.gift_analysis_flow import is_nft_like_check_payload
from app.services.nft_tonapi_image import PreviewMedia, extract_nft_preview_media, safe_media_url_for_log
from app.services.tonapi_collection_client import TonAPICollectionClient
from app.services.universal_nft_resolver import ResolvedNft, resolve_universal_nft
from app.i18n import t, text_lang_from_user
from app.services.watchlist_add_flow import MyListAddResult, add_to_my_list

router = Router()
logger = logging.getLogger(__name__)

# Запас под HTML и лимит Telegram caption (1024).
_TELEGRAM_CAPTION_SAFE = 900


def _smells_like_gift_context(text: str) -> bool:
    low = text.lower().strip()
    if len(low) > 900:
        return False
    gi = parse_gift_input(text.strip())
    if gi.input_type != GiftInputType.unknown:
        return True
    return smells_like_gift_link(text)


def _resolved_nft_keyboard(sid: str) -> InlineKeyboardMarkup:
    check_cb = f"gift:market_check:{sid}"
    price_cb = f"gift:listing_price:{sid}"
    add_cb = f"gift:watch_add:{sid}"
    deal_cb = f"gift:deal_check:{sid}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔎 Проверить рынок", callback_data=check_cb),
                InlineKeyboardButton(text="💎 Цена листинга", callback_data=price_cb),
            ],
            [
                InlineKeyboardButton(text="✅ Добавить в список", callback_data=add_cb),
                InlineKeyboardButton(text="💰 Сделка", callback_data=deal_cb),
            ],
            [
                InlineKeyboardButton(text="❌ Закрыть", callback_data=f"gift:close:{sid}"),
            ],
        ]
    )


def _close_only_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Закрыть", callback_data="gift:cancel:0")]]
    )


def _link_help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Как найти ссылку?", callback_data="help:find_nft_link")],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="gift:cancel:0")],
        ]
    )


def _build_preview_text_from_resolved(resolved: ResolvedNft) -> str:
    src_label = getattr(resolved, "user_source_label", "TonAPI")
    if getattr(resolved, "external_sale_hint", False) and (resolved.source or "") != "getgems_web":
        src_label = f"{src_label} / Getgems link payload"

    def _fmt_ton(v: float) -> str:
        s = f"{float(v):.3f}".rstrip("0").rstrip(".")
        return s.replace(".", ",")

    lines_trait: list[str] = []
    plines = getattr(resolved, "preview_trait_lines", None)
    if plines:
        for k, v in plines:
            lines_trait.append(f"{k}: {v}")
    else:
        model = resolved.traits.get("model") or "—"
        backdrop = resolved.traits.get("backdrop") or "—"
        symbol = resolved.traits.get("symbol") or "—"
        lines_trait.extend(
            [
                f"Model: {model}",
                f"Backdrop: {backdrop}",
                f"Symbol: {symbol}",
            ]
        )
    traits_block = "\n".join(lines_trait)

    if resolved.sale_price_ton is not None:
        if (resolved.source or "") == "getgems_web":
            listing = f"Выставлен за {_fmt_ton(resolved.sale_price_ton)} TON"
        else:
            listing = f"Сейчас выставлен: {_fmt_ton(resolved.sale_price_ton)} TON"
    elif resolved.for_sale:
        listing = "Выставлен, цена не в TON"
    elif getattr(resolved, "external_sale_hint", False):
        listing = "Листинг не подтверждён TonAPI. Возможен активный листинг на Getgems."
    else:
        listing = "Сейчас не выставлен на продажу"
    return (
        f"🎁 <b>{resolved.nft_name}</b>\n"
        f"\nКоллекция: <b>{resolved.collection_name}</b>\n\n"
        "🧬 Трейты\n"
        f"{traits_block}\n\n"
        "💎 Листинг\n"
        f"{listing}\n\n"
        f"Источник: {src_label}\n\n"
        "Что сделать?"
    )


def _preview_caption_short_html(resolved: ResolvedNft) -> str:
    return (
        f"🎁 <b>{resolved.nft_name}</b>\n"
        f"Коллекция: <b>{resolved.collection_name}</b>"
    )


async def _send_resolved_nft_preview(
    message: Message,
    *,
    resolved: ResolvedNft,
    media: PreviewMedia,
    body: str,
    kb: InlineKeyboardMarkup,
) -> None:
    """Отправка превью: animation / video / photo / текст; при ошибке медиа — текстовая карточка."""
    if not media.url or media.kind == "none":
        await message.answer(body, parse_mode="HTML", reply_markup=kb)
        return

    use_short_caption = len(body) > _TELEGRAM_CAPTION_SAFE
    cap = _preview_caption_short_html(resolved) if use_short_caption else body[:1024]
    send_kwargs = {"caption": cap, "parse_mode": "HTML", "reply_markup": None if use_short_caption else kb}

    try:
        if media.kind == "animation":
            await message.answer_animation(animation=media.url, **send_kwargs)
        elif media.kind == "video":
            await message.answer_video(video=media.url, **send_kwargs)
        else:
            await message.answer_photo(photo=media.url, **send_kwargs)
    except Exception as exc:
        logger.warning(
            "nft preview media send failed kind=%s err=%s meta=%s",
            media.kind,
            type(exc).__name__,
            safe_media_url_for_log(media.url),
        )
        await message.answer(body, parse_mode="HTML", reply_markup=kb)
        return

    if use_short_caption:
        await message.answer(body, parse_mode="HTML", reply_markup=kb)


def _friendly_unresolved_message(payload: str, *, paid: bool) -> str:
    p = (payload or "").strip() or "NFT"
    _ = paid
    if "#" in p:
        return (
            f"❌ Пока не нашёл «{p}» по названию.\n\n"
            "Самый надёжный способ — пришли ссылку на конкретный NFT с Getgems / Fragment / Tonviewer.\n"
            "После успешной проверки я запомню коллекцию."
        )
    return (
        "❌ Не нашёл NFT по этой ссылке или адресу.\n\n"
        "Проверь, что это ссылка на конкретный NFT, а не на коллекцию.\n"
        "Можно прислать ссылку Getgems / Fragment / Tonviewer или NFT address."
    )


async def _edit_or_answer(
    message: Message,
    progress: Message | None,
    text: str,
    *,
    kb: InlineKeyboardMarkup | None,
) -> None:
    if progress is not None:
        try:
            await message.bot.edit_message_text(
                text,
                chat_id=message.chat.id,
                message_id=progress.message_id,
                parse_mode="HTML",
                reply_markup=kb,
            )
            return
        except Exception:
            pass
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.message(F.text, ~F.text.startswith("/"))
async def passive_deal_price_input(message: Message, state: FSMContext) -> None:
    """Должен быть выше passive_gift_text: иначе «5» съедается фильтром gift-контекста."""
    if not message.from_user:
        return
    nft_address = runtime_state.pending_deal_get(message.from_user.id)
    if not nft_address:
        return
    raw = (message.text or "").strip().lower().replace("ton", "").strip()
    raw = raw.replace(",", ".")
    try:
        p = float(raw)
        if p <= 0:
            raise ValueError()
    except Exception:
        await message.answer("Нужна цена сделки в TON, например: 95 или 95 TON")
        return
    runtime_state.pending_deal_clear(message.from_user.id)
    await state.clear()
    from app.bot.handlers.market import deal_check

    try:
        message.text = f"/deal {nft_address} | {p:g}"
        await deal_check(message)
    except Exception:
        await message.answer(f"➡️ /deal {nft_address} | {p:g}")


@router.callback_query(F.data == "help:find_nft_link")
async def help_find_nft_link_callback(query: CallbackQuery) -> None:
    await query.answer()
    if query.message:
        await query.message.answer(
            "🔗 Как найти ссылку на NFT\n\n"
            "1. Открой NFT на Getgems / Fragment / Tonviewer.\n"
            "2. Нажми Share / Copy link.\n"
            "3. Пришли ссылку сюда.\n\n"
            "Важно: нужна ссылка именно на конкретный NFT, не просто на коллекцию.\n\n"
            "Можно также прислать NFT address.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Закрыть", callback_data="gift:cancel:0")]
                ]
            ),
        )


@router.message(F.text, ~F.text.startswith("/"))
async def passive_gift_text(message: Message, state: FSMContext) -> None:
    await try_send_nft_preview_card(message, state, (message.text or "").strip())


async def try_send_nft_preview_card(message: Message, state: FSMContext, text: str) -> bool:
    """Показывает короткую карточку NFT с медиа и action-кнопками.

    Возвращает True, если ввод обработан как NFT-контекст; иначе False.
    """
    text = (text or "").strip()
    if not text or "\n" in text:
        return False
    if not _smells_like_gift_context(text) or not is_nft_like_check_payload(text):
        return False

    settings = get_settings()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
    gi = parse_gift_input(text)
    _, identity = await resolve_gift_identity(user, text, settings)

    incomplete = (
        identity.collection in ("Unknown", "")
        and not identity.nft_address
        and identity.number is None
    )
    if incomplete:
        if gi.source_hint == "getgems_startapp_collection_only":
            await message.answer(
                "Это ссылка на коллекцию, а не на конкретный NFT. Пришли ссылку на сам NFT.",
                reply_markup=_link_help_keyboard(),
            )
            return True
        if gi.input_type == GiftInputType.unknown and not smells_like_gift_link(text):
            return False
        progress = await message.answer(
            "Ссылка похожа на Gift/NFT, но в ней нет номера или адреса.\n"
            "Пришли так: /check Ice Cream #217467 или /check <NFT address>.\n\n"
            + format_unknown_gift_input_help(text, gi.parse_warnings, context="check"),
            reply_markup=_close_only_keyboard(),
        )
        return True

    client = TonAPICollectionClient(settings)
    progress = await message.answer("⏳ Ищу NFT...")
    resolved, err = await resolve_universal_nft(text, user, settings, client, learn=True)
    if err or not resolved:
        err_text = (err or "").strip()
        if not err_text or err_text.lower() in {"not_found", "404", "unavailable"}:
            err_text = _friendly_unresolved_message(text, paid=False)
        await _edit_or_answer(
            message,
            progress,
            err_text,
            kb=_link_help_keyboard(),
        )
        return True
    try:
        await message.bot.edit_message_text(
            "✅ NFT найден.",
            chat_id=message.chat.id,
            message_id=progress.message_id,
            reply_markup=None,
        )
    except Exception:
        pass

    nft_raw = resolved.nft_raw
    media = extract_nft_preview_media(nft_raw or {}, ipfs_gateway_url=settings.ipfs_gateway_url)
    anim_u = (getattr(resolved, "animation_url", None) or "").strip()
    if anim_u:
        media = PreviewMedia(
            url=anim_u,
            kind="animation",
            mime_type=None,
            source_field="resolved.animation_url",
        )
    elif not media.url and (resolved.image_url or "").strip():
        media = PreviewMedia(
            url=resolved.image_url.strip(),
            kind="photo",
            mime_type=None,
            source_field="resolved.image_url",
        )

    market_payload = text.strip()
    if (resolved.source or "") == "getgems_web":
        market_payload = (resolved.original_payload or text).strip()

    traits_map = {k: str(v) for k, v in (resolved.traits or {}).items() if v}
    sid = runtime_state.nft_action_session_put(
        user.id,
        nft_address=resolved.nft_address,
        collection_address=resolved.collection_address,
        original_payload=text,
        nft_name=resolved.nft_name,
        collection_name=resolved.collection_name,
        model=resolved.traits.get("model"),
        backdrop=resolved.traits.get("backdrop"),
        symbol=resolved.traits.get("symbol"),
        image_url=resolved.image_url,
        animation_url=getattr(resolved, "animation_url", None),
        sale_price_ton=resolved.sale_price_ton,
        for_sale=resolved.for_sale,
        market_resolve_payload=market_payload,
        getgems_web_preview=(resolved.source or "") == "getgems_web",
        address_kind=getattr(resolved, "address_kind", None),
        resolved_source=(resolved.source or "").strip() or None,
        traits=traits_map or None,
    )
    await state.clear()
    body = _build_preview_text_from_resolved(resolved)
    kb = _resolved_nft_keyboard(sid)
    await _send_resolved_nft_preview(message, resolved=resolved, media=media, body=body, kb=kb)
    return True


@router.callback_query(F.data.startswith("gift:"))
async def passive_gift_callback(query: CallbackQuery, state: FSMContext) -> None:
    data = query.data or ""
    parts = data.split(":", 2)
    if len(parts) < 3:
        await query.answer()
        return
    _, action, sid = parts[0], parts[1], parts[2]
    direct_nft_address: str | None = None
    aliases = {
        "check": "market_check",
        "sell_price": "market_check",
        "add": "watch_add",
        "deal": "deal_check",
    }
    action = aliases.get(action, action)
    if action in {"check_addr", "sell_addr", "add_addr", "deal_addr"}:
        direct_nft_address = sid
        action = aliases.get(action.replace("_addr", ""), action.replace("_addr", ""))
        sid = ""
    if not query.from_user:
        await query.answer()
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(query.from_user.id, query.from_user.username)
    if action == "cancel":
        await query.answer()
        if query.message:
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
        return
    if action == "close":
        runtime_state.pending_gift_cancel(user.id, sid)
        if query.message:
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
        await query.answer("Ок.")
        return
    session_payload = runtime_state.nft_action_session_get(user.id, sid) if sid else None
    if action == "watch_add" and sid and not session_payload and not direct_nft_address:
        await query.answer()
        if query.message:
            lang = text_lang_from_user(user)
            await query.message.answer(
                t("mylist.session_expired", lang),
                reply_markup=my_list_session_expired_inline_keyboard(lang=lang),
            )
        return
    if not session_payload and not direct_nft_address:
        await query.answer("Сессия истекла (15 мин). Пришли ссылку снова.", show_alert=True)
        return

    nft_address = (direct_nft_address or (session_payload or {}).get("nft_address") or "").strip()
    if not nft_address:
        await query.answer("Сессия устарела. Пришли NFT снова.", show_alert=True)
        return
    await state.clear()
    if action == "listing_price":
        await query.answer()
        sp = session_payload or {}
        price = sp.get("sale_price_ton")
        if query.message:
            if price is not None:
                s = f"{float(price):.3f}".rstrip("0").rstrip(".").replace(".", ",")
                await query.message.answer(f"💎 Цена листинга\n\nВыставлен за {s} TON")
            else:
                await query.message.answer(
                    "💎 Цена листинга\n\nПо текущим данным цена в TON не определена. "
                    "Нажми «Проверить рынок» для оценки по коллекции."
                )
        return

    if action == "market_check":
        await query.answer("Проверяю…")
        if query.message:
            from app.bot.handlers.analysis import execute_check_payload

            sp = session_payload or {}
            scan_payload = (sp.get("market_resolve_payload") or "").strip() or nft_address
            await execute_check_payload(
                query.message,
                telegram_id=query.from_user.id,
                username=query.from_user.username,
                payload=scan_payload,
            )
        return
    if action == "watch_add":
        if not query.message:
            await query.answer()
            return
        settings = get_settings()
        async with SessionLocal() as session:
            db_user = await UserRepository(session).get_or_create(query.from_user.id, query.from_user.username)
            lang = text_lang_from_user(db_user)
            gift_repo = GiftRepository(session)
            outcome = await add_to_my_list(
                gift_repo=gift_repo,
                user=db_user,
                settings=settings,
                nft_address=nft_address,
                action_session=session_payload,
            )
        if outcome.result == MyListAddResult.INVALID:
            await query.answer()
            return
        if outcome.result == MyListAddResult.LIMIT:
            await query.answer()
            pl = (db_user.plan or "free").capitalize()
            await query.message.answer(
                format_watchlist_limit_message(
                    pl,
                    outcome.max_gifts,
                    cur=outcome.current_count,
                    lang=lang,
                    settings=settings,
                ),
                reply_markup=my_list_limit_inline_keyboard(lang=lang),
            )
            return
        disp = outcome.display_name
        coll = outcome.collection_display
        if outcome.result == MyListAddResult.UPDATED:
            await query.answer()
            body = (
                f"{t('mylist.already_title', lang)}\n\n"
                f"{t('mylist.line_gift', lang, name=disp)}\n"
                f"{t('mylist.line_collection', lang, collection=coll)}"
            )
            await query.message.answer(body, reply_markup=my_list_after_add_inline_keyboard(lang=lang))
            return
        await query.answer()
        body = (
            f"{t('mylist.added_title', lang)}\n\n"
            f"{t('mylist.line_gift', lang, name=disp)}\n"
            f"{t('mylist.line_collection', lang, collection=coll)}\n\n"
            f"{t('mylist.added_hint', lang)}"
        )
        await query.message.answer(body, reply_markup=my_list_after_add_inline_keyboard(lang=lang))
        return
    if action == "deal_check":
        runtime_state.pending_deal_put(user.id, nft_address=nft_address)
        await query.answer("Жду цену")
        if query.message:
            await query.message.answer("Укажи цену сделки в TON (одним сообщением, без /команд).")
        return
    await query.answer()
