"""Trade journal & accuracy (Stage 31–32)."""

from __future__ import annotations

import json

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import get_settings
from app.db.repositories.signal_snapshots import SignalSnapshotRepository
from app.db.repositories.trade_journal import TradeJournalRepository
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.schemas.gift import GiftAttributeSchema, GiftCard
from app.schemas.market_brain import PrecisionPricePlan
from app.services.accuracy_report import (
    build_admin_accuracy_report,
    build_trade_stats_extended,
    build_user_accuracy_report,
)
from app.services.analyzer import AnalyzerService
from app.services.backtesting import format_backtest_report, journal_rows_to_backtest_pairs, run_backtest
from app.services.gift_analysis_flow import gift_attrs_for_demo
from app.services.gift_cards import format_unknown_gift_input_help
from app.services.gift_intake import GiftInputType
from app.services.gift_resolver import resolve_gift_identity
from app.services.price_explain import compare_price_plans, format_price_change_explanation
from app.services.pricing_tuner import analyze_pricing_accuracy, format_pricing_tuning_report
from app.services.signal_snapshots import prediction_dict_from_signal_snapshot
from app.services.trade_import import (
    format_trade_export_csv,
    format_trade_import_preview,
    format_trade_import_result,
    import_trades_for_user,
    parse_trade_csv,
    validate_trade_row,
)
from app.sources.factory import create_market_source
from app.bot.handlers.market import _parts_pipe, _to_price

router = Router()

_CHUNK = 3800


def _csv_lines_after_command(text: str, command_line_prefix: str) -> str:
    raw = (text or "").strip()
    lines = raw.splitlines()
    if not lines or not lines[0].strip().lower().startswith(command_line_prefix.lower()):
        return ""
    return "\n".join(lines[1:]).strip()


async def _send_long(message: Message, text: str) -> None:
    if len(text) <= _CHUNK:
        await message.answer(text)
        return
    for i in range(0, len(text), _CHUNK):
        await message.answer(text[i : i + _CHUNK])


def _is_env_admin(telegram_id: int) -> bool:
    s = get_settings()
    return str(telegram_id) in {x.strip() for x in s.admin_telegram_ids.split(",") if x.strip()}


def _parse_trade_add(text: str) -> tuple[str, float | None, str | None]:
    parts = _parts_pipe(text, "/trade_add")
    if len(parts) < 2:
        return "", None, None
    subj = parts[0]
    price = _to_price(parts[1])
    note = parts[2] if len(parts) > 2 else None
    return subj, price, note


@router.message(Command("trade_add"))
async def trade_add_handler(message: Message) -> None:
    subj, price, note = _parse_trade_add(message.text or "")
    if not subj or price is None:
        await message.answer(
            "Используйте: /trade_add Ice Cream #1 | 150 | заметка опционально\n"
            "Или после Signal ID: /trade_add 123 | 150 | заметка"
        )
        return
    settings = get_settings()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        if subj.isdigit():
            snap = await SignalSnapshotRepository(session).get_for_user(int(subj), user.id)
            if snap is not None:
                gift = gift_attrs_for_demo(GiftCard(collection=snap.collection, number=snap.number or 0))
                pred_snap = prediction_dict_from_signal_snapshot(snap)
                row = await TradeJournalRepository(session).create(
                    user_id=user.id,
                    collection=gift.collection,
                    number=gift.number,
                    nft_address=snap.nft_address,
                    attributes_json=[],
                    buy_price_ton=price,
                    notes=note,
                    source_url=snap.source_url,
                    prediction_snapshot=pred_snap,
                    signal_snapshot_id=snap.id,
                )
                await message.answer(
                    f"✅ Сделка #{row.id} сохранена (signal #{snap.id}).\n"
                    f"Прогноз из снимка: {pred_snap.get('decision_type', 'n/a')}\n"
                    f"/trade {row.id} · /recheck_trade {row.id}"
                )
                return
        gi, identity = await resolve_gift_identity(user, subj, settings)
        if gi.input_type == GiftInputType.unknown or identity.collection in ("Unknown", "") or identity.number is None:
            await message.answer(format_unknown_gift_input_help(subj, [], context="trade_add"))
            return
        gift = gift_attrs_for_demo(GiftCard(collection=identity.collection, number=identity.number or 0))
        analyzer = AnalyzerService(create_market_source(settings, user_id=user.id))
        est = await analyzer.analyze_gift(gift, risk_mode=user.risk_mode, buy_price_ton=price, owns_asset=False)
        snap = {
            "decision_type": est.decision_type,
            "safe_buy_price_ton": est.safe_buy_price_ton,
            "max_buy_price_ton": est.buy_zone_max_ton,
            "normal_list_price_ton": est.normal_list_price_ton,
            "expected_roi_percent": est.expected_roi_percent,
            "confidence_score": est.confidence_score,
            "precision_plan_json": est.precision_plan_json,
        }
        attrs = [a.model_dump() for a in gift.attributes]
        row = await TradeJournalRepository(session).create(
            user_id=user.id,
            collection=gift.collection,
            number=gift.number,
            nft_address=identity.nft_address,
            attributes_json=attrs,
            buy_price_ton=price,
            notes=note,
            source_url=identity.source_url,
            prediction_snapshot=snap,
        )
    await message.answer(
        f"✅ Сделка #{row.id} сохранена.\n"
        f"Прогноз: {est.decision_type} · safe {est.safe_buy_price_ton} · max {est.buy_zone_max_ton}\n"
        f"/trade {row.id} · /recheck_trade {row.id}"
    )


@router.message(Command("trade_sell"))
async def trade_sell_handler(message: Message) -> None:
    parts = _parts_pipe(message.text or "", "/trade_sell")
    if len(parts) < 2 or not parts[0].isdigit():
        await message.answer("Используйте: /trade_sell <id> | <sell_price> | заметка")
        return
    tid = int(parts[0])
    sp = _to_price(parts[1])
    if sp is None:
        await message.answer("Нужна цена продажи.")
        return
    note = parts[2] if len(parts) > 2 else None
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        row = await TradeJournalRepository(session).mark_sold(tid, user.id, sp, note)
    if row is None:
        await message.answer("Сделка не найдена.")
        return
    buy = float(row.buy_price_ton or 0)
    net = sp * 0.95
    pnl = net - buy
    roi = (pnl / buy * 100.0) if buy > 0 else 0.0
    await message.answer(f"✅ Сделка #{tid} закрыта.\nSell {sp:.2f} TON · PnL ~ {pnl:+.2f} TON · ROI ~ {roi:+.1f}%")


@router.message(Command("trade_cancel"))
async def trade_cancel_handler(message: Message) -> None:
    parts = _parts_pipe(message.text or "", "/trade_cancel")
    if len(parts) < 1 or not parts[0].isdigit():
        await message.answer("Используйте: /trade_cancel <id> | заметка")
        return
    tid = int(parts[0])
    note = parts[1] if len(parts) > 1 else None
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        row = await TradeJournalRepository(session).cancel(tid, user.id, note)
    await message.answer("✅ Отменено." if row else "Не найдено.")


@router.message(Command("trades"))
async def trades_list_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        rows = await TradeJournalRepository(session).list_for_user(user.id, limit=30)
    if not rows:
        await message.answer("Журнал пуст. /trade_add …")
        return
    lines = [f"#{r.id} {r.collection} #{r.number or '?'} · {r.status} · buy {r.buy_price_ton}" for r in rows]
    await message.answer("Журнал:\n" + "\n".join(lines[:25]))


@router.message(Command("trade"))
async def trade_one_handler(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Используйте: /trade <id>")
        return
    tid = int(parts[1])
    settings = get_settings()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        row = await TradeJournalRepository(session).get(tid, user.id)
    if row is None:
        await message.answer("Не найдено.")
        return
    pred = ""
    if row.prediction_json:
        pred = "\nПрогноз при входе:\n" + row.prediction_json[:1200]
    tags = ""
    if row.accuracy_tags_json:
        tags = f"\nTags: {row.accuracy_tags_json}"
    recheck = ""
    gift = gift_attrs_for_demo(GiftCard(collection=row.collection, number=row.number or 0))
    if row.attributes_json and isinstance(row.attributes_json, list):
        gift = gift.model_copy(
            attributes=[GiftAttributeSchema(**a) for a in row.attributes_json if isinstance(a, dict)]
        )
    analyzer = AnalyzerService(create_market_source(settings, user_id=user.id))
    est = await analyzer.analyze_gift(
        gift, risk_mode=user.risk_mode, buy_price_ton=float(row.buy_price_ton or 0), owns_asset=False
    )
    new_plan = PrecisionPricePlan.model_validate_json(est.precision_plan_json) if est.precision_plan_json else None
    old_plan = None
    if row.prediction_json:
        try:
            snap = json.loads(row.prediction_json)
            if snap.get("precision_plan_json"):
                old_plan = PrecisionPricePlan.model_validate_json(snap["precision_plan_json"])
        except Exception:
            pass
    explain = ""
    if old_plan and new_plan:
        explain = "\nИзменение модели:\n" + format_price_change_explanation(compare_price_plans(old_plan, new_plan))
    recheck = (
        f"\n--- Сейчас ---\n{est.decision_type} · safe {est.safe_buy_price_ton} · max {est.buy_zone_max_ton}\n"
        f"List {est.normal_list_price_ton} · conf {est.confidence_score}{explain}\n"
        f"Идея: сравните с прогнозом при входе; это не сигнал автопокупки."
    )
    await _send_long(
        message,
        f"#{row.id} {row.collection} #{row.number}\n"
        f"Status: {row.status}\n"
        f"Buy: {row.buy_price_ton} · Sell: {row.sell_price_ton}\n"
        f"Realized PnL/ROI: {row.realized_profit_ton if row.realized_profit_ton is not None else '—'} / "
        f"{row.realized_roi_percent if row.realized_roi_percent is not None else '—'}%\n"
        f"Hold h: {row.hold_time_hours if row.hold_time_hours is not None else '—'}\n"
        f"{row.notes or ''}{pred}{tags}{recheck}",
    )


@router.message(Command("trade_stats"))
async def trade_stats_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        rows = await TradeJournalRepository(session).list_for_user(user.id, limit=500)
    await _send_long(
        message,
        build_trade_stats_extended(rows) + "\n\n" + build_user_accuracy_report(rows, include_segments=False),
    )


@router.message(Command("accuracy_report"))
async def accuracy_report_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        rows = await TradeJournalRepository(session).list_for_user(user.id, limit=500)
    await message.answer(build_user_accuracy_report(rows))


@router.message(Command("recheck_trade"))
async def recheck_trade_handler(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Используйте: /recheck_trade <id>")
        return
    tid = int(parts[1])
    settings = get_settings()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        row = await TradeJournalRepository(session).get(tid, user.id)
    if row is None:
        await message.answer("Не найдено.")
        return
    gift = gift_attrs_for_demo(GiftCard(collection=row.collection, number=row.number or 0))
    if row.attributes_json and isinstance(row.attributes_json, list):
        gift = gift.model_copy(
            attributes=[GiftAttributeSchema(**a) for a in row.attributes_json if isinstance(a, dict)]
        )
    analyzer = AnalyzerService(create_market_source(settings, user_id=user.id))
    est = await analyzer.analyze_gift(
        gift, risk_mode=user.risk_mode, buy_price_ton=float(row.buy_price_ton or 0), owns_asset=False
    )
    from app.schemas.market_brain import PrecisionPricePlan

    new_plan = PrecisionPricePlan.model_validate_json(est.precision_plan_json) if est.precision_plan_json else None
    old_plan = None
    if row.prediction_json:
        try:
            snap = json.loads(row.prediction_json)
            if snap.get("precision_plan_json"):
                old_plan = PrecisionPricePlan.model_validate_json(snap["precision_plan_json"])
        except Exception:
            pass
    explain = ""
    if old_plan and new_plan:
        diffs = compare_price_plans(old_plan, new_plan)
        explain = "\n" + format_price_change_explanation(diffs)
    await message.answer(
        f"Recheck trade #{tid}\n"
        f"Сейчас: {est.decision_type} · safe {est.safe_buy_price_ton} · max {est.buy_zone_max_ton}\n"
        f"List normal {est.normal_list_price_ton} · conf {est.confidence_score}{explain}"
    )


@router.message(Command("trade_import_help"))
async def trade_import_help_handler(message: Message) -> None:
    await message.answer(
        "📥 Импорт сделок (CSV текстом под командой):\n\n"
        "/trade_import_preview\n"
        "collection,buy_price_ton,number,sell_price_ton,status\n"
        "Ice Cream,180,217467,230,sold\n\n"
        "Обязательно: collection, buy_price_ton.\n"
        "Опционально: number, nft_address, buy_date, sell_price_ton, sell_date, status, "
        "attributes_json (JSON), source_url, notes, decision_type, predicted_* поля.\n"
        "Если sell_price задан — статус будет sold.\n\n"
        "/trade_import_commit — то же тело, записывает в журнал.\n"
        "/trade_export — выгрузка CSV.\n"
        "/backtest_trades — бэктест по закрытым сделкам.\n"
        "/pricing_tuning_report — рекомендации по PRICING_* (не применяются сами)."
    )


@router.message(Command("trade_import_preview"))
async def trade_import_preview_handler(message: Message) -> None:
    csv_body = _csv_lines_after_command(message.text or "", "/trade_import_preview")
    if not csv_body:
        await message.answer("Пришлите CSV после строки команды. /trade_import_help")
        return
    fields, rows = parse_trade_csv(csv_body)
    errs: list[tuple[int, str]] = []
    for i, row in enumerate(rows, start=2):
        ok, e = validate_trade_row(row, i)
        if not ok:
            errs.extend((i, x) for x in e)
    await message.answer(format_trade_import_preview(fields, rows, errs))


@router.message(Command("trade_import_commit"))
async def trade_import_commit_handler(message: Message) -> None:
    csv_body = _csv_lines_after_command(message.text or "", "/trade_import_commit")
    if not csv_body:
        await message.answer("Нет CSV. /trade_import_help")
        return
    _, rows = parse_trade_csv(csv_body)
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        res = await import_trades_for_user(session, user.id, rows)
    await message.answer(format_trade_import_result(res))


@router.message(Command("trade_export"))
async def trade_export_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        rows = await TradeJournalRepository(session).list_for_user(user.id, limit=5000)
    if not rows:
        await message.answer("Журнал пуст.")
        return
    csv_text = format_trade_export_csv(rows)
    await _send_long(message, "Экспорт trade_journal (CSV):\n" + csv_text)


@router.message(Command("backtest_trades"))
async def backtest_trades_handler(message: Message) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        rows = await TradeJournalRepository(session).list_for_user(user.id, limit=2000)
    pairs = journal_rows_to_backtest_pairs(rows)
    if not pairs:
        await message.answer("Нет закрытых сделок с ценами для бэктеста.")
        return
    rep = run_backtest(pairs)
    await _send_long(message, format_backtest_report(rep) + "\n\nСценарный разбор; не обещание будущей доходности.")


@router.message(Command("pricing_tuning_report"))
async def pricing_tuning_report_handler(message: Message) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        rows = await TradeJournalRepository(session).list_for_user(user.id, limit=2000)
    rep = analyze_pricing_accuracy(rows, settings=settings)
    await _send_long(message, format_pricing_tuning_report(rep))
