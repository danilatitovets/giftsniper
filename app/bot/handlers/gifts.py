import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.handlers.analysis import execute_check_payload
from app.bot.keyboards import empty_watchlist_inline_keyboard
from app.bot.upgrade_inline import format_watchlist_limit_message, upgrade_inline_keyboard_open
from app.config import get_settings
from app.i18n import t, text_lang_from_user
from app.db.repositories.analysis import AnalysisRepository
from app.db.repositories.gifts import GiftRepository
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.schemas.gift import GiftCard
from app.services.feature_limits import check_usage_limit, get_plan_limits, normalize_plan_for_limits
from app.services.gift_cards import format_gift_watchlist_card
from app.services.gift_intake import (
    GiftIdentity,
    build_canonical_gift_key,
    normalize_gift_collection,
    parse_nft_address,
    scrub_import_line,
)
from app.services.gift_resolver import (
    enrich_identity_with_collection_registry,
    enrich_identity_with_tonapi,
    resolve_gift_identity,
)
from app.sources.collections import load_collection_registry, resolve_collection

router = Router()


def _parse_collection_number_from_body(payload: str) -> tuple[str, int] | None:
    payload = payload.strip()
    if not payload or payload.startswith("http"):
        return None
    m = re.search(r"(.+?)\s+#?(\d+)$", payload)
    if not m:
        return None
    return m.group(1).strip(), int(m.group(2))


def _to_price(raw: str) -> float | None:
    try:
        value = float(raw.replace(",", "."))
        if value <= 0:
            return None
        return value
    except ValueError:
        return None


def _split_import_lines(blob: str) -> list[str]:
    raw = blob.strip()
    if not raw:
        return []
    if ";" in raw:
        chunks = [scrub_import_line(x) for x in raw.split(";")]
    else:
        chunks = [scrub_import_line(ln) for ln in raw.splitlines()]
    return [c for c in chunks if c][:20]


def _watchlist_inline_keyboard(gifts: list, *, lang: str) -> InlineKeyboardMarkup | None:
    if not gifts:
        return None
    rows: list[list[InlineKeyboardButton]] = []
    btn_market = t("mylist.btn_row_market", lang)
    btn_notif = t("notifications.btn", lang)
    for idx, g in enumerate(gifts, start=1):
        rows.append(
            [
                InlineKeyboardButton(text=f"{btn_market} #{idx}", callback_data=f"watchlist:check:{g.id}"),
                InlineKeyboardButton(text=f"{btn_notif} #{idx}", callback_data=f"watchlist:signals:{g.id}"),
            ]
        )
        rows.append([InlineKeyboardButton(text=f"❌ Удалить #{idx}", callback_data=f"watchlist:remove:{g.id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _apply_watch_intake(message: Message, body: str, *, command_label: str) -> None:
    settings = get_settings()
    body = body.strip()
    if not body:
        await message.answer(
            "Скиньте ссылку на NFT (или NFT address / Ice Cream #217467).\n"
            "После карточки нажмите кнопку «✅ Добавить в список»."
        )
        return

    # Коллекция без номера — пока только явный NFT (EQ/UQ или raw 0:… / -1:…)
    if (
        not body.startswith("http")
        and "EQ" not in body
        and "#" not in body
        and _parse_collection_number_from_body(body) is None
        and parse_nft_address(body) is None
    ):
        registry = load_collection_registry(settings.collection_registry_path)
        canonical, payload = resolve_collection(body.strip(), registry=registry)
        if canonical and payload:
            await message.answer(
                "Пока в отслеживание можно добавить конкретный NFT (нужен номер).\n"
                f"Пример: {command_label} Ice Cream #217467 или NFT address / ссылку.\n"
                "Отслеживание всей коллекции без номера — в следующих версиях.",
            )
            return

    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        gift_repo = GiftRepository(session)
        user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)

        parsed = _parse_collection_number_from_body(body)
        if parsed:
            collection, number = parsed
            norm = normalize_gift_collection(collection)
            ident = GiftIdentity(
                collection=norm,
                number=number,
                nft_address=None,
                collection_address=None,
                normalized_collection=norm,
                canonical_key=build_canonical_gift_key(
                    collection=norm, number=number, nft_address=None, normalized_collection=norm
                ),
                confidence=80,
                warnings=[],
            )
            ident = enrich_identity_with_collection_registry(settings, ident)
        else:
            _, ident = await resolve_gift_identity(user, body, settings)
            if ident.collection in ("Unknown", "") or ident.number is None:
                if ident.nft_address:
                    ident = await enrich_identity_with_tonapi(settings, ident)
                    ident = enrich_identity_with_collection_registry(settings, ident)
                if ident.collection in ("Unknown", "") or ident.number is None:
                    await message.answer(
                        "Не удалось распознать. Пришли NFT address, ссылку или текст вида Ice Cream #217467.",
                    )
                    return

        existing = None
        if ident.canonical_key:
            existing = await gift_repo.get_by_canonical_key(user.id, ident.canonical_key)
        if existing is None and ident.nft_address:
            existing = await gift_repo.get_by_nft_address(user.id, ident.nft_address)
        if existing is None and ident.number is not None:
            existing = await gift_repo.get_by_collection_number(user.id, ident.collection, ident.number)

        if existing is None:
            current_count = await gift_repo.count_by_user(user.id)
            allowed, max_allowed = check_usage_limit(user, "max_gifts", current_count)
            if not allowed:
                pl = (user.plan or "free").capitalize()
                lim = get_plan_limits(user.plan)
                lang = text_lang_from_user(user)
                await message.answer(
                    format_watchlist_limit_message(
                        pl,
                        int(lim.get("max_gifts", max_allowed)),
                        cur=current_count,
                        lang=lang,
                        settings=settings,
                    ),
                    reply_markup=upgrade_inline_keyboard_open(lang=lang),
                )
                return

        gift, status = await gift_repo.add_or_update_gift_from_identity(user.id, ident)
        updated = status == "updated"
        card_gift = GiftCard(collection=gift.collection, number=gift.number)
        await message.answer(format_gift_watchlist_card(card_gift, gift.id, updated))


async def send_empty_watchlist_message(
    message: Message,
    *,
    telegram_id: int | None = None,
    username: str | None = None,
) -> None:
    async with SessionLocal() as session:
        actor_tid = int(telegram_id) if telegram_id is not None else int(message.from_user.id)
        actor_username = username if username is not None else message.from_user.username
        user = await UserRepository(session).get_or_create(actor_tid, actor_username)
        lang = text_lang_from_user(user)
    await message.answer(t("watchlist.empty", lang), reply_markup=empty_watchlist_inline_keyboard(lang=lang))


async def send_watchlist_message(
    message: Message,
    *,
    telegram_id: int | None = None,
    username: str | None = None,
) -> None:
    async with SessionLocal() as session:
        actor_tid = int(telegram_id) if telegram_id is not None else int(message.from_user.id)
        actor_username = username if username is not None else message.from_user.username
        user = await UserRepository(session).get_or_create(actor_tid, actor_username)
        lang = text_lang_from_user(user)
        gifts = await GiftRepository(session).list_by_user(user.id)
        analysis_repo = AnalysisRepository(session)
        latest_by_gift: dict[int, float | None] = {}
        for g in gifts:
            row = await analysis_repo.get_latest_for_gift(g.id)
            price = float(row.normal_list_price_ton) if row and row.normal_list_price_ton is not None else None
            latest_by_gift[g.id] = price

    if not gifts:
        await send_empty_watchlist_message(message)
        return

    lines: list[str] = [t("mylist.header", lang), t("mylist.list_hint", lang), ""]
    for i, g in enumerate(gifts, start=1):
        last = latest_by_gift.get(g.id)
        last_s = f"{last:.1f} TON" if last is not None else "нет данных"
        lines.append(f"{i}. {g.collection} #{g.number}")
        lines.append(f"   Последняя оценка: {last_s}")
        st = t("notifications.status_on", lang) if getattr(g, "signals_enabled", False) else t("notifications.status_off", lang)
        lines.append(f"   {st}")
        lines.append("")
    text = "\n".join(lines).strip()
    await message.answer(text, reply_markup=_watchlist_inline_keyboard(gifts, lang=lang))


@router.message(Command("add"))
async def add_gift_handler(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    body = parts[1].strip() if len(parts) > 1 else ""
    await _apply_watch_intake(message, body, command_label="/add")


@router.message(Command("watch"))
async def watch_handler(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    body = parts[1].strip() if len(parts) > 1 else ""
    await _apply_watch_intake(message, body, command_label="/watch")


@router.message(Command("watchlist"))
async def watchlist_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await send_watchlist_message(message)


@router.message(Command("mylist"))
async def mylist_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await send_watchlist_message(message)


@router.callback_query(F.data.startswith("watchlist:"))
async def watchlist_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.data or not callback.from_user or not callback.message:
        await callback.answer()
        return
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    _, action, gid_s = parts
    if not gid_s.isdigit():
        await callback.answer()
        return
    gift_id = int(gid_s)
    uid = callback.from_user.id

    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        gift_repo = GiftRepository(session)
        user = await user_repo.get_or_create(uid, callback.from_user.username)
        gift = await gift_repo.get_by_id(user.id, gift_id)
        if gift is None:
            await callback.answer("Позиция не найдена", show_alert=True)
            return
        if action == "remove":
            await gift_repo.delete_by_id(user.id, gift_id)
            await callback.answer("Удалено из списка")
            await callback.message.answer(f"Удалено из списка: {gift.collection} #{gift.number}")
            return
        if action == "signals":
            lang = text_lang_from_user(user)
            plan = normalize_plan_for_limits(user.plan)
            if plan == "free":
                await callback.answer()
                await callback.message.answer(
                    t("notifications.free_gate", lang),
                    reply_markup=upgrade_inline_keyboard_open(lang=lang),
                )
                return
            new_val = not bool(getattr(gift, "signals_enabled", False))
            await gift_repo.set_signals_enabled(user.id, gift_id, new_val)
            if new_val:
                await callback.answer()
                await callback.message.answer(
                    t("notifications.enabled_title", lang) + "\n\n" + t("notifications.enabled_body", lang)
                )
            else:
                await callback.answer()
                await callback.message.answer(
                    t("notifications.disabled_title", lang) + "\n\n" + t("notifications.disabled_body", lang)
                )
            return
        if action == "check":
            await state.clear()
            await callback.answer()
            payload = (gift.nft_address or "").strip() or f"{gift.collection} #{gift.number}"
            await execute_check_payload(callback.message, payload, telegram_id=uid, username=callback.from_user.username)
            return

    await callback.answer()


@router.callback_query(F.data.startswith("notifications:"))
async def notifications_push_callback(query: CallbackQuery, state: FSMContext) -> None:
    if not query.data or not query.from_user or not query.message:
        await query.answer()
        return
    parts = query.data.split(":")
    if len(parts) != 3:
        await query.answer()
        return
    _, action, gid_s = parts
    if not gid_s.isdigit():
        await query.answer()
        return
    gift_id = int(gid_s)
    uid = query.from_user.id
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        gift_repo = GiftRepository(session)
        user = await user_repo.get_or_create(uid, query.from_user.username)
        gift = await gift_repo.get_by_id(user.id, gift_id)
        lang = text_lang_from_user(user)
        if gift is None:
            await query.answer()
            return
        if action == "off":
            await gift_repo.set_signals_enabled(user.id, gift_id, False)
            await query.answer(t("notifications.toast_off", lang))
            return
        if action == "check":
            await state.clear()
            await query.answer()
            payload = f"{gift.collection} #{gift.number}"
            if (gift.nft_address or "").strip():
                payload = (gift.nft_address or "").strip()
            await execute_check_payload(query.message, payload, telegram_id=uid, username=query.from_user.username)
            return
    await query.answer()


@router.message(Command("import_gifts"))
async def import_gifts_handler(message: Message) -> None:
    settings = get_settings()
    parts = (message.text or "").split(maxsplit=1)
    blob = parts[1] if len(parts) > 1 else ""
    lines = _split_import_lines(blob)
    if not lines:
        await message.answer("Отправь до 20 строк после команды или через `;`:\n/import_gifts\nIce Cream #1\nhttps://...")
        return

    added = updated = skipped = failed = 0
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        gift_repo = GiftRepository(session)
        user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)

        for line in lines:
            _, ident = await resolve_gift_identity(user, line, settings)
            if ident.collection in ("Unknown", "") or ident.number is None:
                if ident.nft_address:
                    ident = await enrich_identity_with_tonapi(settings, ident)
                    ident = enrich_identity_with_collection_registry(settings, ident)
            if ident.collection in ("Unknown", "") or ident.number is None:
                failed += 1
                continue

            existing = None
            if ident.canonical_key:
                existing = await gift_repo.get_by_canonical_key(user.id, ident.canonical_key)
            if existing is None and ident.nft_address:
                existing = await gift_repo.get_by_nft_address(user.id, ident.nft_address)
            if existing is None:
                existing = await gift_repo.get_by_collection_number(user.id, ident.collection, ident.number)

            if existing is None:
                current_count = await gift_repo.count_by_user(user.id)
                allowed, _ = check_usage_limit(user, "max_gifts", current_count)
                if not allowed:
                    skipped += 1
                    continue
            _, st = await gift_repo.add_or_update_gift_from_identity(user.id, ident)
            if st == "created":
                added += 1
            else:
                updated += 1

    await message.answer(
        f"📥 Import gifts\nДобавлено: {added}\nОбновлено: {updated}\nПропущено (лимит): {skipped}\nОшибок: {failed}"
    )


@router.message(Command("repair_gifts"))
async def repair_gifts_handler(message: Message) -> None:
    settings = get_settings()
    fixed = enriched = 0
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        gift_repo = GiftRepository(session)
        user = await user_repo.get_or_create(message.from_user.id, message.from_user.username)
        gifts = await gift_repo.list_by_user(user.id)
        for gift in gifts:
            norm = normalize_gift_collection(gift.collection)
            ident = GiftIdentity(
                collection=gift.collection,
                number=gift.number,
                nft_address=gift.nft_address,
                collection_address=gift.collection_address,
                normalized_collection=gift.normalized_collection or norm,
                canonical_key=gift.canonical_key
                or build_canonical_gift_key(
                    collection=gift.collection, number=gift.number, nft_address=gift.nft_address, normalized_collection=norm
                ),
                source_url=gift.source_url,
                marketplace=gift.marketplace,
                confidence=gift.identity_confidence or 70,
                warnings=[],
            )
            ident = enrich_identity_with_collection_registry(settings, ident)
            if gift.nft_address:
                ident = await enrich_identity_with_tonapi(settings, ident)
                enriched += 1
            before = (gift.canonical_key, gift.normalized_collection)
            await gift_repo.update_gift_identity(user.id, gift.id, ident)
            after = (ident.canonical_key, ident.normalized_collection)
            if before != after:
                fixed += 1
        dups = await gift_repo.list_duplicates(user.id)

    dup_lines = "\n".join(f"- {k}: ids {v}" for k, v in list(dups.items())[:5]) if dups else "нет"
    await message.answer(
        f"🔧 Repair gifts\nОбновлено записей: {fixed}\nTonAPI enrich попыток: {enriched}\nДубли:\n{dup_lines}"
    )


@router.message(Command("list"))
async def list_gifts_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        gifts = await GiftRepository(session).list_by_user(user.id)
        lang = text_lang_from_user(user)
    if not gifts:
        await message.answer(
            t("watchlist.empty", lang),
            reply_markup=empty_watchlist_inline_keyboard(lang=lang),
        )
        return
    lines = [f"{gift.id}. {gift.collection} #{gift.number}" for gift in gifts]
    await message.answer(t("mylist.header", lang).strip() + "\n" + "\n".join(lines))


@router.message(Command("gift_set_buy"))
async def gift_set_buy_handler(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) < 3 or not parts[1].isdigit():
        await message.answer("Используйте: /gift_set_buy <gift_id> <price>")
        return
    price = _to_price(parts[2])
    if price is None:
        await message.answer("Цена должна быть положительным числом.")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        gift = await GiftRepository(session).set_purchase_price(user.id, int(parts[1]), price)
    if gift is None:
        await message.answer("Подарок не найден.")
        return
    await message.answer(f"✅ Цена покупки обновлена: {gift.collection} #{gift.number} = {price:.2f} TON")


@router.message(Command("gift_set_target"))
async def gift_set_target_handler(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) < 3 or not parts[1].isdigit():
        await message.answer("Используйте: /gift_set_target <gift_id> <price>")
        return
    price = _to_price(parts[2])
    if price is None:
        await message.answer("Цена должна быть положительным числом.")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        gift = await GiftRepository(session).set_target_price(user.id, int(parts[1]), price)
    if gift is None:
        await message.answer("Подарок не найден.")
        return
    await message.answer(f"✅ Target price обновлена: {gift.collection} #{gift.number} = {price:.2f} TON")
