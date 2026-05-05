from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import Settings
from app.db.repositories.gifts import GiftRepository
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.schemas.gift import GiftAttributeSchema, GiftCard
from app.services.analyzer import AnalyzerService
from app.services.gift_cards import format_gift_analysis_card, format_unknown_gift_input_help
from app.services.gift_intake import (
    GiftIdentity,
    GiftInputType,
    parse_collection_number,
    parse_nft_address,
    smells_like_gift_link,
)
from app.services.gift_resolver import resolve_gift_identity
from app.sources.factory import create_market_source
from app.bot.ux import format_next_action, format_risk_disclaimer_short
from app.services.signal_snapshots import build_snapshot_seed_from_flip_analysis
from app.i18n import normalize_lang, t, text_lang_from_user
from app.services import runtime_state
from app.services.real_market_collection_scan import (
    FullMarketNftReport,
    format_full_market_nft_report,
    format_full_market_nft_report_for_telegram_edit,
    format_progress_message,
    run_full_market_analysis_flow,
)
from app.services.tonapi_collection_client import TonAPICollectionClient
from app.services.universal_nft_resolver import resolve_universal_nft

logger = logging.getLogger(__name__)

_HAS_HASH_NUMBER_RE = re.compile(r"#\s*\d+")

MSG_NFT_CHECK_NO_TONAPI_KEY = (
    "❌ Не настроен TONAPI_API_KEY. Реальный анализ NFT через TonAPI невозможен."
)
MSG_NFT_CHECK_NO_COLLECTION_ADDR = (
    "❌ Не удалось автоматически определить коллекцию.\n\n"
    "Пришли NFT address или ссылку на NFT — так я смогу получить коллекцию через TonAPI."
)
MSG_NFT_CHECK_TONAPI_UNAVAILABLE = (
    "❌ TonAPI сейчас недоступен или вернул ошибку. Повтори запрос позже или пришли другую ссылку на NFT."
)


def is_nft_like_check_payload(payload: str) -> bool:
    """Признаки NFT-маршрута /check: адрес TON, URL, «коллекция #номер», #число в строке, id watchlist."""
    p = (payload or "").strip()
    if not p:
        return False
    if p.isdigit():
        return True
    if parse_nft_address(p):
        return True
    if p.lower().startswith(("http://", "https://")):
        return True
    if parse_collection_number(p):
        return True
    if _HAS_HASH_NUMBER_RE.search(p):
        return True
    return False


def _map_nft_full_market_error(err: str | None) -> str:
    if not err or not str(err).strip():
        return MSG_NFT_CHECK_TONAPI_UNAVAILABLE
    err = str(err).strip()
    low = err.lower()
    if "tonapi_api_key" in low or "api key не задан" in low or "api_key" in low:
        return MSG_NFT_CHECK_NO_TONAPI_KEY
    if err.startswith("❌") or err.startswith("⚠️"):
        return err
    if "collections.json" in low:
        return MSG_NFT_CHECK_NO_COLLECTION_ADDR
    if "tonapi_enabled=false" in low:
        return "❌ TonAPI отключён в настройках (TONAPI_ENABLED=false). Реальный анализ NFT недоступен."
    if "timeout" in low:
        return "❌ TonAPI не ответил вовремя. Повтори проверку через минуту или пришли прямой NFT address."
    if "429" in low or "rate limit" in low:
        return "❌ TonAPI временно ограничил запросы (429). Подожди немного и нажми «Проверить рынок» снова."
    if "полный скан рынка выключен" in low or "full_market_scan_enabled" in low:
        return f"❌ {err}"
    if "загруженных" in low and "не найден" in low:
        return f"❌ {err}"
    return MSG_NFT_CHECK_TONAPI_UNAVAILABLE


async def _finalize_nft_check_telegram_message(message: Message, progress_msg: Message, body: str) -> None:
    text = body if len(body) <= 4090 else body[:4087] + "…"
    try:
        await message.bot.edit_message_text(
            text,
            chat_id=message.chat.id,
            message_id=progress_msg.message_id,
        )
    except Exception:
        await message.answer(text)


def build_nft_check_result_keyboard(sidebar_id: str, *, nft_address: str | None, lang: str | None = None) -> InlineKeyboardMarkup:
    lg = normalize_lang(lang)
    row1: list[InlineKeyboardButton] = [
        InlineKeyboardButton(text="📊 Полный отчёт", callback_data=f"check:full:{sidebar_id}")
    ]
    if nft_address:
        row1.append(
            InlineKeyboardButton(text=t("mylist.btn_add_from_check", lg), callback_data=f"watch:add:{sidebar_id}")
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            row1,
            [InlineKeyboardButton(text="🚀 Upgrade", callback_data="upgrade:open")],
        ]
    )


async def deliver_full_market_nft_check_result(
    message: Message,
    progress_msg: Message,
    report: FullMarketNftReport,
    *,
    telegram_id: int,
    skip_photo_if_url: str | None = None,
    edit_only: bool = False,
    lang: str | None = None,
) -> None:
    """Финал /check: одно сообщение — правка progress, без отдельного медиа и без «Готово»."""
    _ = skip_photo_if_url
    _ = edit_only
    full_plain = format_full_market_nft_report(report)
    sidebar_body = full_plain if len(full_plain) <= 16000 else full_plain[:15997] + "…"
    display = format_full_market_nft_report_for_telegram_edit(report, max_len=4090)

    addr = (report.target.address or "").strip() or None
    tinfo = report.target
    snapshot: dict[str, Any] | None = None
    if addr:
        snapshot = {
            "nft_name": tinfo.name,
            "collection_name": tinfo.collection_name,
            "collection_address": (tinfo.collection_address or "").strip() or None,
            "address_kind": getattr(tinfo, "address_kind", None),
            "resolved_source": (report.scan_target_source or report.source_label or "").strip() or None,
            "image_url": (tinfo.image_url or "").strip() or None,
        }
        if tinfo.traits_normalized:
            snapshot["traits"] = dict(tinfo.traits_normalized)
    sidebar_id = runtime_state.nft_check_sidebar_put(
        telegram_id, full_report=sidebar_body, nft_address=addr, snapshot=snapshot
    )
    kb = build_nft_check_result_keyboard(sidebar_id, nft_address=addr, lang=lang)

    try:
        await message.bot.edit_message_text(
            display,
            chat_id=message.chat.id,
            message_id=progress_msg.message_id,
            reply_markup=kb,
        )
    except Exception:
        await message.answer(display, reply_markup=kb)


def gift_attrs_for_demo(gift: GiftCard) -> GiftCard:
    if gift.collection.lower() == "ice cream" and gift.number == 217467:
        gift.attributes = [
            GiftAttributeSchema(trait_type="Model", trait_value="Vice Dream", rarity_percent=3.0),
            GiftAttributeSchema(trait_type="Backdrop", trait_value="Ivory White", rarity_percent=1.2),
            GiftAttributeSchema(trait_type="Symbol", trait_value="Moon", rarity_percent=0.7),
        ]
    return gift


async def run_analysis_for_watchlist(
    telegram_id: int,
    gift_id: int,
    settings: Settings,
) -> tuple[GiftCard, Any, float | None, Any, dict] | None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(telegram_id, None)
        gift = await GiftRepository(session).get_by_id(user.id, gift_id)
    if gift is None:
        return None
    gift_card = GiftCard(collection=gift.collection, number=gift.number, title=gift.title)
    gift_card = gift_attrs_for_demo(gift_card)
    analyzer = AnalyzerService(create_market_source(settings, user_id=user.id))
    estimate = await analyzer.analyze_gift(
        gift_card,
        risk_mode=user.risk_mode,
        buy_price_ton=gift.purchase_price_ton,
        owns_asset=True,
    )
    return gift_card, estimate, gift.purchase_price_ton, analyzer.last_data_quality, analyzer.last_market_stats


def build_next_actions_watchlist(gift_id: int) -> str:
    return format_next_action(f"/analyze {gift_id}")


def build_next_actions_universal(_identity: GiftIdentity) -> str:
    return format_next_action("/add <то же самое> — в watchlist, затем /analyze <id>")


@dataclass
class UniversalCheckOutcome:
    ok: bool
    text: str | None = None
    error: str | None = None
    snapshot_seed: dict | None = None


async def resolve_full_market_scan_payload(
    telegram_id: int,
    username: str | None,
    payload: str,
) -> str | None:
    """Same text as /check: watchlist id, collection #num, NFT address, or link-resolvable string."""
    p = (payload or "").strip()
    if not p:
        return None
    if p.isdigit():
        async with SessionLocal() as session:
            user = await UserRepository(session).get_or_create(telegram_id, username)
            gift = await GiftRepository(session).get_by_id(user.id, int(p))
        if gift is None:
            return None
        addr = (gift.nft_address or "").strip()
        if addr:
            return addr
        return f"{gift.collection} #{gift.number}"
    return p


async def deliver_nft_check_tonapi_only(
    message: Message,
    *,
    telegram_id: int,
    username: str | None,
    payload: str,
    settings: Settings,
) -> tuple[Literal["legacy", "done"], bool]:
    """
    Для NFT-подобного ввода — только TonAPI full-market. Возвращает ``legacy``, если ввод не NFT-like.
    Для NFT-like после первой проверки **никогда** не возвращает ``legacy``: только ``done`` и ответ в чат.
    """
    if not is_nft_like_check_payload(payload):
        return "legacy", False

    scan_payload = await resolve_full_market_scan_payload(telegram_id, username, payload)
    if not scan_payload:
        await message.answer(
            "❌ Запись не найдена. Добавьте подарок через /add или пришлите ссылку, адрес или «коллекция #номер»."
        )
        return "done", False

    if not settings.full_market_scan_enabled:
        await message.answer("❌ Полный скан рынка выключен (FULL_MARKET_SCAN_ENABLED=false).")
        return "done", False

    if not settings.tonapi_enabled:
        await message.answer(
            "❌ TonAPI отключён в настройках (TONAPI_ENABLED=false). Реальный анализ NFT недоступен."
        )
        return "done", False

    if not (settings.tonapi_api_key or "").strip():
        await message.answer(MSG_NFT_CHECK_NO_TONAPI_KEY)
        return "done", False

    client = TonAPICollectionClient(settings)
    if not client.configured:
        await message.answer(MSG_NFT_CHECK_NO_TONAPI_KEY)
        return "done", False

    async with SessionLocal() as session:
        db_user = await UserRepository(session).get_or_create(telegram_id, username)

    lang = text_lang_from_user(db_user)

    resolved, resolve_err = await resolve_universal_nft(
        scan_payload,
        db_user,
        settings,
        client,
        learn=False,
    )
    if resolve_err or not resolved:
        await message.answer(_map_nft_full_market_error(resolve_err))
        return "done", False
    tgt_resolved = resolved.target

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
            logger.debug("check full-market progress edit skipped: %s", exc)

    try:
        report, err = await run_full_market_analysis_flow(
            scan_payload,
            db_user,
            settings,
            client,
            on_progress=on_progress,
            pre_resolved_target=tgt_resolved,
        )
    except Exception:
        logger.exception("full market during /check failed")
        await _finalize_nft_check_telegram_message(message, progress_msg, MSG_NFT_CHECK_TONAPI_UNAVAILABLE)
        return "done", False

    if report:
        await deliver_full_market_nft_check_result(
            message,
            progress_msg,
            report,
            telegram_id=telegram_id,
            skip_photo_if_url=None,
            edit_only=False,
            lang=lang,
        )
        return "done", True
    await _finalize_nft_check_telegram_message(
        message, progress_msg, _map_nft_full_market_error(err)
    )

    return "done", False


async def run_gift_check(
    telegram_id: int,
    username: str | None,
    raw_payload: str,
    settings: Settings,
    *,
    short: bool = True,
) -> UniversalCheckOutcome:
    payload = raw_payload.strip()
    if payload.isdigit():
        result = await run_analysis_for_watchlist(telegram_id, int(payload), settings)
        if result is None:
            return UniversalCheckOutcome(False, error="Подарок не найден. Добавь через /add или универсальный ввод.")
        gift, estimate, purchase_price, quality, stats = result
        card = format_gift_analysis_card(
            gift, estimate, quality, stats, compact=short, purchase_price=purchase_price
        )
        body = (
            f"🔎 Быстрая проверка\n{card}\n"
            f"{build_next_actions_watchlist(int(payload))}\n"
            f"{format_risk_disclaimer_short()}"
        )
        seed = build_snapshot_seed_from_flip_analysis(
            source_command="check",
            gift=gift,
            estimate=estimate,
            stats=stats,
            quality=quality,
            input_text=payload,
        )
        return UniversalCheckOutcome(True, text=body, snapshot_seed=seed)

    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(telegram_id, username)
    gi, identity = await resolve_gift_identity(user, payload, settings)

    if gi.input_type == GiftInputType.unknown:
        err = format_unknown_gift_input_help(payload, gi.parse_warnings, context="check")
        if smells_like_gift_link(payload):
            err += "\n\nПохоже на ссылку маркетплейса — вставь её целиком с https:// (без обрезки)."
        return UniversalCheckOutcome(False, error=err)

    if identity.collection in ("Unknown", "") or identity.number is None:
        if identity.nft_address:
            identity.collection = identity.normalized_collection or "On-chain NFT"
            identity.number = 0
        else:
            return UniversalCheckOutcome(
                False,
                error=(
                    "Недостаточно данных для анализа. Добавь номер или NFT address.\n"
                    + format_unknown_gift_input_help(payload, gi.parse_warnings, context="check")
                ),
            )

    gift_card = GiftCard(collection=identity.collection, number=identity.number)
    gift_card = gift_attrs_for_demo(gift_card)
    analyzer = AnalyzerService(create_market_source(settings, user_id=user.id))
    buy_hint = gi.listing_price_ton
    estimate = await analyzer.analyze_gift(gift_card, risk_mode=user.risk_mode, buy_price_ton=buy_hint)
    quality = analyzer.last_data_quality
    stats = analyzer.last_market_stats
    card = format_gift_analysis_card(
        gift_card, estimate, quality, stats, compact=short, purchase_price=buy_hint
    )
    extra = ""
    if identity.warnings:
        extra = "\nЗаметки:\n" + "\n".join(f"- {w}" for w in identity.warnings[:4])
    body = (
        f"🔎 Проверка подарка\n{card}{extra}\n"
        f"{build_next_actions_universal(identity)}\n"
        f"{format_risk_disclaimer_short()}"
    )
    seed = build_snapshot_seed_from_flip_analysis(
        source_command="check",
        gift=gift_card,
        estimate=estimate,
        stats=stats,
        quality=quality,
        input_text=payload,
        nft_address=identity.nft_address,
        source_url=identity.source_url,
    )
    return UniversalCheckOutcome(True, text=body, snapshot_seed=seed)


async def run_gift_analyze_watchlist(
    telegram_id: int,
    gift_id: int,
    settings: Settings,
) -> tuple[GiftCard, Any, float | None, Any, dict] | None:
    return await run_analysis_for_watchlist(telegram_id, gift_id, settings)


async def run_gift_deal_core(
    user: Any,
    gift: GiftCard,
    buy_price_ton: float,
    settings: Settings,
) -> tuple[Any, Any, dict, Any]:
    gift = gift_attrs_for_demo(gift)
    analyzer = AnalyzerService(create_market_source(settings, user_id=user.id))
    est = await analyzer.analyze_gift(
        gift, risk_mode=user.risk_mode, buy_price_ton=buy_price_ton, owns_asset=False
    )
    return est, analyzer.last_data_quality, analyzer.last_market_stats, analyzer
