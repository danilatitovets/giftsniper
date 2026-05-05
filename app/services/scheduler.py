import logging
from datetime import datetime, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.repositories.alerts import AlertRepository
from app.db.repositories.feedback import FeedbackRepository
from app.db.repositories.gifts import GiftRepository
from app.db.repositories.users import UserRepository
from app.services.market_regime import evaluate_universe_regime
from app.services.product_analytics import (
    calculate_activation_metrics,
    calculate_feature_usage,
    calculate_funnel_metrics,
    calculate_retention_metrics,
    format_beta_metrics_report,
)
from app.services.notification_policy import classify_severity, format_digest, should_batch, should_send_now
from app.services import runtime_state
from app.services.accuracy_digest import build_owner_accuracy_digest_text
from app.services.manual_payments import expire_old_pending_requests, list_stale_submitted_requests
from app.services.incident_manager import (
    detect_recovery,
    escalate_incident,
    format_incident_update,
    format_recovery_message,
    should_suppress_event,
)
from app.services.smart_alerts import (
    evaluate_concentration_risk,
    evaluate_data_stale,
    evaluate_liquidity_crash,
    evaluate_rebalance_needed,
    evaluate_regime_change,
    evaluate_stay_in_cash,
    evaluate_strength_drop,
    payload_hash,
    should_send_smart_alert,
)
from app.services.alerts import evaluate_alert_rule, format_alert_notification, should_send_alert_notification
from app.bot.handlers.portfolio import _collection_reports_from_ranked, _resolve_universe_collections
from app.services.universe_opportunities import gather_ranked_universe_opportunities
from app.services.entitlements import downgrade_expired_users
from app.services.financial_analytics import calculate_revenue_summary
from app.services.watchlist_signals_job import check_watchlist_signals_job
from app.sources.factory import create_market_source

logger = logging.getLogger(__name__)


async def check_alert_rules_job(bot: Bot, session_maker, settings) -> None:
    now = datetime.now(timezone.utc)
    runtime_state.last_price_alert_check = now
    async with session_maker() as session:
        alerts_repo = AlertRepository(session)
        users_repo = UserRepository(session)
        rules = await alerts_repo.list_active_alert_rules()
        for rule in rules:
            try:
                market_source = create_market_source(settings, user_id=rule.user_id)
                evaluation = await evaluate_alert_rule(rule, market_source)
                should_send = should_send_alert_notification(
                    rule,
                    evaluation,
                    now=now,
                    cooldown_minutes=settings.alert_cooldown_minutes,
                )
                if should_send:
                    user = await users_repo.get_by_id(rule.user_id)
                    if user is not None:
                        await bot.send_message(
                            chat_id=user.telegram_id,
                            text=format_alert_notification(rule, evaluation),
                        )
                await alerts_repo.update_alert_rule_state(
                    rule_id=rule.id,
                    last_checked_at=now,
                    last_is_triggered=evaluation.triggered,
                    last_value_ton=evaluation.current_value_ton,
                    triggered_now=evaluation.triggered,
                )
            except Exception as exc:
                logger.exception("Alert rule check failed for rule_id=%s: %s", rule.id, exc)


async def check_smart_alerts_job(bot: Bot, session_maker, settings) -> None:
    now = datetime.now(timezone.utc)
    runtime_state.last_smart_alert_check = now
    async with session_maker() as session:
        alerts_repo = AlertRepository(session)
        users_repo = UserRepository(session)
        gift_repo = GiftRepository(session)
        try:
            users = await users_repo.list_all()
        except Exception as exc:
            logger.exception("Smart alert user list failed: %s", exc)
            return
        for user in users:
            try:
                smart_rules = [r for r in await alerts_repo.list_user_smart_alert_rules(user.id) if r.is_active]
                if not smart_rules:
                    continue
                collections = await _resolve_universe_collections(user.id)
                ranked = await gather_ranked_universe_opportunities(user, collections, settings)
                gifts = await gift_repo.list_by_user(user.id)
                portfolio_rows = [{"collection": g.collection, "value_ton": g.purchase_price_ton or 0.0} for g in gifts]
                reports = _collection_reports_from_ranked(ranked, portfolio_rows)
                regime = evaluate_universe_regime(reports)
                for rule in smart_rules:
                    alert_text = ""
                    if rule.alert_type == "regime_change":
                        state = await alerts_repo.get_smart_alert_state(user.id, "regime_change", None)
                        fired, alert_text = evaluate_regime_change(user, regime.regime, state)
                    elif rule.alert_type == "stay_in_cash":
                        fired, alert_text = evaluate_stay_in_cash(regime, ranked)
                    elif rule.alert_type == "concentration_risk":
                        fired, alert_text = evaluate_concentration_risk(portfolio_rows, user)
                    elif rule.alert_type == "rebalance_needed":
                        fired, alert_text = evaluate_rebalance_needed(portfolio_rows, reports)
                    elif rule.alert_type in {"strength_drop", "liquidity_crash", "data_stale"} and reports:
                        target = reports[0]
                        state = await alerts_repo.get_smart_alert_state(user.id, rule.alert_type, target.collection)
                        threshold = float(rule.threshold_value or 0)
                        if rule.alert_type == "strength_drop":
                            fired, alert_text = evaluate_strength_drop(target, state, threshold or settings.smart_alert_strength_drop_threshold)
                        elif rule.alert_type == "liquidity_crash":
                            fired, alert_text = evaluate_liquidity_crash(
                                target, threshold or settings.smart_alert_liquidity_crash_threshold
                            )
                        else:
                            fired, alert_text = evaluate_data_stale(target, int(threshold or settings.smart_alert_data_stale_minutes))
                    else:
                        fired = False
                    if not fired:
                        continue
                    severity = classify_severity(rule.alert_type, {"regime": regime.regime})
                    title = f"{rule.alert_type} ({severity})"
                    new_hash = payload_hash(alert_text)
                    event = await alerts_repo.create_smart_alert_event(
                        user_id=user.id,
                        alert_type=rule.alert_type,
                        severity=severity,
                        title=title,
                        message=alert_text,
                        payload_hash=new_hash,
                        collection=None,
                        is_sent=False,
                        is_batched=False,
                    )
                    state = await alerts_repo.get_smart_alert_state(user.id, rule.alert_type, None)
                    cooldown = int(rule.cooldown_minutes or settings.smart_alert_default_cooldown_minutes)
                    incident = await alerts_repo.find_open_incident(user.id, rule.alert_type, None)
                    if should_suppress_event(incident, event, now):
                        continue
                    if incident is None:
                        incident = await alerts_repo.create_incident(
                            user_id=user.id,
                            alert_type=rule.alert_type,
                            collection=None,
                            severity=severity,
                            title=title,
                            summary=alert_text,
                            payload_hash=new_hash,
                        )
                    else:
                        new_sev, esc_inc = escalate_incident(incident, event, now)
                        incident = await alerts_repo.update_incident(
                            incident.id,
                            severity=new_sev,
                            summary=alert_text,
                            payload_hash=new_hash,
                            escalation_increment=esc_inc,
                            event_increment=1,
                        )
                    await alerts_repo.link_event_to_incident(event.id, incident.id)

                    # Recovery detection for open incidents.
                    recovered, recovery_summary = detect_recovery(
                        rule.alert_type,
                        {
                            "prev_regime": getattr(state, "last_regime", None),
                            "current_regime": regime.regime,
                            "liquidity_score": reports[0].liquidity_score if reports else 0,
                            "threshold": float(rule.threshold_value or settings.smart_alert_liquidity_crash_threshold),
                            "exposure_percent": 0,
                            "limit_percent": float(user.max_collection_percent or 40),
                            "best_tier": ranked[0]["score"].final_rank_label if ranked else "AVOID",
                            "regime": regime.regime,
                            "freshness": reports[0].freshness_label if reports else "unknown",
                        },
                    )
                    if recovered and incident.status == "open":
                        incident = await alerts_repo.update_incident(
                            incident.id, status="recovered", recovered_at=now, summary=recovery_summary, event_increment=0
                        )
                        recovery_event = await alerts_repo.create_smart_alert_event(
                            user_id=user.id,
                            alert_type=f"{rule.alert_type}_recovery",
                            severity="info",
                            title=f"Recovery: {rule.alert_type}",
                            message=format_recovery_message(incident, recovery_summary),
                            payload_hash=payload_hash(f"recovery:{incident.id}:{recovery_summary}"),
                            is_sent=False,
                            is_batched=True,
                        )
                        await alerts_repo.link_event_to_incident(recovery_event.id, incident.id)
                    if not should_send_smart_alert(
                        getattr(state, "last_sent_at", None),
                        cooldown_minutes=cooldown,
                        new_hash=new_hash,
                        old_hash=getattr(state, "last_payload_hash", None),
                    ):
                        continue
                    notif_settings = await alerts_repo.get_or_create_notification_settings(user.id)
                    if should_send_now(notif_settings, event, now):
                        await bot.send_message(chat_id=user.telegram_id, text=format_incident_update(incident, event))
                        await alerts_repo.mark_events_sent([event.id], now)
                    elif should_batch(notif_settings, event, now):
                        event.is_batched = True
                        await session.commit()
                    await alerts_repo.upsert_smart_alert_state(
                        user_id=user.id,
                        alert_type=rule.alert_type,
                        collection=None,
                        last_regime=regime.regime,
                        last_strength_score=(reports[0].relative_strength_score if reports else None),
                        last_liquidity_score=(reports[0].liquidity_score if reports else None),
                        last_payload_hash=new_hash,
                        last_sent_at=now,
                    )
            except Exception as exc:
                logger.exception("Smart alert check failed for user_id=%s: %s", user.id, exc)


async def send_digest_job(bot: Bot, session_maker, settings) -> None:
    now = datetime.now(timezone.utc)
    runtime_state.last_digest_check = now
    async with session_maker() as session:
        alerts_repo = AlertRepository(session)
        users_repo = UserRepository(session)
        pending = await alerts_repo.list_pending_batched_events()
        by_user: dict[int, list] = {}
        for e in pending:
            by_user.setdefault(e.user_id, []).append(e)
        for user_id, events in by_user.items():
            try:
                user = await users_repo.get_by_id(user_id)
                if user is None:
                    continue
                filtered_events = []
                for e in events:
                    if e.incident_id is None:
                        filtered_events.append(e)
                        continue
                    inc = await alerts_repo.get_incident(user_id, e.incident_id)
                    if inc is None:
                        filtered_events.append(e)
                        continue
                    if inc.muted_until is not None and not e.alert_type.endswith("_recovery"):
                        continue
                    if inc.acknowledged_at is not None and e.severity.lower() != "critical" and not e.alert_type.endswith("_recovery"):
                        continue
                    filtered_events.append(e)
                events = filtered_events
                if not events:
                    continue
                settings_row = await alerts_repo.get_or_create_notification_settings(user_id)
                # Simple digest interval guard by latest sent_at in batch.
                if events and settings_row.digest_interval_minutes > 0:
                    latest = max((e.sent_at or e.created_at) for e in events)
                    if latest and (now - latest).total_seconds() < settings_row.digest_interval_minutes * 60:
                        continue
                await bot.send_message(chat_id=user.telegram_id, text=format_digest(events))
                await alerts_repo.mark_events_sent([e.id for e in events], now)
            except Exception as exc:
                logger.exception("Digest send failed for user_id=%s: %s", user_id, exc)


async def check_entitlements_job(bot: Bot, session_maker, settings) -> None:
    now = datetime.now(timezone.utc)
    async with session_maker() as session:
        users_repo = UserRepository(session)
        changed_user_ids = await downgrade_expired_users(session)
        for user_id in changed_user_ids:
            try:
                user = await users_repo.get_by_id(user_id)
                if user is None:
                    continue
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text="💳 Entitlement update: срок плана изменился. Проверьте /my_plan.",
                )
            except Exception as exc:
                logger.exception("Entitlement notification failed user_id=%s: %s", user_id, exc)


async def expire_manual_payment_requests_job(bot: Bot, session_maker, settings) -> None:
    now = datetime.now(timezone.utc)
    runtime_state.last_manual_payment_expiry_check = now
    admin_ids = [int(x.strip()) for x in settings.admin_telegram_ids.split(",") if x.strip().isdigit()]
    async with session_maker() as session:
        expired = await expire_old_pending_requests(session)
        stale_submitted = await list_stale_submitted_requests(session)
    # Alert admins about stale submitted payments with simple cooldown.
    for req in stale_submitted:
        last = runtime_state.last_stuck_payment_alert_by_request.get(req.id)
        if last and (now - last).total_seconds() < settings.admin_payment_alert_cooldown_minutes * 60:
            continue
        runtime_state.last_stuck_payment_alert_by_request[req.id] = now
        for admin_id in admin_ids:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=(
                        "⚠️ Stuck manual payment\n"
                        f"Request #{req.id}\n"
                        f"User: {req.user_id}\n"
                        f"Plan: {req.requested_plan}\n"
                        f"Submitted: {req.created_at}\n"
                        f"Action: /admin_payment {req.id}"
                    ),
                )
            except Exception as exc:
                logger.exception("Stuck payment alert failed admin_id=%s request_id=%s: %s", admin_id, req.id, exc)
    if expired:
        logger.info("Expired manual payment requests: %s", [x.id for x in expired])


async def send_owner_accuracy_digest_job(bot: Bot, session_maker, settings) -> None:
    admin_ids = [int(x.strip()) for x in settings.admin_telegram_ids.split(",") if x.strip().isdigit()]
    if not admin_ids:
        return
    now = datetime.now(timezone.utc)
    runtime_state.last_accuracy_digest_check = now
    async with session_maker() as session:
        text = await build_owner_accuracy_digest_text(session, settings)
    chunk = 3800
    for admin_id in admin_ids:
        try:
            for i in range(0, len(text), chunk):
                await bot.send_message(chat_id=admin_id, text=text[i : i + chunk])
        except Exception as exc:
            logger.exception("Accuracy digest failed admin_id=%s: %s", admin_id, exc)


async def send_owner_weekly_summary_job(bot: Bot, session_maker, settings) -> None:
    admin_ids = [int(x.strip()) for x in settings.admin_telegram_ids.split(",") if x.strip().isdigit()]
    if not admin_ids:
        return
    async with session_maker() as session:
        activation = await calculate_activation_metrics(session, period_days=7)
        retention = await calculate_retention_metrics(session, period_days=7)
        funnel = await calculate_funnel_metrics(session, period_days=7)
        feature = await calculate_feature_usage(session, period_days=7)
        finance7 = await calculate_revenue_summary(session, period_days=7)
        feedback_sla = await FeedbackRepository(session).calculate_sla_metrics()
    text = (
        "🗓 Weekly Owner Summary\n\n"
        + format_beta_metrics_report(activation=activation, retention=retention, funnel=funnel, feature=feature)
        + "\n\n"
        + f"Finance 7d: {finance7['revenue_ton']:.2f} TON ({finance7['payments_count']} payments)\n"
        + f"Feedback overdue >48h: {feedback_sla['overdue_feedback_48h']}"
    )
    for admin_id in admin_ids:
        try:
            await bot.send_message(chat_id=admin_id, text=text)
        except Exception as exc:
            logger.exception("Weekly summary failed admin_id=%s: %s", admin_id, exc)


def setup_scheduler(bot: Bot, session_maker, settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.configure(timezone="UTC")
    scheduler.add_job(
        check_alert_rules_job,
        "interval",
        minutes=settings.check_interval_minutes,
        id="alerts_scan",
        kwargs={
            "bot": bot,
            "session_maker": session_maker,
            "settings": settings,
        },
    )
    scheduler.add_job(
        check_smart_alerts_job,
        "interval",
        minutes=settings.check_interval_minutes,
        id="smart_alerts_scan",
        kwargs={"bot": bot, "session_maker": session_maker, "settings": settings},
    )
    scheduler.add_job(
        send_digest_job,
        "interval",
        minutes=settings.smart_alert_default_cooldown_minutes,
        id="smart_alerts_digest",
        kwargs={"bot": bot, "session_maker": session_maker, "settings": settings},
    )
    scheduler.add_job(
        check_entitlements_job,
        "interval",
        minutes=settings.check_interval_minutes,
        id="entitlements_scan",
        kwargs={"bot": bot, "session_maker": session_maker, "settings": settings},
    )
    scheduler.add_job(
        expire_manual_payment_requests_job,
        "interval",
        minutes=settings.check_interval_minutes,
        id="manual_payment_expiry_scan",
        kwargs={"bot": bot, "session_maker": session_maker, "settings": settings},
    )
    scheduler.add_job(
        check_watchlist_signals_job,
        "interval",
        minutes=10,
        id="watchlist_notifications_scan",
        kwargs={"bot": bot, "session_maker": session_maker, "settings": settings},
    )
    if settings.owner_weekly_summary_enabled:
        day = (settings.owner_weekly_summary_day or "MON").lower()[:3]
        scheduler.add_job(
            send_owner_weekly_summary_job,
            "cron",
            day_of_week=day,
            hour=int(settings.owner_weekly_summary_hour),
            minute=0,
            id="owner_weekly_summary",
            kwargs={"bot": bot, "session_maker": session_maker, "settings": settings},
        )
    if settings.owner_accuracy_digest_enabled:
        dday = (settings.owner_accuracy_digest_day or "SUN").upper()[:3]
        scheduler.add_job(
            send_owner_accuracy_digest_job,
            "cron",
            day_of_week=dday.lower()[:3],
            hour=int(settings.owner_accuracy_digest_hour),
            minute=0,
            id="owner_accuracy_digest",
            kwargs={"bot": bot, "session_maker": session_maker, "settings": settings},
        )
    return scheduler
