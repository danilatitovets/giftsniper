from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import get_settings
from app.db.repositories.gifts import GiftRepository
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.schemas.gift import GiftCard
from app.services.analyzer import AnalyzerService
from app.services.capital_allocation import allocate_capital, allocate_capital_dynamic, format_capital_plan
from app.services.diversification import (
    calculate_collection_exposure,
    calculate_diversification_score,
    calculate_trait_exposure,
    get_concentration_warnings,
)
from app.services.market_regime import (
    evaluate_collection_regime,
    evaluate_universe_regime,
    format_market_regime_report,
    get_regime_allocation_multiplier,
)
from app.services.audit import log_audit
from app.services.feature_limits import assert_feature_allowed, check_usage_limit
from app.services.opportunity_scoring import calculate_opportunity_score, rank_opportunities
from app.services.capital_multiplier import flip_candidate_from_opportunity_row, metrics_for_owned_gift
from app.services.portfolio import aggregate_portfolio
from app.services.market_data_validity import filter_mock_listings_for_production
from app.services.universe_opportunities import gather_ranked_universe_opportunities
from app.sources.factory import create_market_source

router = Router()


def _parse_positive_amount(text: str, cmd: str) -> float | None:
    payload = text.removeprefix(cmd).strip().replace(",", ".")
    try:
        value = float(payload)
        if value <= 0:
            return None
        return value
    except ValueError:
        return None


def _parse_risk(text: str) -> tuple[int, int, int] | None:
    payload = text.removeprefix("/risk_set").strip()
    parts = [x.strip() for x in payload.split("|")]
    if len(parts) != 3:
        return None
    try:
        values = tuple(int(x) for x in parts)
    except ValueError:
        return None
    if any(x < 0 or x > 100 for x in values):
        return None
    return values


def _downside(total_value: float) -> dict[str, float]:
    return {"-10%": round(total_value * 0.9, 2), "-25%": round(total_value * 0.75, 2), "-40%": round(total_value * 0.6, 2)}


def _sell_priority(action: str) -> int:
    priority = {"SELL_FAST": 0, "LIST_HIGHER": 1, "HOLD": 2, "BUY_ONLY_CHEAP": 3, "AVOID": 4}
    return priority.get(action, 9)


def _build_rebalance_hints(warnings: list[str]) -> list[str]:
    hints = []
    overloaded = [w for w in warnings if "портфеля" in w]
    if overloaded:
        hints.append("снизить концентрацию в перегруженных коллекциях")
    hints.append("искать альтернативы в universe")
    return hints


def _effective_universe(active_universe: list[str], watchlist: list[str]) -> list[str]:
    if active_universe:
        return active_universe
    return list(dict.fromkeys(watchlist))


async def _resolve_universe_collections(user_id: int) -> list[str]:
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        gift_repo = GiftRepository(session)
        universe = await user_repo.list_universe(user_id)
        active = [x.collection for x in universe if x.is_active]
        gifts = await gift_repo.list_by_user(user_id)
        watchlist = list(dict.fromkeys(g.collection for g in gifts))
        return _effective_universe(active, watchlist)


def _collection_reports_from_ranked(ranked: list[dict], portfolio_rows: list[dict]) -> list:
    by_collection: dict[str, list[dict]] = {}
    for row in ranked:
        by_collection.setdefault(row["listing"].collection, []).append(row)
    exp = calculate_collection_exposure(portfolio_rows)
    reports = []
    for collection, items in by_collection.items():
        reports.append(
            evaluate_collection_regime(
                collection=collection,
                opportunities=items,
                portfolio_exposure_percent=float(exp.get(collection, 0.0)),
            )
        )
    reports.sort(key=lambda x: x.relative_strength_score, reverse=True)
    return reports


@router.message(Command("bank_set"))
async def bank_set_handler(message: Message) -> None:
    amount = _parse_positive_amount(message.text or "", "/bank_set")
    if amount is None:
        await message.answer("Используйте: /bank_set <положительная сумма>")
        return
    async with SessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.get_or_create(message.from_user.id, message.from_user.username)
        await repo.set_bankroll(user.id, amount)
    await message.answer(f"✅ Банк сохранен: {amount:.2f} TON")


@router.message(Command("goal_set"))
async def goal_set_handler(message: Message) -> None:
    amount = _parse_positive_amount(message.text or "", "/goal_set")
    if amount is None:
        await message.answer("Используйте: /goal_set <положительная сумма>")
        return
    async with SessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.get_or_create(message.from_user.id, message.from_user.username)
        await repo.set_goal(user.id, amount)
    await message.answer(f"✅ Цель сохранена: {amount:.2f} TON")


@router.message(Command("risk_set"))
async def risk_set_handler(message: Message) -> None:
    parsed = _parse_risk(message.text or "")
    if parsed is None:
        await message.answer("Используйте: /risk_set 25 | 40 | 20 (0-100)")
        return
    max_deal, max_collection, reserve = parsed
    async with SessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.get_or_create(message.from_user.id, message.from_user.username)
        await repo.set_risk_limits(user.id, max_deal, max_collection, reserve)
        await log_audit(
            session,
            user_id=user.id,
            action="risk_settings_changed",
            entity_type="user",
            entity_id=str(user.id),
            metadata_json={"max_deal": max_deal, "max_collection": max_collection, "reserve": reserve},
        )
    await message.answer("✅ Риск-настройки обновлены.")


@router.message(Command("bank"))
async def bank_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
    if user.bankroll_ton is None:
        await message.answer("Банк не задан. Используйте /bank_set <amount>.")
        return
    reserve = user.bankroll_ton * float(user.reserve_percent or 20) / 100.0
    max_deal = user.bankroll_ton * float(user.max_deal_percent or 25) / 100.0
    max_collection = user.bankroll_ton * float(user.max_collection_percent or 40) / 100.0
    goal = user.goal_ton
    to_goal = (goal - user.bankroll_ton) if goal else None
    await message.answer(
        f"🏦 Bank settings\n\n"
        f"Банк: {user.bankroll_ton:.2f} TON\n"
        f"Цель: {(f'{goal:.2f} TON' if goal else 'не задана')}\n"
        f"До цели: {(f'{to_goal:.2f} TON' if to_goal is not None else 'н/д')}\n"
        f"Reserve: {reserve:.2f} TON ({user.reserve_percent}%)\n"
        f"Max per deal: {max_deal:.2f} TON ({user.max_deal_percent}%)\n"
        f"Max per collection: {max_collection:.2f} TON ({user.max_collection_percent}%)"
    )


@router.message(Command("universe"))
async def universe_handler(message: Message) -> None:
    async with SessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.get_or_create(message.from_user.id, message.from_user.username)
        rows = await repo.list_universe(user.id)
    if not rows:
        fallback = await _resolve_universe_collections(user.id)
        if fallback:
            await message.answer("Universe пуст. Использую watchlist: " + ", ".join(fallback))
            return
        await message.answer("Universe пуст. Добавьте коллекцию через /universe_add или /add.")
        return
    lines = [f"- {r.collection} ({'on' if r.is_active else 'off'})" for r in rows]
    await message.answer("🌍 Universe:\n" + "\n".join(lines))


@router.message(Command("universe_add"))
async def universe_add_handler(message: Message) -> None:
    collection = (message.text or "").removeprefix("/universe_add").strip()
    if not collection:
        await message.answer("Используйте: /universe_add <collection>")
        return
    async with SessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.get_or_create(message.from_user.id, message.from_user.username)
        universe_rows = await repo.list_universe(user.id)
        allowed, max_allowed = check_usage_limit(user, "max_universe_collections", len(universe_rows))
        if not allowed:
            await message.answer(
                f"🔒 Лимит плана: максимум {max_allowed} коллекций в universe.\n"
                f"Текущий план: {user.plan.capitalize()}."
            )
            return
        await repo.add_universe_collection(user.id, collection)
    await message.answer(f"✅ Добавлено в universe: {collection}")


@router.message(Command("universe_remove"))
async def universe_remove_handler(message: Message) -> None:
    collection = (message.text or "").removeprefix("/universe_remove").strip()
    if not collection:
        await message.answer("Используйте: /universe_remove <collection>")
        return
    async with SessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.get_or_create(message.from_user.id, message.from_user.username)
        await repo.remove_universe_collection(user.id, collection)
        await log_audit(
            session,
            user_id=user.id,
            action="universe_remove",
            entity_type="collection",
            entity_id=collection,
        )
    await message.answer(f"🗑 Удалено из universe: {collection}")


@router.message(Command("universe_on"))
async def universe_on_handler(message: Message) -> None:
    collection = (message.text or "").removeprefix("/universe_on").strip()
    if not collection:
        await message.answer("Используйте: /universe_on <collection>")
        return
    async with SessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.get_or_create(message.from_user.id, message.from_user.username)
        ok = await repo.set_universe_collection_state(user.id, collection, True)
    await message.answer("✅ Коллекция включена." if ok else "Коллекция не найдена в universe.")


@router.message(Command("universe_off"))
async def universe_off_handler(message: Message) -> None:
    collection = (message.text or "").removeprefix("/universe_off").strip()
    if not collection:
        await message.answer("Используйте: /universe_off <collection>")
        return
    async with SessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.get_or_create(message.from_user.id, message.from_user.username)
        ok = await repo.set_universe_collection_state(user.id, collection, False)
    await message.answer("⏸ Коллекция выключена." if ok else "Коллекция не найдена в universe.")


@router.message(Command("portfolio"))
async def portfolio_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        gifts = await GiftRepository(session).list_by_user(user.id)

    analyzer = AnalyzerService(create_market_source(get_settings(), user_id=user.id))
    estimates = []
    purchase_prices = []
    for gift in gifts:
        estimate = await analyzer.analyze_gift(
            GiftCard(collection=gift.collection, number=gift.number),
            risk_mode=user.risk_mode,
            buy_price_ton=gift.purchase_price_ton,
            owns_asset=True,
        )
        estimates.append(estimate)
        purchase_prices.append(gift.purchase_price_ton)
    totals = aggregate_portfolio(estimates, purchase_prices)
    goal_text = "н/д"
    progress_text = "н/д"
    if user.goal_ton:
        goal_text = f"{user.goal_ton:.2f} TON"
        progress = (totals["estimated_net_total"] / user.goal_ton * 100.0) if user.goal_ton > 0 else 0.0
        progress_text = f"{progress:.1f}%"
    await message.answer(
        f"Портфель:\n"
        f"Кол-во: {totals['count']}\n"
        f"Quick sell total: {totals['quick_sell_total']} TON\n"
        f"Fair total: {totals['fair_price_total']} TON\n"
        f"List total: {totals['list_total']} TON\n"
        f"Net after fees: {totals['estimated_net_total']} TON\n"
        f"Оценочный PnL: {totals['pnl'] if totals['pnl'] is not None else 'н/д'}\n"
        f"Средний risk: {totals['avg_risk_score']}/100\n"
        f"Средний confidence: {totals['avg_confidence_score']}/100\n"
        f"Банк: {(f'{user.bankroll_ton:.2f} TON' if user.bankroll_ton else 'не задан')}\n"
        f"Цель: {goal_text}\n"
        f"Progress to goal: {progress_text}\n"
        f"Risk summary: deal {user.max_deal_percent}% / collection {user.max_collection_percent}% / reserve {user.reserve_percent}%\n\n"
        f"Команды:\n/portfolio_rank\n/capital_plan\n/sell_plan"
    )


@router.message(Command("portfolio_rank"))
async def portfolio_rank_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        gifts = await GiftRepository(session).list_by_user(user.id)
    analyzer = AnalyzerService(create_market_source(get_settings(), user_id=user.id))
    if not gifts:
        await message.answer("Портфель пуст.")
        return
    rows = []
    estimates = []
    purchase_prices = []
    by_collection: dict[str, float] = {}
    for gift in gifts:
        estimate = await analyzer.analyze_gift(
            GiftCard(collection=gift.collection, number=gift.number),
            risk_mode=user.risk_mode,
            buy_price_ton=gift.purchase_price_ton,
            owns_asset=True,
        )
        estimates.append(estimate)
        purchase_prices.append(gift.purchase_price_ton)
        rows.append((gift, estimate))
        by_collection[gift.collection] = by_collection.get(gift.collection, 0.0) + estimate.fair_price_ton
    totals = aggregate_portfolio(estimates, purchase_prices)
    portfolio_rows = [
        {"collection": g.collection, "value_ton": e.fair_price_ton, "traits": []}
        for g, e in rows
    ]
    diversification_score = calculate_diversification_score(portfolio_rows)
    collection_exp = calculate_collection_exposure(portfolio_rows)
    trait_exp = calculate_trait_exposure(portfolio_rows)
    concentration_warnings = get_concentration_warnings(portfolio_rows, user)
    downside = _downside(totals["fair_price_total"])
    action_chunks: list[str] = []
    for idx, (gift, est) in enumerate(
        sorted(rows, key=lambda x: x[1].confidence_score - x[1].risk_score, reverse=True), start=1
    ):
        sp, pw, eff = metrics_for_owned_gift(est, gift.purchase_price_ton)
        action_chunks.append(
            f"#{idx} {gift.collection} #{gift.number} — {getattr(est, 'decision_type', None) or est.recommendation}\n"
            f"Bought: {gift.purchase_price_ton or 'n/a'} TON · Safe value ~{getattr(est, 'safe_buy_price_ton', None) or est.buy_zone_max_ton}\n"
            f"List normal/high: {getattr(est, 'normal_list_price_ton', None) or est.list_price_ton} / "
            f"{getattr(est, 'high_list_price_ton', None) or est.optimistic_price_ton} TON\n"
            f"Quick sell: {getattr(est, 'quick_sell_price_ton', est.quick_sell_price_ton)} TON\n"
            f"Est. PnL (сценарий): {est.expected_profit_ton:+.2f} TON · Risk: {est.risk_score}/100\n"
            f"p(sale)~{sp:.0f}% · pw-profit~{pw:+.1f} TON · cap.eff~{eff:.0f}/100"
        )
    actions = "\n\n".join(action_chunks)
    collection_total = sum(by_collection.values()) or 1.0
    concentration = sorted(((k, v / collection_total * 100.0) for k, v in by_collection.items()), key=lambda x: x[1], reverse=True)
    risk_lines = [f"- {pct:.0f}% портфеля в {name}" for name, pct in concentration if pct >= 40]
    if any("старше 7 дней" in reason for est in estimates for reason in est.reasons):
        risk_lines.append("- мало recent sales")
    if any("manual" in reason.lower() or "устар" in reason.lower() for est in estimates for reason in est.reasons):
        risk_lines.append("- часть данных manual/stale")
    risk_lines.extend(f"- {w}" for w in concentration_warnings)
    risk_text = "\n".join(risk_lines) if risk_lines else "- выраженной концентрации риска нет"
    collection_exp_text = ", ".join(f"{k}: {v:.1f}%" for k, v in sorted(collection_exp.items(), key=lambda x: x[1], reverse=True)) or "н/д"
    trait_exp_text = ", ".join(f"{k}: {v:.1f}%" for k, v in sorted(trait_exp.items(), key=lambda x: x[1], reverse=True)[:5]) or "н/д"
    await message.answer(
        f"📊 Portfolio Ranking\n\n"
        f"Всего подарков: {totals['count']}\n"
        f"Quick sell total: {totals['quick_sell_total']} TON\n"
        f"Fair total: {totals['fair_price_total']} TON\n"
        f"List total: {totals['list_total']} TON\n"
        f"Net after fees: {totals['estimated_net_total']} TON\n\n"
        f"Top actions:\n{actions}\n\n"
        f"Diversification score: {diversification_score}/100\n"
        f"Collection exposure: {collection_exp_text}\n"
        f"Trait exposure: {trait_exp_text}\n"
        f"Rebalance hints: {'; '.join(concentration_warnings) if concentration_warnings else 'перекосов нет'}\n\n"
        f"Риск:\n{risk_text}\n\n"
        f"📉 Downside:\n"
        f"-10% market: ~{downside['-10%']} TON\n"
        f"-25% market: ~{downside['-25%']} TON\n"
        f"-40% market: ~{downside['-40%']} TON"
    )


@router.message(Command("capital_plan"))
async def capital_plan_handler(message: Message) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        gifts = await GiftRepository(session).list_by_user(user.id)
    try:
        assert_feature_allowed(user, "capital_plan")
    except PermissionError as exc:
        await message.answer(str(exc))
        return
    if user.bankroll_ton is None:
        await message.answer("Сначала задайте банк: /bank_set <amount>")
        return
    source = create_market_source(settings, user_id=user.id)
    listings = await source.search_underpriced("Ice Cream", filters={})
    listings = filter_mock_listings_for_production(settings, listings)
    analyzer = AnalyzerService(source)
    opportunities: list[dict] = []
    for listing in listings:
        estimate = await analyzer.analyze_gift(
            GiftCard(collection=listing.collection, number=listing.number),
            risk_mode=user.risk_mode,
            buy_price_ton=listing.price_ton,
        )
        quality = analyzer.last_data_quality
        stats = analyzer.last_market_stats
        freshness_label = "old" if "old" in [stats.get("floor_freshness"), stats.get("sales_freshness")] else (
            "stale" if "stale" in [stats.get("floor_freshness"), stats.get("sales_freshness"), stats.get("listings_freshness")] else "fresh"
        )
        score = calculate_opportunity_score(
            estimate,
            quality,
            {
                "label": freshness_label,
                "has_recent_sales": bool(stats.get("sales_age_minutes") is not None and stats.get("sales_age_minutes") <= 7 * 24 * 60),
                "listing_price_ton": float(listing.price_ton),
                "real_sales_count": int(stats.get("real_sales_count") or 0),
                "spread_percent": float(stats.get("spread_percent") or 0),
            },
        )
        opportunities.append(
            {
                "listing": listing,
                "estimate": estimate,
                "score": score,
                "freshness_label": freshness_label,
                "real_sales_count": int(stats.get("real_sales_count") or 0),
                "stats": stats,
                "quality": quality,
            }
        )
    portfolio_rows = [{"collection": g.collection, "value_ton": g.purchase_price_ton or 0.0} for g in gifts]
    plan = allocate_capital(opportunities, user, portfolio_rows)
    extra34 = ""
    for row in opportunities[:5]:
        fc = flip_candidate_from_opportunity_row(row, market_regime=None, settings=settings)
        pw = fc.probability_weighted_profit_ton or 0
        extra34 += (
            f"\n- {fc.collection} #{fc.number}: p(sale)~{fc.sale_probability_percent:.0f}%, "
            f"pw~{pw:+.1f} TON, eff {fc.capital_efficiency_score:.0f}/100"
        )
    cap_text = format_capital_plan(plan)
    if extra34:
        cap_text += "\n\n📎 Оценки Stage34 (сценарий):" + extra34
    await message.answer(cap_text)


@router.message(Command("scan_universe"))
async def scan_universe_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        gifts = await GiftRepository(session).list_by_user(user.id)
    try:
        assert_feature_allowed(user, "scan_universe")
    except PermissionError as exc:
        await message.answer(str(exc))
        return
    collections = await _resolve_universe_collections(user.id)
    if not collections:
        await message.answer("Universe и watchlist пусты. Добавьте через /universe_add или /add.")
        return
    ranked = await gather_ranked_universe_opportunities(user, collections, get_settings())
    portfolio_rows = [{"collection": g.collection, "value_ton": g.purchase_price_ton or 0.0} for g in gifts]
    reports = _collection_reports_from_ranked(ranked, portfolio_rows)
    regime = evaluate_universe_regime(reports)
    ranked = await gather_ranked_universe_opportunities(
        user, collections, get_settings(), market_regime=regime.regime
    )
    reports = _collection_reports_from_ranked(ranked, portfolio_rows)
    regime = evaluate_universe_regime(reports)
    good = [
        row
        for row in ranked
        if row["estimate"].expected_profit_ton >= get_settings().min_profit_ton
        and row["estimate"].confidence_score >= 45
        and row["estimate"].risk_score <= 80
        and row["freshness_label"] != "old"
        and getattr(row["estimate"], "decision_type", None) not in {"AVOID", "NEED_MORE_DATA"}
        and not (
            getattr(row["estimate"], "decision_type", None) == "STRONG_BUY"
            and int(row.get("real_sales_count") or 0) < 3
        )
        and (
            float(getattr(row["estimate"], "buy_zone_max_ton", 0) or 0) <= 0
            or float(row["listing"].price_ton) <= float(row["estimate"].buy_zone_max_ton) * 1.02
        )
    ]
    if regime.regime == "data_poor":
        good = [row for row in good if row["estimate"].recommendation != "BUY_FOR_FLIP"]
    if not good:
        await message.answer("Сейчас нет сделок, которые проходят фильтр profit/ROI/risk/freshness.")
        return
    best_collection = reports[0].collection if reports else "n/a"
    worst_collection = reports[-1].collection if reports else "n/a"
    lines = [
        f"🌍 Universe Scan\n\nКоллекции: {', '.join(collections)}\n"
        f"Market regime: {regime.regime} ({regime.score}/100)\n"
        f"Best collection: {best_collection}\n"
        f"Worst collection: {worst_collection}\n"
        f"{('⚠️ Нужны реальные/ручные данные для надежного анализа' if regime.regime == 'data_poor' else '')}\n"
    ]
    for idx, row in enumerate(good[:10], start=1):
        l = row["listing"]
        e = row["estimate"]
        s = row["score"]
        lines.append(
            f"#{idx} {l.collection} #{l.number}\n"
            f"Tier: {s.final_rank_label}\n"
            f"Score: {s.total_score}/100\n"
            f"Buy: {l.price_ton:.2f} TON\n"
            f"List: {e.list_price_ton} TON\n"
            f"Profit: {e.expected_profit_ton:+.2f} TON\n"
            f"ROI: {e.expected_roi_percent:+.2f}%\n"
            f"Risk: {e.risk_score}/100\n"
            f"Freshness: {row['freshness_label']}\n"
            f"Signal: {row['signal_label']}"
        )
    await message.answer("\n\n".join(lines))


@router.message(Command("capital_plan_universe"))
async def capital_plan_universe_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        gifts = await GiftRepository(session).list_by_user(user.id)
    try:
        assert_feature_allowed(user, "capital_plan")
    except PermissionError as exc:
        await message.answer(str(exc))
        return
    if user.bankroll_ton is None:
        await message.answer("Сначала задайте банк: /bank_set <amount>")
        return
    collections = await _resolve_universe_collections(user.id)
    ranked = await gather_ranked_universe_opportunities(user, collections, get_settings())
    portfolio_rows = [{"collection": g.collection, "value_ton": g.purchase_price_ton or 0.0} for g in gifts]
    reports = _collection_reports_from_ranked(ranked, portfolio_rows)
    regime = evaluate_universe_regime(reports)
    ranked = await gather_ranked_universe_opportunities(
        user, collections, get_settings(), market_regime=regime.regime
    )
    reports = _collection_reports_from_ranked(ranked, portfolio_rows)
    regime = evaluate_universe_regime(reports)
    plan = allocate_capital_dynamic(ranked, user, portfolio_rows, regime=regime.regime)
    extra34 = ""
    for row in ranked[:5]:
        fc = flip_candidate_from_opportunity_row(row, market_regime=regime.regime, settings=get_settings())
        pw = fc.probability_weighted_profit_ton or 0
        extra34 += (
            f"\n- {fc.collection} #{fc.number}: p(sale)~{fc.sale_probability_percent:.0f}%, "
            f"pw~{pw:+.1f} TON, eff {fc.capital_efficiency_score:.0f}/100"
        )
    uni = (
        "💼 Universe Capital Plan\n\n"
        f"🌡 Market regime: {regime.regime}\n"
        f"Allocation multiplier: {int(get_regime_allocation_multiplier(regime.regime) * 100)}%\n"
        f"Причина: {', '.join(regime.reasons) if regime.reasons else 'n/a'}\n\n"
        + format_capital_plan(plan)
    )
    if extra34:
        uni += "\n\n📎 Оценки Stage34 (сценарий):" + extra34
    await message.answer(uni)


@router.message(Command("rebalance"))
async def rebalance_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        gifts = await GiftRepository(session).list_by_user(user.id)
    if not gifts:
        await message.answer("Портфель пуст.")
        return
    analyzer = AnalyzerService(create_market_source(get_settings(), user_id=user.id))
    rows = []
    ranked = await gather_ranked_universe_opportunities(
        user, await _resolve_universe_collections(user.id), get_settings()
    )
    reports = _collection_reports_from_ranked(
        ranked, [{"collection": g.collection, "value_ton": g.purchase_price_ton or 0.0} for g in gifts]
    )
    report_by_collection = {r.collection: r for r in reports}
    for gift in gifts:
        est = await analyzer.analyze_gift(
            GiftCard(collection=gift.collection, number=gift.number),
            risk_mode=user.risk_mode,
            buy_price_ton=gift.purchase_price_ton,
            owns_asset=True,
        )
        rows.append({"collection": gift.collection, "value_ton": est.fair_price_ton, "recommendation": est.recommendation, "stop": est.stop_price_ton})
    warnings = get_concentration_warnings(rows, user)
    for row in rows:
        rep = report_by_collection.get(row["collection"])
        if rep and rep.regime in {"risk_off", "illiquid"}:
            warnings.append(f"{row['collection']} в режиме {rep.regime}: reduce exposure, не докупать выше buy_zone_max")
    hints = _build_rebalance_hints(warnings)
    await message.answer(
        "⚖️ Rebalance\n\n"
        f"Проблемы:\n{chr(10).join('- ' + w for w in warnings) if warnings else '- критичных перекосов нет'}\n\n"
        f"Рекомендация:\n- {'; '.join(hints)}"
    )


@router.message(Command("market_regime"))
async def market_regime_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        gifts = await GiftRepository(session).list_by_user(user.id)
    try:
        assert_feature_allowed(user, "scan_universe")
    except PermissionError as exc:
        await message.answer(str(exc))
        return
    collections = await _resolve_universe_collections(user.id)
    ranked = await gather_ranked_universe_opportunities(user, collections, get_settings())
    reports = _collection_reports_from_ranked(
        ranked, [{"collection": g.collection, "value_ton": g.purchase_price_ton or 0.0} for g in gifts]
    )
    regime = evaluate_universe_regime(reports)
    await message.answer(format_market_regime_report(regime))


@router.message(Command("collection_strength"))
async def collection_strength_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        gifts = await GiftRepository(session).list_by_user(user.id)
    try:
        assert_feature_allowed(user, "scan_universe")
    except PermissionError as exc:
        await message.answer(str(exc))
        return
    collections = await _resolve_universe_collections(user.id)
    ranked = await gather_ranked_universe_opportunities(user, collections, get_settings())
    reports = _collection_reports_from_ranked(
        ranked, [{"collection": g.collection, "value_ton": g.purchase_price_ton or 0.0} for g in gifts]
    )
    if not reports:
        await message.answer("Нет данных для collection strength.")
        return
    lines = ["💪 Collection Strength\n"]
    for idx, rep in enumerate(reports, start=1):
        best_tier = "n/a"
        same = [x for x in ranked if x["listing"].collection == rep.collection]
        if same:
            best_tier = same[0]["score"].final_rank_label
        lines.append(
            f"#{idx} {rep.collection}\n"
            f"Strength: {rep.relative_strength_score}/100\n"
            f"Regime: {rep.regime}\n"
            f"Best opportunity: {best_tier}\n"
            f"Recommendation: {rep.recommendation}"
        )
    await message.answer("\n\n".join(lines))


@router.message(Command("universe_report"))
async def universe_report_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        gifts = await GiftRepository(session).list_by_user(user.id)
    try:
        assert_feature_allowed(user, "scan_universe")
    except PermissionError as exc:
        await message.answer(str(exc))
        return
    collections = await _resolve_universe_collections(user.id)
    ranked = await gather_ranked_universe_opportunities(user, collections, get_settings())
    portfolio_rows = [{"collection": g.collection, "value_ton": g.purchase_price_ton or 0.0} for g in gifts]
    reports = _collection_reports_from_ranked(ranked, portfolio_rows)
    regime = evaluate_universe_regime(reports)
    best = reports[0].collection if reports else "n/a"
    weak = ", ".join(r.collection for r in reports[-2:]) if len(reports) >= 2 else "n/a"
    top = "\n".join(
        f"- {x['listing'].collection} #{x['listing'].number} ({x['score'].final_rank_label}, {x['score'].total_score}/100)"
        for x in ranked[:5]
    ) or "- нет"
    conc = get_concentration_warnings(portfolio_rows, user)
    report_text = (
        f"🧾 Universe Report\n\n"
        f"Market regime: {regime.regime} ({regime.score}/100)\n"
        f"Best collection: {best}\n"
        f"Weak collections: {weak}\n\n"
        f"Top opportunities:\n{top}\n\n"
        f"Concentration risk:\n{chr(10).join('- ' + x for x in conc) if conc else '- нет'}\n\n"
        f"Data quality issues:\n{chr(10).join('- ' + x for x in regime.warnings) if regime.warnings else '- нет'}\n\n"
        f"Suggested next actions:\n"
        f"- использовать multiplier {int(get_regime_allocation_multiplier(regime.regime)*100)}% в плане\n"
        f"- {'держать больше кэша' if regime.regime in {'risk_off','illiquid','data_poor'} else 'можно работать по топ-кандидатам'}"
    )
    await message.answer(report_text)


@router.message(Command("sell_plan"))
async def sell_plan_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        gifts = await GiftRepository(session).list_by_user(user.id)
    analyzer = AnalyzerService(create_market_source(get_settings(), user_id=user.id))
    if not gifts:
        await message.answer("Портфель пуст.")
        return
    lines = []
    rows = []
    for gift in gifts:
        est = await analyzer.analyze_gift(
            GiftCard(collection=gift.collection, number=gift.number),
            risk_mode=user.risk_mode,
            buy_price_ton=gift.purchase_price_ton,
            owns_asset=True,
        )
        rows.append((gift, est))
    rows.sort(key=lambda x: (_sell_priority(x[1].recommendation), -(x[1].risk_score or 0)))
    for idx, (gift, est) in enumerate(rows, start=1):
        dec = getattr(est, "decision_type", None) or est.recommendation
        sp, pw, eff = metrics_for_owned_gift(est, gift.purchase_price_ton)
        lines.append(
            f"#{idx} {gift.collection} #{gift.number}\n"
            f"Bought at: {gift.purchase_price_ton or 'n/a'} TON · Suggested: {dec}\n"
            f"Safe value ~{getattr(est, 'safe_buy_price_ton', None) or est.buy_zone_max_ton} TON\n"
            f"List normal/high: {getattr(est, 'normal_list_price_ton', None) or est.list_price_ton} / "
            f"{getattr(est, 'high_list_price_ton', None) or est.optimistic_price_ton} TON\n"
            f"Quick sell: {est.quick_sell_price_ton} TON · Stop: {est.stop_price_ton} TON\n"
            f"Expected PnL (сценарий): {est.expected_profit_ton:+.2f} TON\n"
            f"p(sale)~{sp:.0f}% · pw~{pw:+.1f} TON · cap.eff~{eff:.0f}/100"
        )
    await message.answer("📤 Sell Plan\n\n" + "\n\n".join(lines))
