from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.messages import (
    ALERTS_COMMANDS_HINT,
    ALERTS_EMPTY_TEXT,
    ALERTS_HEADER_TEXT,
    ALERT_ADD_USAGE_TEXT,
    ALERT_CREATED_TEXT,
    ALERT_DELETED_TEXT,
    ALERT_ID_REQUIRED_DELETE_TEXT,
    ALERT_ID_REQUIRED_OFF_TEXT,
    ALERT_ID_REQUIRED_ON_TEXT,
    ALERT_ID_REQUIRED_TEST_TEXT,
    ALERT_NOT_FOUND_TEXT,
    ALERT_OFF_TEXT,
    ALERT_ON_TEXT,
    ALERTS_CHECK_EMPTY_TEXT,
    ALERTS_CHECK_HEADER_TEXT,
)
from app.config import get_settings
from app.db.repositories.alerts import AlertRepository
from app.db.repositories.gifts import GiftRepository
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.services.capital_allocation import allocate_capital_dynamic
from app.services.diversification import get_concentration_warnings
from app.services.market_regime import evaluate_universe_regime
from app.services.notification_policy import format_digest
from app.services import runtime_state
from app.services.audit import log_audit
from app.services.incident_analytics import (
    calculate_incident_age,
    calculate_false_positive_rate,
    find_top_recurring_incidents,
    format_incident_analytics_report,
    summarize_incidents,
)
from app.services.feature_limits import assert_feature_allowed
from app.services.smart_alerts import SMART_ALERT_TYPES
from app.services.alerts import (
    evaluate_alert_rule,
    format_alert_rule,
    parse_alert_command,
)
from app.bot.handlers.portfolio import _collection_reports_from_ranked, _resolve_universe_collections
from app.services.universe_opportunities import gather_ranked_universe_opportunities
from app.sources.factory import create_market_source

router = Router()


def _smart_defaults(alert_type: str, settings) -> tuple[float | None, int]:
    threshold_defaults = {
        "strength_drop": float(settings.smart_alert_strength_drop_threshold),
        "liquidity_crash": float(settings.smart_alert_liquidity_crash_threshold),
        "data_stale": float(settings.smart_alert_data_stale_minutes),
    }
    return threshold_defaults.get(alert_type), int(settings.smart_alert_default_cooldown_minutes)


def _parse_smart_type(text: str, cmd: str) -> str:
    return text.removeprefix(cmd).strip()


def _parse_quiet_hours(text: str) -> tuple[str, str] | None:
    payload = text.removeprefix("/quiet_hours_on").strip()
    parts = [x.strip() for x in payload.split("|")]
    if len(parts) != 2:
        return None
    if ":" not in parts[0] or ":" not in parts[1]:
        return None
    return parts[0], parts[1]


def _parse_incident_pipe(text: str, cmd: str) -> list[str]:
    payload = text.removeprefix(cmd).strip()
    return [x.strip() for x in payload.split("|")]


@router.message(Command("alerts"))
async def alerts_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        rules = await AlertRepository(session).list_user_alert_rules(user.id)
    if not rules:
        await message.answer(ALERTS_EMPTY_TEXT)
        return
    body = "\n\n".join(format_alert_rule(rule) for rule in rules)
    await message.answer(f"{ALERTS_HEADER_TEXT}\n\n{body}{ALERTS_COMMANDS_HINT}")


@router.message(Command("alert_add"))
async def alert_add_handler(message: Message) -> None:
    text = message.text or ""
    try:
        parsed = parse_alert_command(text)
    except ValueError as exc:
        await message.answer(f"{ALERT_ADD_USAGE_TEXT}\n\nДетали: {exc}")
        return

    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        rule = await AlertRepository(session).create_alert_rule(
            user_id=user.id,
            collection=parsed.collection,
            trait_type=parsed.trait_type,
            trait_value=parsed.trait_value,
            max_price_ton=parsed.max_price_ton,
            min_price_ton=parsed.min_price_ton,
            is_active=True,
        )
    await message.answer(f"{ALERT_CREATED_TEXT}\n\n{format_alert_rule(rule)}")


def _parse_rule_id(text: str) -> int | None:
    parts = text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        return None
    return int(parts[1])


@router.message(Command("alert_delete"))
async def alert_delete_handler(message: Message) -> None:
    rule_id = _parse_rule_id(message.text or "")
    if rule_id is None:
        await message.answer(ALERT_ID_REQUIRED_DELETE_TEXT)
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        deleted = await AlertRepository(session).delete_user_alert_rule(user.id, rule_id)
    if not deleted:
        await message.answer(ALERT_NOT_FOUND_TEXT)
        return
    await message.answer(ALERT_DELETED_TEXT.format(rule_id=rule_id))


@router.message(Command("alert_on"))
async def alert_on_handler(message: Message) -> None:
    rule_id = _parse_rule_id(message.text or "")
    if rule_id is None:
        await message.answer(ALERT_ID_REQUIRED_ON_TEXT)
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        rule = await AlertRepository(session).set_alert_rule_active(user.id, rule_id, True)
    if rule is None:
        await message.answer(ALERT_NOT_FOUND_TEXT)
        return
    await message.answer(ALERT_ON_TEXT.format(rule_id=rule_id))


@router.message(Command("alert_off"))
async def alert_off_handler(message: Message) -> None:
    rule_id = _parse_rule_id(message.text or "")
    if rule_id is None:
        await message.answer(ALERT_ID_REQUIRED_OFF_TEXT)
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        rule = await AlertRepository(session).set_alert_rule_active(user.id, rule_id, False)
    if rule is None:
        await message.answer(ALERT_NOT_FOUND_TEXT)
        return
    await message.answer(ALERT_OFF_TEXT.format(rule_id=rule_id))


@router.message(Command("alert_test"))
async def alert_test_handler(message: Message) -> None:
    rule_id = _parse_rule_id(message.text or "")
    if rule_id is None:
        await message.answer(ALERT_ID_REQUIRED_TEST_TEXT)
        return

    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        rule = await AlertRepository(session).get_user_alert_rule(user.id, rule_id)
    if rule is None:
        await message.answer(ALERT_NOT_FOUND_TEXT)
        return

    source = create_market_source(get_settings(), user_id=user.id)
    evaluation = await evaluate_alert_rule(rule, source)
    trait_line = (
        f"\nTrait: {evaluation.trait_type} = {evaluation.trait_value}"
        if evaluation.trait_type and evaluation.trait_value
        else ""
    )
    value_text = f"{evaluation.current_value_ton:.2f} TON" if evaluation.current_value_ton is not None else "нет данных"
    status = "сработает" if evaluation.triggered else "пока не сработает"
    await message.answer(
        f"🧪 Проверка уведомления #{evaluation.rule_id}\n\n"
        f"Коллекция: {evaluation.collection}{trait_line}\n"
        f"Текущая цена: {value_text}\n"
        f"Условие: {evaluation.condition_text}\n"
        f"Источник: {evaluation.source.title()}\n\n"
        f"Статус: {status}"
    )


@router.message(Command("alerts_check"))
async def alerts_check_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        rules = await AlertRepository(session).list_user_alert_rules(user.id)
    active_rules = [rule for rule in rules if rule.is_active]
    if not active_rules:
        await message.answer(ALERTS_CHECK_EMPTY_TEXT)
        return

    source = create_market_source(get_settings(), user_id=user.id)
    chunks: list[str] = []
    for rule in active_rules:
        evaluation = await evaluate_alert_rule(rule, source)
        trait_suffix = (
            f" / {evaluation.trait_type} = {evaluation.trait_value}"
            if evaluation.trait_type and evaluation.trait_value
            else ""
        )
        value_text = f"{evaluation.current_value_ton:.2f} TON" if evaluation.current_value_ton is not None else "нет данных"
        status = "сработает" if evaluation.triggered else "пока не сработает"
        chunks.append(
            f"#{evaluation.rule_id} {evaluation.collection}{trait_suffix}\n"
            f"Текущая цена: {value_text}\n"
            f"Условие: {evaluation.condition_text}\n"
            f"Статус: {status}"
        )

    await message.answer(f"{ALERTS_CHECK_HEADER_TEXT}\n\n" + "\n\n".join(chunks))


@router.message(Command("smart_alerts"))
async def smart_alerts_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        rules = await AlertRepository(session).list_user_smart_alert_rules(user.id)
    if not rules:
        await message.answer("Smart alerts пока не включены. Используйте /smart_alert_on <type>.")
        return
    lines = [
        f"- {r.alert_type}: {'on' if r.is_active else 'off'}; threshold={r.threshold_value}; cooldown={r.cooldown_minutes}"
        for r in rules
    ]
    await message.answer("🧠 Smart alerts\n" + "\n".join(lines))


@router.message(Command("smart_alert_on"))
async def smart_alert_on_handler(message: Message) -> None:
    alert_type = _parse_smart_type(message.text or "", "/smart_alert_on")
    if alert_type not in SMART_ALERT_TYPES:
        await message.answer("Неизвестный type. Доступно: " + ", ".join(sorted(SMART_ALERT_TYPES)))
        return
    settings = get_settings()
    threshold, cooldown = _smart_defaults(alert_type, settings)
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        try:
            assert_feature_allowed(user, "smart_alerts")
        except PermissionError as exc:
            await message.answer(str(exc))
            return
        await AlertRepository(session).upsert_smart_alert_rule(
            user_id=user.id,
            alert_type=alert_type,
            threshold_value=threshold,
            cooldown_minutes=cooldown,
            is_active=True,
        )
    await message.answer(f"✅ Smart alert включен: {alert_type}")


@router.message(Command("smart_alert_off"))
async def smart_alert_off_handler(message: Message) -> None:
    alert_type = _parse_smart_type(message.text or "", "/smart_alert_off")
    if alert_type not in SMART_ALERT_TYPES:
        await message.answer("Неизвестный type. Доступно: " + ", ".join(sorted(SMART_ALERT_TYPES)))
        return
    settings = get_settings()
    threshold, cooldown = _smart_defaults(alert_type, settings)
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        await AlertRepository(session).upsert_smart_alert_rule(
            user_id=user.id,
            alert_type=alert_type,
            threshold_value=threshold,
            cooldown_minutes=cooldown,
            is_active=False,
        )
    await message.answer(f"⏸ Smart alert выключен: {alert_type}")


@router.message(Command("smart_alert_set"))
async def smart_alert_set_handler(message: Message) -> None:
    payload = (message.text or "").removeprefix("/smart_alert_set").strip()
    parts = [x.strip() for x in payload.split("|")]
    if len(parts) != 3:
        await message.answer("Используйте: /smart_alert_set <type> | <threshold> | <cooldown_minutes>")
        return
    alert_type = parts[0]
    if alert_type not in SMART_ALERT_TYPES:
        await message.answer("Неизвестный type.")
        return
    try:
        threshold = float(parts[1])
        cooldown = int(parts[2])
    except ValueError:
        await message.answer("Threshold/cooldown должны быть числами.")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        try:
            assert_feature_allowed(user, "smart_alerts")
        except PermissionError as exc:
            await message.answer(str(exc))
            return
        await AlertRepository(session).upsert_smart_alert_rule(
            user_id=user.id,
            alert_type=alert_type,
            threshold_value=threshold,
            cooldown_minutes=cooldown,
            is_active=True,
        )
    await message.answer("✅ Smart alert settings обновлены.")


@router.message(Command("smart_alert_settings"))
async def smart_alert_settings_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        rules = await AlertRepository(session).list_user_smart_alert_rules(user.id)
    if not rules:
        await message.answer("Smart alert settings пусты.")
        return
    lines = [f"- {r.alert_type}: threshold={r.threshold_value}, cooldown={r.cooldown_minutes}, active={r.is_active}" for r in rules]
    await message.answer("⚙️ Smart alert settings\n" + "\n".join(lines))


@router.message(Command("health_dashboard"))
async def health_dashboard_handler(message: Message) -> None:
    async with SessionLocal() as session:
        repo = AlertRepository(session)
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        alerts = await repo.list_user_smart_alert_rules(user.id)
        notify_settings = await repo.get_or_create_notification_settings(user.id)
        gifts = await GiftRepository(session).list_by_user(user.id)
        open_incidents = await repo.list_open_incidents(user.id)
        recovered_incidents = await repo.list_recovered_incidents(user.id, limit=50)
        recoveries = recovered_incidents[:1]
        recent_events = await repo.list_recent_events(user.id, limit=100)
        recurring = await repo.list_recurring_incidents(user.id, days=7)
    collections = await _resolve_universe_collections(user.id)
    ranked = await gather_ranked_universe_opportunities(user, collections, get_settings())
    reports = _collection_reports_from_ranked(ranked, [])
    regime = evaluate_universe_regime(reports)
    top_warnings = []
    for rep in reports:
        top_warnings.extend(rep.warnings)
    portfolio_rows = [{"collection": g.collection, "value_ton": g.purchase_price_ton or 0.0} for g in gifts]
    conc = get_concentration_warnings(portfolio_rows, user)
    summary = summarize_incidents(open_incidents, recovered_incidents)
    _, fp_rate = calculate_false_positive_rate(open_incidents + recovered_incidents)
    top_recurring = recurring[0][0] if recurring else "n/a"
    oldest_open_age = f"{int(calculate_incident_age(summary['oldest_open']) // 60)}h" if summary["oldest_open"] else "n/a"
    await message.answer(
        "🩺 Health Dashboard\n\n"
        f"Market regime: {regime.regime} ({regime.score}/100)\n"
        f"Universe collections: {len(collections)}\n"
        f"Active smart alerts: {len([r for r in alerts if r.is_active])}\n"
        f"Data freshness summary: {', '.join(sorted(set(r.freshness_label for r in reports))) if reports else 'n/a'}\n"
        f"Portfolio concentration: {('; '.join(conc) if conc else 'ok')}\n"
        f"Open incidents: {len(open_incidents)}\n"
        f"Critical incidents: {len([x for x in open_incidents if x.severity.lower()=='critical'])}\n"
        f"Last recovery: {(recoveries[0].recovered_at if recoveries else 'n/a')}\n"
        f"Top open incident: {(f'#{open_incidents[0].id} {open_incidents[0].alert_type}' if open_incidents else 'none')}\n"
        f"Suppressed events (24h): {len([e for e in recent_events if (not e.is_sent and not e.is_batched)])}\n"
        f"Acknowledged open incidents: {summary['ack_count']}\n"
        f"Muted incidents: {summary['muted_count']}\n"
        f"False positives 7d: {fp_rate:.1f}%\n"
        f"Oldest open incident age: {oldest_open_age}\n"
        f"Average TTR: {summary['avg_ttr_minutes']:.1f} min\n"
        f"Top recurring alert type: {top_recurring}\n"
        f"Last price alert check: {runtime_state.last_price_alert_check or 'n/a'}\n"
        f"Last smart alert check: {runtime_state.last_smart_alert_check or 'n/a'}\n"
        f"Last digest check: {runtime_state.last_digest_check or 'n/a'}\n"
        f"Active notification mode: {notify_settings.delivery_mode}\n"
        f"Quiet hours: {'on' if notify_settings.quiet_hours_enabled else 'off'}\n"
        f"Top warnings: {('; '.join(top_warnings[:3]) if top_warnings else 'none')}"
    )


@router.message(Command("notify_settings"))
async def notify_settings_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        row = await AlertRepository(session).get_or_create_notification_settings(user.id)
    await message.answer(
        "🔔 Notification settings\n"
        f"- delivery mode: {row.delivery_mode}\n"
        f"- quiet hours: {'on' if row.quiet_hours_enabled else 'off'} ({row.quiet_hours_start}-{row.quiet_hours_end})\n"
        f"- digest interval: {row.digest_interval_minutes} min\n"
        f"- min severity: {row.min_severity_to_notify}\n"
        f"- critical ignore quiet: {row.critical_ignore_quiet_hours}"
    )


@router.message(Command("notify_mode"))
async def notify_mode_handler(message: Message) -> None:
    mode = (message.text or "").removeprefix("/notify_mode").strip().lower()
    if mode not in {"instant", "digest", "smart"}:
        await message.answer("Используйте: /notify_mode <instant|digest|smart>")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        await AlertRepository(session).update_notification_settings(user.id, delivery_mode=mode)
        await log_audit(
            session,
            user_id=user.id,
            action="notification_settings_changed",
            entity_type="user",
            entity_id=str(user.id),
            metadata_json={"delivery_mode": mode},
        )
    await message.answer(f"✅ Notification mode: {mode}")


@router.message(Command("quiet_hours_on"))
async def quiet_hours_on_handler(message: Message) -> None:
    parsed = _parse_quiet_hours(message.text or "")
    if parsed is None:
        await message.answer("Используйте: /quiet_hours_on 23:00 | 08:00")
        return
    start, end = parsed
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        await AlertRepository(session).update_notification_settings(
            user.id, quiet_hours_enabled=True, quiet_hours_start=start, quiet_hours_end=end
        )
        await log_audit(
            session,
            user_id=user.id,
            action="notification_settings_changed",
            entity_type="user",
            entity_id=str(user.id),
            metadata_json={"quiet_hours_enabled": True, "start": start, "end": end},
        )
    await message.answer("✅ Quiet hours включены.")


@router.message(Command("quiet_hours_off"))
async def quiet_hours_off_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        await AlertRepository(session).update_notification_settings(user.id, quiet_hours_enabled=False)
        await log_audit(
            session,
            user_id=user.id,
            action="notification_settings_changed",
            entity_type="user",
            entity_id=str(user.id),
            metadata_json={"quiet_hours_enabled": False},
        )
    await message.answer("⏸ Quiet hours выключены.")


@router.message(Command("min_severity"))
async def min_severity_handler(message: Message) -> None:
    level = (message.text or "").removeprefix("/min_severity").strip().lower()
    if level not in {"info", "warning", "critical"}:
        await message.answer("Используйте: /min_severity <info|warning|critical>")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        await AlertRepository(session).update_notification_settings(user.id, min_severity_to_notify=level)
        await log_audit(
            session,
            user_id=user.id,
            action="notification_settings_changed",
            entity_type="user",
            entity_id=str(user.id),
            metadata_json={"min_severity_to_notify": level},
        )
    await message.answer(f"✅ min severity: {level}")


@router.message(Command("digest_now"))
async def digest_now_handler(message: Message) -> None:
    async with SessionLocal() as session:
        repo = AlertRepository(session)
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        events = await repo.list_pending_batched_events(user_id=user.id)
        if not events:
            await message.answer("Digest пуст.")
            return
        await message.answer(format_digest(events))
        await repo.mark_events_sent([e.id for e in events], datetime.now(timezone.utc))


@router.message(Command("alert_history"))
async def alert_history_handler(message: Message) -> None:
    async with SessionLocal() as session:
        repo = AlertRepository(session)
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        events = await repo.list_recent_events(user.id, limit=10)
    if not events:
        await message.answer("История alert events пуста.")
        return
    grouped: dict[str, list] = {}
    for e in events:
        key = f"incident #{e.incident_id}" if e.incident_id else "no incident"
        grouped.setdefault(key, []).append(e)
    lines = []
    for key, items in grouped.items():
        lines.append(f"{key}:")
        for e in items:
            lines.append(
                f"  - {e.severity.upper()} {e.alert_type} {f'[{e.collection}]' if e.collection else ''} "
                f"(sent={e.is_sent}, batched={e.is_batched}) at {e.created_at}"
            )
    await message.answer("🕘 Alert history\n" + "\n".join(lines))


@router.message(Command("incidents"))
async def incidents_handler(message: Message) -> None:
    async with SessionLocal() as session:
        repo = AlertRepository(session)
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        try:
            assert_feature_allowed(user, "incidents")
        except PermissionError as exc:
            await message.answer(str(exc))
            return
        rows = await repo.list_open_incidents(user.id)
    if not rows:
        await message.answer("Открытых incidents нет.")
        return
    lines = [
        f"#{x.id} {x.severity.upper()} {x.alert_type} {f'[{x.collection}]' if x.collection else ''}\n"
        f"first: {x.first_seen_at}\nlast: {x.last_seen_at}\ncount: {x.event_count}\nstatus: {x.status}\n"
        f"ack: {'yes' if x.acknowledged_at else 'no'} / muted: {'yes' if x.muted_until else 'no'}"
        for x in rows
    ]
    await message.answer("🔥 Open incidents\n\n" + "\n\n".join(lines))


@router.message(Command("incident"))
async def incident_handler(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Используйте: /incident <id>")
        return
    incident_id = int(parts[1])
    async with SessionLocal() as session:
        repo = AlertRepository(session)
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        try:
            assert_feature_allowed(user, "incidents")
        except PermissionError as exc:
            await message.answer(str(exc))
            return
        incident = await repo.get_incident(user.id, incident_id)
        events = await repo.list_recent_events(user.id, limit=30)
    if incident is None:
        await message.answer("Incident не найден.")
        return
    timeline = [e for e in events if e.incident_id == incident.id][:10]
    actions = await repo.list_incident_actions(user.id, incident.id)
    timeline_text = "\n".join(f"- {e.created_at}: {e.severity.upper()} {e.alert_type}" for e in timeline) or "- нет событий"
    actions_text = "\n".join(f"- {a.created_at}: {a.action_type} ({a.note or 'no note'})" for a in actions[:10]) or "- нет"
    await message.answer(
        f"🧾 Incident #{incident.id}\n\n"
        f"Title: {incident.title}\n"
        f"Status: {incident.status}\n"
        f"Severity: {incident.severity}\n"
        f"Escalation level: {incident.escalation_level}\n"
        f"Summary: {incident.summary or 'n/a'}\n"
        f"Ack: {'yes' if incident.acknowledged_at else 'no'}\n"
        f"Muted until: {incident.muted_until or 'no'}\n"
        f"Manual resolved: {incident.resolved_manually_at or 'no'}\n"
        f"False positive: {'yes' if incident.is_false_positive else 'no'}\n"
        f"Event count: {incident.event_count}\n"
        f"Timeline:\n{timeline_text}\n"
        f"Actions:\n{actions_text}\n"
        f"Recommended action: {'reduce risk / wait data' if incident.severity in ('critical','warning') else 'monitor'}"
    )


@router.message(Command("recoveries"))
async def recoveries_handler(message: Message) -> None:
    async with SessionLocal() as session:
        repo = AlertRepository(session)
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        rows = await repo.list_recovered_incidents(user.id, limit=10)
    if not rows:
        await message.answer("Recovery incidents пока нет.")
        return
    lines = [f"#{x.id} {x.alert_type} recovered at {x.recovered_at}" for x in rows]
    await message.answer("✅ Recoveries\n" + "\n".join(lines))


@router.message(Command("incident_ack"))
async def incident_ack_handler(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Используйте: /incident_ack <id>")
        return
    async with SessionLocal() as session:
        repo = AlertRepository(session)
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        try:
            assert_feature_allowed(user, "incidents")
        except PermissionError as exc:
            await message.answer(str(exc))
            return
        row = await repo.acknowledge_incident(user.id, int(parts[1]))
    await message.answer("✅ Incident acknowledged." if row else "Incident не найден.")


@router.message(Command("incident_mute"))
async def incident_mute_handler(message: Message) -> None:
    parts = _parse_incident_pipe(message.text or "", "/incident_mute")
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await message.answer("Используйте: /incident_mute <id> | <minutes> | <reason optional>")
        return
    reason = parts[2] if len(parts) > 2 else None
    async with SessionLocal() as session:
        repo = AlertRepository(session)
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        try:
            assert_feature_allowed(user, "incidents")
        except PermissionError as exc:
            await message.answer(str(exc))
            return
        row = await repo.mute_incident(user.id, int(parts[0]), int(parts[1]), reason)
    await message.answer("🔕 Incident muted." if row else "Incident не найден.")


@router.message(Command("incident_unmute"))
async def incident_unmute_handler(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Используйте: /incident_unmute <id>")
        return
    async with SessionLocal() as session:
        repo = AlertRepository(session)
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        try:
            assert_feature_allowed(user, "incidents")
        except PermissionError as exc:
            await message.answer(str(exc))
            return
        row = await repo.unmute_incident(user.id, int(parts[1]))
    await message.answer("🔔 Incident unmuted." if row else "Incident не найден.")


@router.message(Command("incident_resolve"))
async def incident_resolve_handler(message: Message) -> None:
    parts = _parse_incident_pipe(message.text or "", "/incident_resolve")
    if not parts or not parts[0].isdigit():
        await message.answer("Используйте: /incident_resolve <id> | <note optional>")
        return
    note = parts[1] if len(parts) > 1 else None
    async with SessionLocal() as session:
        repo = AlertRepository(session)
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        try:
            assert_feature_allowed(user, "incidents")
        except PermissionError as exc:
            await message.answer(str(exc))
            return
        row = await repo.resolve_incident_manually(user.id, int(parts[0]), note)
        if row:
            await log_audit(
                session,
                user_id=user.id,
                action="incident_resolve_manual",
                entity_type="incident",
                entity_id=str(row.id),
                metadata_json={"note": note},
            )
    await message.answer("✅ Incident resolved manually." if row else "Incident не найден.")


@router.message(Command("incident_false_positive"))
async def incident_false_positive_handler(message: Message) -> None:
    parts = _parse_incident_pipe(message.text or "", "/incident_false_positive")
    if not parts or not parts[0].isdigit():
        await message.answer("Используйте: /incident_false_positive <id> | <note optional>")
        return
    note = parts[1] if len(parts) > 1 else None
    async with SessionLocal() as session:
        repo = AlertRepository(session)
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        try:
            assert_feature_allowed(user, "incidents")
        except PermissionError as exc:
            await message.answer(str(exc))
            return
        row = await repo.mark_incident_false_positive(user.id, int(parts[0]), note)
        if row:
            await log_audit(
                session,
                user_id=user.id,
                action="incident_false_positive",
                entity_type="incident",
                entity_id=str(row.id),
                metadata_json={"note": note},
            )
    await message.answer("✅ Marked as false positive." if row else "Incident не найден.")


@router.message(Command("incident_note"))
async def incident_note_handler(message: Message) -> None:
    parts = _parse_incident_pipe(message.text or "", "/incident_note")
    if len(parts) < 2 or not parts[0].isdigit():
        await message.answer("Используйте: /incident_note <id> | <note>")
        return
    async with SessionLocal() as session:
        repo = AlertRepository(session)
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        try:
            assert_feature_allowed(user, "incidents")
        except PermissionError as exc:
            await message.answer(str(exc))
            return
        row = await repo.add_incident_note(user.id, int(parts[0]), parts[1])
    await message.answer("📝 Note added." if row else "Incident не найден.")


@router.message(Command("incident_actions"))
async def incident_actions_handler(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Используйте: /incident_actions <id>")
        return
    async with SessionLocal() as session:
        repo = AlertRepository(session)
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        try:
            assert_feature_allowed(user, "incidents")
        except PermissionError as exc:
            await message.answer(str(exc))
            return
        actions = await repo.list_incident_actions(user.id, int(parts[1]))
    if not actions:
        await message.answer("Действий по incident нет.")
        return
    text = "\n".join(f"- {a.created_at}: {a.action_type} ({a.note or 'no note'})" for a in actions[:20])
    await message.answer("🧷 Incident actions\n" + text)


@router.message(Command("incident_analytics"))
async def incident_analytics_handler(message: Message) -> None:
    async with SessionLocal() as session:
        repo = AlertRepository(session)
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        try:
            assert_feature_allowed(user, "incidents")
        except PermissionError as exc:
            await message.answer(str(exc))
            return
        open_incidents = await repo.list_open_incidents(user.id)
        recovered = await repo.list_recovered_incidents(user.id, limit=100)
        recurring = await repo.list_recurring_incidents(user.id, days=7)
    summary = summarize_incidents(open_incidents, recovered)
    top = find_top_recurring_incidents(recurring, top_n=3)
    fp_count, fp_rate = calculate_false_positive_rate(open_incidents + recovered)
    await message.answer(format_incident_analytics_report(summary, top, fp_count, fp_rate))


@router.message(Command("scheduler_status"))
async def scheduler_status_handler(message: Message) -> None:
    await message.answer(
        "🛠 Scheduler status\n"
        "- scheduler: active\n"
        f"- last price alert check: {runtime_state.last_price_alert_check or 'n/a'}\n"
        f"- last smart alert check: {runtime_state.last_smart_alert_check or 'n/a'}\n"
        f"- last digest check: {runtime_state.last_digest_check or 'n/a'}\n"
        "- next expected checks: based on configured intervals"
    )
