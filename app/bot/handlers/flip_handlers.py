"""Stage 34–35: budget flip plan, compound ladder, sell-to-buy, lite plan (analytics only)."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.handlers.portfolio import _resolve_universe_collections
from app.bot.messages import FREE_BUDGET_DEALS_TEASER, FREE_FLIP_PLAN_TEASER, LITE_PLAN_TEASER_FOOTER
from app.config import get_settings
from app.db.repositories.gifts import GiftRepository
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.schemas.gift import GiftCard
from app.services.capital_multiplier import (
    CapitalMultiplierPlan,
    build_capital_multiplier_plan,
    format_capital_multiplier_plan,
)
from app.services.feature_limits import assert_feature_allowed, can_use_feature
from app.services.flip_ladder import build_flip_ladder, format_flip_ladder
from app.services.signal_snapshots import build_snapshot_seed_from_flip_analysis, create_signal_snapshot_from_analysis
from app.services.sell_to_buy_planner import build_sell_to_buy_plan, format_sell_to_buy_plan

router = Router()


def _parse_budget(text: str, cmd: str) -> float | None:
    payload = (text or "").removeprefix(cmd).strip().replace(",", ".")
    parts = payload.split()
    if not parts:
        return None
    try:
        v = float(parts[0])
        return v if v > 0 else None
    except ValueError:
        return None


def _parse_compound(text: str) -> tuple[float | None, float | None]:
    raw = (text or "").removeprefix("/compound_plan").strip()
    if "|" in raw:
        a, b = [x.strip().replace(",", ".") for x in raw.split("|", 1)]
        try:
            return float(a), float(b)
        except ValueError:
            return None, None
    try:
        v = float(raw.replace(",", "."))
        return v, None
    except ValueError:
        return None, None


def _parse_sell_to_buy_budget(text: str) -> float | None:
    raw = (text or "").removeprefix("/sell_to_buy").strip()
    if not raw:
        return None
    try:
        v = float(raw.replace(",", "."))
        return v if v > 0 else None
    except ValueError:
        return None


def _stage34_verdict(plan: CapitalMultiplierPlan) -> str:
    n = len(plan.selected_candidates)
    spec_any = any(c.is_speculative for c in plan.selected_candidates)
    if n == 0:
        if plan.market_regime in {"data_poor", "illiquid"}:
            return "📌 Вердикт: данные слабые — план осторожный; кэш допустим (сценарий)."
        return "📌 Вердикт: сейчас лучше держать кэш или ужать входы (оценка)."
    if spec_any:
        return f"📌 Вердикт: есть {n} кандидат(а), в т.ч. спекулятивный вариант — не всем бюджетом."
    return f"📌 Вердикт: есть {n} рабочих кандидат(а) (оценка, не обещание сделки)."


def _stage34_signal_footer() -> str:
    return (
        "\n\n---\nОцени сигнал: /signal_good <id> или /signal_bad <id>\n"
        "Если купил: /trade_add <signal_id> | цена"
    )


async def _snapshots_for_flip_rows(
    session,
    user_id: int,
    rows: list[dict],
    *,
    source_command: str,
    top_n: int,
) -> list[str]:
    lines: list[str] = []
    for row in rows[:top_n]:
        listing = row["listing"]
        est = row["estimate"]
        stats = row.get("stats") or {}
        quality = row.get("quality")
        score = row.get("score")
        gift = GiftCard(collection=listing.collection, number=listing.number)
        seed = build_snapshot_seed_from_flip_analysis(
            source_command=source_command,
            gift=gift,
            estimate=est,
            stats=stats,
            quality=quality,
            score=score,
            input_text=f"{listing.collection} #{listing.number}",
            source_url=getattr(listing, "url", None),
        )
        snap = await create_signal_snapshot_from_analysis(session, user_id=user_id, seed=seed)
        lines.append(f"#{snap.id} · {snap.collection} #{snap.number} — /signal_good {snap.id} или /signal_bad {snap.id}")
    return lines


@router.message(Command("lite_plan"))
async def lite_plan_handler(message: Message) -> None:
    settings = get_settings()
    amt = _parse_budget(message.text or "", "/lite_plan")
    if amt is None:
        await message.answer("Используйте: /lite_plan <budget_ton>\nПример: /lite_plan 300")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        gifts = await GiftRepository(session).list_by_user(user.id)
    cols = list(dict.fromkeys(g.collection for g in gifts))[:2]
    if not cols:
        await message.answer(
            "Lite-план строится по коллекциям из watchlist.\n"
            "Добавь подарок: /add <ссылка> или /add Ice Cream 217467 — затем /lite_plan 300"
        )
        return
    plan, selected_rows = await build_capital_multiplier_plan(
        user,
        amt,
        settings,
        universe_collections=cols,
        gifts_for_regime=gifts,
        lite_mode=True,
        max_selected_override=3,
        ranked_row_limit=22,
    )
    signal_lines: list[str] = []
    top_sn = min(2, int(settings.capital_multiplier_signal_snapshots_top_n))
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        if selected_rows:
            signal_lines = await _snapshots_for_flip_rows(
                session,
                user.id,
                selected_rows,
                source_command="lite_plan",
                top_n=top_sn,
            )
    body = format_capital_multiplier_plan(plan, signal_hint_lines=signal_lines or None)
    text = _stage34_verdict(plan) + "\n\n" + body + LITE_PLAN_TEASER_FOOTER + _stage34_signal_footer()
    await message.answer(text[:4090])


@router.message(Command("flip_plan"))
async def flip_plan_handler(message: Message) -> None:
    settings = get_settings()
    amt = _parse_budget(message.text or "", "/flip_plan")
    if amt is None:
        await message.answer("Используйте: /flip_plan <budget_ton>\nПример: /flip_plan 300")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        gifts = await GiftRepository(session).list_by_user(user.id)
    if not can_use_feature(user, "capital_plan"):
        await message.answer(FREE_FLIP_PLAN_TEASER)
        return
    cols = await _resolve_universe_collections(user.id)
    if not cols:
        await message.answer("Добавьте коллекции в universe или подарки в watchlist.")
        return
    plan, selected_rows = await build_capital_multiplier_plan(
        user,
        amt,
        settings,
        universe_collections=cols,
        gifts_for_regime=gifts,
    )
    signal_lines: list[str] = []
    top_sn = int(settings.capital_multiplier_signal_snapshots_top_n)
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        signal_lines = await _snapshots_for_flip_rows(
            session,
            user.id,
            selected_rows,
            source_command="flip_plan",
            top_n=top_sn,
        )
    body = format_capital_multiplier_plan(plan, signal_hint_lines=signal_lines or None)
    text = _stage34_verdict(plan) + "\n\n" + body + _stage34_signal_footer()
    await message.answer(text[:4090])


@router.message(Command("budget_deals"))
async def budget_deals_handler(message: Message) -> None:
    settings = get_settings()
    amt = _parse_budget(message.text or "", "/budget_deals")
    if amt is None:
        await message.answer("Используйте: /budget_deals <budget_ton>")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        gifts = await GiftRepository(session).list_by_user(user.id)
    if not can_use_feature(user, "capital_plan"):
        await message.answer(FREE_BUDGET_DEALS_TEASER)
        return
    cols = await _resolve_universe_collections(user.id)
    if not cols:
        await message.answer("Добавьте коллекции в universe или подарки в watchlist.")
        return
    plan, selected_rows = await build_capital_multiplier_plan(
        user,
        amt,
        settings,
        universe_collections=cols,
        gifts_for_regime=gifts,
    )
    signal_lines: list[str] = []
    top_sn = int(settings.capital_multiplier_signal_snapshots_top_n)
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        signal_lines = await _snapshots_for_flip_rows(
            session,
            user.id,
            selected_rows,
            source_command="budget_deals",
            top_n=top_sn,
        )
    body = format_capital_multiplier_plan(plan, compact=True, signal_hint_lines=signal_lines or None)
    text = _stage34_verdict(plan) + "\n\n" + body + _stage34_signal_footer()
    await message.answer(text[:4090])


@router.message(Command("compound_plan"))
async def compound_plan_handler(message: Message) -> None:
    start, goal = _parse_compound(message.text or "")
    if start is None or goal is None:
        await message.answer("Используйте: /compound_plan <budget_ton> | <goal_ton>\nПример: /compound_plan 300 | 1000")
        return
    if goal <= start:
        await message.answer("Цель должна быть больше стартового бюджета.")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
    try:
        assert_feature_allowed(user, "capital_plan")
    except PermissionError as exc:
        await message.answer(str(exc))
        return
    ladder = build_flip_ladder(start, goal, risk_mode=user.risk_mode or "normal", settings=get_settings())
    text = (
        "📌 Вердикт: сценарий сложения капитала (сроки и факт могут отличаться).\n\n"
        + format_flip_ladder(ladder)
        + _stage34_signal_footer()
    )
    await message.answer(text[:4090])


@router.message(Command("sell_to_buy"))
async def sell_to_buy_handler(message: Message) -> None:
    settings = get_settings()
    extra = _parse_sell_to_buy_budget(message.text or "")
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        gifts = await GiftRepository(session).list_by_user(user.id)
    if not gifts:
        await message.answer("Портфель пуст.")
        return
    try:
        assert_feature_allowed(user, "capital_plan")
    except PermissionError as exc:
        await message.answer(str(exc))
        return
    cols = await _resolve_universe_collections(user.id)
    if not cols:
        await message.answer("Нужен universe или watchlist с коллекциями.")
        return
    plan = await build_sell_to_buy_plan(
        user,
        settings,
        gifts=gifts,
        universe_collections=cols,
        target_budget_ton=extra,
    )
    verdict = (
        "📌 Вердикт: сравнение hold vs замена по модели (решения только вручную).\n\n"
        if plan.replacement_buys
        else "📌 Вердикт: явных замен с лучшей моделью не видно — hold/кэш нормальны.\n\n"
    )
    text = verdict + format_sell_to_buy_plan(plan) + _stage34_signal_footer()
    await message.answer(text[:4090])


@router.message(Command("m4_plan"))
async def m4_plan_handler(message: Message) -> None:
    settings = get_settings()
    amt = _parse_budget(message.text or "", "/m4_plan")
    if amt is None:
        await message.answer("Используйте: /m4_plan <budget_ton>")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        gifts = await GiftRepository(session).list_by_user(user.id)
    if not can_use_feature(user, "capital_plan"):
        await message.answer(FREE_FLIP_PLAN_TEASER)
        return
    goal = user.goal_ton
    if goal is None or goal <= amt:
        await message.answer(
            "Задайте цель выше текущего бюджета: /goal_set <goal_ton> — затем повторите /m4_plan.\n"
            "Это сценарий пути к цели, без гарантий результата."
        )
        return
    cols = await _resolve_universe_collections(user.id)
    if not cols:
        await message.answer("Добавьте коллекции в universe или watchlist.")
        return
    plan, selected_rows = await build_capital_multiplier_plan(
        user,
        amt,
        settings,
        universe_collections=cols,
        gifts_for_regime=gifts,
    )
    risk = user.risk_mode or "normal"
    ladder = build_flip_ladder(amt, float(goal), risk_mode=risk, settings=settings)
    signal_lines: list[str] = []
    top_sn = int(settings.capital_multiplier_signal_snapshots_top_n)
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        signal_lines = await _snapshots_for_flip_rows(
            session,
            user.id,
            selected_rows,
            source_command="m4_plan",
            top_n=top_sn,
        )
    flip_body = format_capital_multiplier_plan(plan, signal_hint_lines=signal_lines or None)
    body = (
        _stage34_verdict(plan)
        + "\n\n"
        + f"🎯 Путь к цели ~{goal:.0f} TON (сценарий, не обещание)\n\n"
        + format_flip_ladder(ladder)
        + "\n\n---\nТекущий flip-plan на бюджет:\n"
        + flip_body
        + _stage34_signal_footer()
    )
    await message.answer(body[:4090])
