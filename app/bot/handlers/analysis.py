from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import (
    my_list_after_add_inline_keyboard,
    my_list_limit_inline_keyboard,
    my_list_session_expired_inline_keyboard,
)
from app.bot.upgrade_inline import format_watchlist_limit_message
from app.config import get_settings
from app.db.repositories.gifts import GiftRepository
from app.db.repositories.signal_snapshots import SignalSnapshotRepository
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.i18n import t, text_lang_from_user
from app.schemas.gift import GiftCard
from app.services.analyzer import AnalyzerService
from app.services.feature_limits import normalize_plan_for_limits
from app.services import gift_analysis_flow as gift_flow
from app.services.gift_analysis_flow import (
    gift_attrs_for_demo,
    run_analysis_for_watchlist,
    run_gift_check,
)
from app.services.gift_cards import format_gift_analysis_card
from app.services.market_data_validity import filter_mock_listings_for_production
from app.services.opportunity_scoring import calculate_opportunity_score, rank_opportunities
from app.services.pricing import is_viable_flip
from app.sources.factory import create_market_source
from app.utils.text import clamp_reason_lines
from app.bot.ux import format_next_action, format_risk_disclaimer_short
from app.services import runtime_state
from app.services.watchlist_add_flow import MyListAddResult, add_to_my_list, snapshot_to_action_session
from app.services.signal_snapshots import build_snapshot_seed_from_flip_analysis, signal_feedback_footer

router = Router()


def _minutes_to_human(minutes: int | None) -> str:
    if minutes is None:
        return "unknown"
    if minutes < 60:
        return f"{minutes} мин назад"
    if minutes < 1440:
        return f"{minutes // 60} ч назад"
    return f"{minutes // 1440} дней назад"


def _passes_scan_filters(
    estimate,
    settings,
    freshness_label: str,
    is_mock: bool,
    real_sales_count: int,
    listing_price_ton: float | None = None,
) -> bool:
    mb = float(getattr(estimate, "buy_zone_max_ton", 0) or 0)
    lp = float(listing_price_ton or 0)
    if lp > 0 and mb > 0 and lp > mb * 1.02:
        return False
    if getattr(estimate, "pricing_suppressed", False):
        return False
    dt = getattr(estimate, "decision_type", None)
    if dt == "STRONG_BUY" and real_sales_count < 3:
        return False
    mts = getattr(estimate, "max_trait_recent_sales", None)
    liq_r = float(getattr(estimate, "liquidity_adjusted_rarity_score", 0) or 0)
    if dt == "STRONG_BUY" and mts == 0 and liq_r >= 45:
        return False
    return (
        estimate.expected_profit_ton >= settings.min_profit_ton
        and is_viable_flip(estimate, risk_mode=settings.default_risk_mode, settings=settings)
        and estimate.confidence_score >= 45
        and estimate.risk_score <= 80
        and not (freshness_label == "old" and not real_sales_count)
        and not (is_mock and estimate.recommendation == "BUY_FOR_FLIP")
        and dt not in {"AVOID", "NEED_MORE_DATA"}
    )


def _verdict_text(recommendation: str) -> str:
    if recommendation in {"BUY_FOR_FLIP", "LIST_HIGHER"}:
        return "🟢 Можно смотреть к покупке"
    if recommendation in {"BUY_ONLY_CHEAP", "HOLD"}:
        return "🟡 Только если дешевле"
    return "🔴 Не покупать сейчас"


@router.message(Command("gift"))
async def gift_card_handler(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Используйте: /gift <id>")
        return
    result = await run_analysis_for_watchlist(message.from_user.id, int(parts[1]), get_settings())
    if result is None:
        await message.answer("Подарок не найден.")
        return
    gift, estimate, purchase_price, quality, stats = result
    card = format_gift_analysis_card(
        gift, estimate, quality, stats, compact=True, purchase_price=purchase_price
    )
    await message.answer(f"🎁 Gift #{parts[1]}\n{card}")


@router.message(Command("analyze"))
async def analyze_handler(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Используйте: /analyze <id>")
        return
    result = await run_analysis_for_watchlist(message.from_user.id, int(parts[1]), get_settings())
    if result is None:
        await message.answer("Подарок не найден.")
        return
    gift, estimate, purchase_price, quality, stats = result
    top_card = format_gift_analysis_card(
        gift, estimate, quality, stats, compact=False, purchase_price=purchase_price
    )
    roi_note = "ROI расчетный, потому что цена покупки не указана" if estimate.roi_based_on_estimated_buy_zone else ""
    main_note = (
        "Не продавать по floor, есть потенциал выше рынка."
        if estimate.recommendation in ("LIST_HIGHER", "HOLD")
        else "Проверить быструю фиксацию или осторожный вход по buy zone."
    )
    quality_label = "mock" if quality.is_mock_data else ("partial" if quality.is_partial_data else "ok")
    sources_text = ", ".join(quality.sources_used) if quality.sources_used else "unknown"
    warnings_text = "\n".join(f"- {w}" for w in quality.warnings) if quality.warnings else "- нет"
    freshness_label = "old" if "old" in [stats.get("floor_freshness"), stats.get("sales_freshness")] else (
        "stale" if "stale" in [stats.get("floor_freshness"), stats.get("sales_freshness"), stats.get("listings_freshness")] else "fresh"
    )
    score = calculate_opportunity_score(
        estimate,
        quality,
        {
            "label": freshness_label,
            "has_recent_sales": bool(stats.get("sales_age_minutes") is not None and stats.get("sales_age_minutes") <= 7 * 24 * 60),
        },
    )
    await message.answer(
        top_card
        + "\n---\n"
        f"🎯 Главный вывод:\n{main_note}\n\n"
        f"💰 Цены:\n"
        f"Buy zone: {estimate.buy_zone_min_ton}-{estimate.buy_zone_max_ton} TON\n"
        f"Quick sell: {estimate.quick_sell_price_ton} TON\n"
        f"Fair price: {estimate.fair_price_ton} TON\n"
        f"List price: {estimate.list_price_ton} TON\n"
        f"Stop price: {estimate.stop_price_ton} TON\n\n"
        f"📈 Экономика:\n"
        f"Цена входа: {(f'{purchase_price:.2f} TON' if purchase_price else 'по расчетной buy zone')}\n"
        f"Комиссия: {estimate.marketplace_fee_percent}%\n"
        f"Чистыми при продаже: {estimate.expected_net_sale_ton} TON\n"
        f"Ожидаемый профит: {estimate.expected_profit_ton:+.2f} TON\n"
        f"ROI: {estimate.expected_roi_percent:+.2f}%\n"
        f"{(roi_note + chr(10)) if roi_note else ''}\n"
        f"🌊 Ликвидность и риск:\n"
        f"Liquidity score: {estimate.liquidity_score}/100\n"
        f"Risk score: {estimate.risk_score}/100\n"
        f"Confidence: {estimate.confidence_score}/100\n\n"
        f"📡 Данные:\n"
        f"Источники: {sources_text}\n"
        f"Качество: {quality_label}\n"
        f"Real floor: {'yes' if stats.get('real_floor') else 'no'}\n"
        f"Real listings: {stats.get('real_listings_count', 0)}\n"
        f"Real sales: {stats.get('real_sales_count', 0)}\n"
        f"Manual floor: {'yes' if stats.get('manual_floor') else 'no'}\n"
        f"Manual trait floors: {stats.get('manual_trait_count', 0)}\n"
        f"Manual sales: {stats.get('manual_sales_count', 0)}\n"
        f"Data age: n/a\n"
        f"Warning: ручные данные могут устареть\n"
        f"Trait attributes: {'available' if stats.get('trait_attributes_available') else 'unavailable'}\n"
        f"Confidence cap reason: {stats.get('confidence_cap_reason') or 'none'}\n"
        f"Предупреждения:\n{warnings_text}\n\n"
        f"⏱ Свежесть данных:\n"
        f"Floor: {stats.get('floor_freshness', 'unknown')}, {_minutes_to_human(stats.get('floor_age_minutes'))}\n"
        f"Trait floors: {stats.get('trait_freshness', 'unknown')}, {_minutes_to_human(stats.get('trait_age_minutes'))}\n"
        f"Listings: {stats.get('listings_freshness', 'unknown')}, {_minutes_to_human(stats.get('listings_age_minutes'))}\n"
        f"Sales: {stats.get('sales_freshness', 'unknown')}, {_minutes_to_human(stats.get('sales_age_minutes'))}\n\n"
        f"Влияние:\n"
        f"- confidence снижен по freshness: {'yes' if stats.get('floor_freshness') in ('stale','old') or stats.get('sales_freshness') in ('stale','old') else 'no'}\n"
        f"- риск повышен из-за старых продаж: {'yes' if stats.get('sales_freshness') == 'old' else 'no'}\n\n"
        f"🧠 Оценка возможности:\n"
        f"Score: {score.total_score}/100 — {score.final_rank_label}\n"
        f"Лучшее действие: {estimate.recommendation}\n"
        f"Почему score не выше:\n"
        f"{('- ' + chr(10) + '- '.join(score.breakdown[-3:])) if score.breakdown else '- нет'}\n\n"
        f"✅ Рекомендация:\n{estimate.recommendation}\n\n"
        f"Почему:\n{clamp_reason_lines(estimate.reasons)}"
    )


async def execute_check_payload(
    message: Message,
    payload: str,
    *,
    telegram_id: int | None = None,
    username: str | None = None,
) -> None:
    payload = (payload or "").strip()
    uid = telegram_id if telegram_id is not None else message.from_user.id
    uname = username if username is not None else message.from_user.username
    async with SessionLocal() as session:
        u = await UserRepository(session).get_or_create(uid, uname)
    lang = text_lang_from_user(u)
    if not payload:
        await message.answer(t("check.need_payload", lang))
        return
    from app.services.nft_check_limits import assert_nft_daily_check_allowed, record_successful_nft_check

    if not await assert_nft_daily_check_allowed(message, uid, uname):
        return
    settings = get_settings()
    route, tonapi_ok = await gift_flow.deliver_nft_check_tonapi_only(
        message,
        telegram_id=uid,
        username=uname,
        payload=payload,
        settings=settings,
    )
    if route == "done":
        if tonapi_ok:
            await record_successful_nft_check(uid, uname, notify_message=message)
        return

    if route == "legacy":
        if gift_flow.is_nft_like_check_payload(payload) and settings.production_mode:
            await message.answer(
                "❌ Не удалось выполнить реальный TonAPI-анализ NFT. "
                "Mock/legacy-анализ в production отключён."
            )
            return

    out = await run_gift_check(uid, uname, payload, settings, short=True)
    if not out.ok:
        await message.answer(out.error or "Ошибка.")
        return
    await record_successful_nft_check(uid, uname, notify_message=message)
    text = out.text or ""
    if out.snapshot_seed:
        async with SessionLocal() as session:
            user = await UserRepository(session).get_or_create(uid, uname)
            snap = await SignalSnapshotRepository(session).create(user_id=user.id, **out.snapshot_seed)
            text = text + signal_feedback_footer(snap.id)
    await message.answer(text)


@router.message(Command("check"))
async def check_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        async with SessionLocal() as session:
            u = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        lang = text_lang_from_user(u)
        await message.answer(t("check.need_payload", lang))
        return
    await execute_check_payload(message, parts[1].strip())


@router.message(Command("deals"))
async def deals_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        has_universe = bool([x for x in await UserRepository(session).list_universe(user.id) if x.is_active])
    plan = (user.plan or "free").lower()
    if normalize_plan_for_limits(plan) in {"pro", "sniper"} and has_universe:
        await message.answer("Запускаю расширенный поиск по Universe (/scan_universe).")
        from app.bot.handlers.portfolio import scan_universe_handler

        await scan_universe_handler(message)
        return
    if plan == "free":
        await message.answer(
            "На Free доступен базовый поиск. Запускаю /scan.\n"
            f"{format_next_action('/upgrade для Universe-скана и расширенных сигналов')}"
        )
    else:
        await message.answer("Запускаю базовый поиск сделок (/scan).")
    await _scan_handler_impl(message, include_doubtful=False)


async def _scan_handler_impl(message: Message, include_doubtful: bool) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
    source = create_market_source(settings, user_id=user.id)
    items = await source.search_underpriced("Ice Cream", filters={})
    items = filter_mock_listings_for_production(settings, items)
    if not items:
        if settings.production_mode and not settings.allow_mock_in_production and settings.block_trading_verdict_on_mock:
            await message.answer(
                "Нет real/manual кандидатов. Mock отключён для trading в production.\n"
                "Добавьте /market_set_* или подключите Getgems/Tonnel/Fragment — см. /sources."
            )
        else:
            await message.answer("Пока недооцененных лотов не найдено.")
        return
    opportunities: list[dict] = []
    doubtful: list[dict] = []
    analyzer = AnalyzerService(source)
    for listing in items:
        gift = gift_attrs_for_demo(GiftCard(collection=listing.collection, number=listing.number))
        estimate = await analyzer.analyze_gift(gift, risk_mode=settings.default_risk_mode, buy_price_ton=listing.price_ton)
        data_quality = analyzer.last_data_quality
        stats = analyzer.last_market_stats
        source_title = ", ".join(data_quality.sources_used) if data_quality.sources_used else listing.source.title()
        warnings = "\n".join(f"- {w}" for w in data_quality.warnings) if data_quality.warnings else "- нет"
        listing_freshness = stats.get("listings_freshness", "unknown")
        signal_label = (
            "real listing signal"
            if listing.source.lower() in {"getgems", "tonnel", "fragment"}
            else (
                "manual estimate, verify before buying (fresh)"
                if listing.source.lower() == "manual" and listing_freshness == "fresh"
                else (
                    "manual estimate, verify before buying (stale)"
                    if listing.source.lower() == "manual"
                    else "test signal"
                )
            )
        )
        if listing.source.lower() == "manual" and listing_freshness == "old":
            signal_label = "manual estimate, stale data"
        freshness_label = "old" if "old" in [stats.get("floor_freshness"), stats.get("sales_freshness")] else (
            "stale" if "stale" in [stats.get("floor_freshness"), stats.get("sales_freshness"), stats.get("listings_freshness")] else "fresh"
        )
        score = calculate_opportunity_score(
            estimate,
            data_quality,
            {
                "label": freshness_label,
                "has_recent_sales": bool(stats.get("sales_age_minutes") is not None and stats.get("sales_age_minutes") <= 7 * 24 * 60),
                "listing_price_ton": float(listing.price_ton),
                "real_sales_count": int(stats.get("real_sales_count") or 0),
                "spread_percent": float(stats.get("spread_percent") or 0),
            },
        )
        candidate = {
            "listing": listing,
            "estimate": estimate,
            "quality": data_quality,
            "stats": stats,
            "source_title": source_title,
            "warnings": warnings,
            "signal_label": signal_label,
            "score": score,
        }
        strict_ok = _passes_scan_filters(
            estimate,
            settings,
            freshness_label,
            data_quality.is_mock_data,
            int(candidate["stats"].get("real_sales_count") or 0),
            listing_price_ton=float(listing.price_ton),
        )
        if strict_ok:
            opportunities.append(candidate)
        else:
            doubtful.append(candidate)
    ranked = rank_opportunities(opportunities)
    if not ranked and not include_doubtful:
        await message.answer("Сейчас нет сделок, которые проходят фильтр profit/ROI/risk.")
        return
    snap_by_idx: dict[int, int] = {}
    async with SessionLocal() as session:
        usr = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        repo = SignalSnapshotRepository(session)
        for idx, item in enumerate(ranked[:3], start=1):
            listing = item["listing"]
            gift = gift_attrs_for_demo(GiftCard(collection=listing.collection, number=listing.number))
            seed = build_snapshot_seed_from_flip_analysis(
                source_command="scan",
                gift=gift,
                estimate=item["estimate"],
                stats=item["stats"],
                quality=item["quality"],
                score=item["score"],
                input_text=f"{listing.collection} #{listing.number}",
            )
            snap = await repo.create(user_id=usr.id, **seed)
            snap_by_idx[idx] = snap.id

    lines = ["🏆 Топ флип-возможностей\n"]
    for idx, item in enumerate(ranked[:5], start=1):
        listing = item["listing"]
        estimate = item["estimate"]
        score = item["score"]
        block = (
            f"#{idx} {listing.collection} #{listing.number}\n"
            f"Tier: {score.final_rank_label}\n"
            f"Score: {score.total_score}/100\n"
            f"Buy: {listing.price_ton:.2f} TON\n"
            f"List: {estimate.list_price_ton} TON\n"
            f"Net after fee: {estimate.expected_net_sale_ton} TON\n"
            f"Profit: {estimate.expected_profit_ton:+.2f} TON\n"
            f"ROI: {estimate.expected_roi_percent:+.2f}%\n"
            f"Risk: {estimate.risk_score}/100\n"
            f"Confidence: {estimate.confidence_score}/100\n"
            f"Freshness: {item['stats'].get('listings_freshness', 'unknown')}\n"
            f"Signal: {item['signal_label']}\n\n"
            f"Почему:\n{clamp_reason_lines(estimate.reasons)}"
        )
        if idx in snap_by_idx:
            block += signal_feedback_footer(snap_by_idx[idx])
        lines.append(block)
    if include_doubtful and doubtful:
        lines.append("\n⚠️ Сомнительные варианты:\n")
        for item in rank_opportunities(doubtful)[:5]:
            listing = item["listing"]
            estimate = item["estimate"]
            score = item["score"]
            lines.append(
                f"{listing.collection} #{listing.number} — {score.final_rank_label}, score {score.total_score}/100, "
                f"profit {estimate.expected_profit_ton:+.2f}, ROI {estimate.expected_roi_percent:+.2f}%"
            )
    await message.answer("\n\n".join(lines))


@router.message(Command("scan"))
async def scan_handler(message: Message) -> None:
    await _scan_handler_impl(message, include_doubtful=False)


@router.message(Command("scan_all"))
async def scan_all_handler(message: Message) -> None:
    await _scan_handler_impl(message, include_doubtful=True)


@router.callback_query(F.data.startswith("check:full:"))
async def nft_check_full_report_callback(query: CallbackQuery) -> None:
    if not query.from_user or not query.data:
        await query.answer()
        return
    sid = query.data.split(":", 2)[-1]
    full, _addr, _snap = runtime_state.nft_check_sidebar_get(query.from_user.id, sid)
    if not full:
        await query.answer("Отчёт устарел. Запусти /check снова.", show_alert=True)
        return
    await query.answer()
    if query.message:
        await query.message.answer(full)


@router.callback_query(F.data.startswith("watch:add:"))
async def nft_check_watch_add_callback(query: CallbackQuery) -> None:
    if not query.from_user or not query.data or not query.message:
        await query.answer()
        return
    sid = query.data.split(":", 2)[-1]
    uid = query.from_user.id
    uname = query.from_user.username
    _full, addr, snap = runtime_state.nft_check_sidebar_get(uid, sid)
    if not addr:
        await query.answer()
        async with SessionLocal() as session:
            u = await UserRepository(session).get_or_create(uid, uname)
        lang = text_lang_from_user(u)
        await query.message.answer(
            t("mylist.session_expired", lang),
            reply_markup=my_list_session_expired_inline_keyboard(lang=lang),
        )
        return
    settings = get_settings()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(uid, uname)
        lang = text_lang_from_user(user)
        plan_label = (user.plan or "free").capitalize()
        gift_repo = GiftRepository(session)
        action_session = snapshot_to_action_session(snap, nft_address=addr)
        outcome = await add_to_my_list(
            gift_repo=gift_repo,
            user=user,
            settings=settings,
            nft_address=addr,
            action_session=action_session,
        )
    if outcome.result == MyListAddResult.INVALID:
        await query.answer()
        return
    if outcome.result == MyListAddResult.LIMIT:
        await query.answer()
        pl = plan_label
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
