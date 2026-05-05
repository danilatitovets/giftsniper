from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text

from app.config import get_settings
from app.bot.messages import BETA_SMOKE_PLAN_TEXT, BETA_USER_SCRIPT_TEXT
from app.db.models import FeedbackItem, SignalSnapshot, SmartAlertIncident
from app.db.repositories.alerts import AlertRepository
from app.db.repositories.beta_invites import BetaInviteRepository
from app.db.repositories.billing import BillingRepository
from app.db.repositories.feedback import FeedbackRepository
from app.db.repositories.gifts import GiftRepository
from app.db.repositories.manual_payments import ManualPaymentRepository
from app.db.repositories.payment_webhooks import PaymentWebhookRepository
from app.db.repositories.product_events import ProductEventRepository
from app.db.repositories.signal_snapshots import SignalSnapshotRepository
from app.db.repositories.trade_journal import TradeJournalRepository
from app.db.repositories.users import UserRepository
from app.db.session import SessionLocal
from app.bot.handlers.start import _render_home
from app.services import runtime_state
from app.services.audit import log_audit
from app.services.billing_providers.manual import ManualBillingProvider
from app.services.billing_webhooks import retry_webhook_event
from app.services.entitlements import (
    cancel_entitlement,
    format_entitlement_status,
    get_effective_entitlement,
    grant_entitlement,
    get_effective_entitlement,
    sync_user_plan_from_entitlement,
)
from app.services.feature_limits import get_plan_limits
from app.services.gift_intake import GiftIdentity, build_canonical_gift_key, normalize_gift_collection
from app.services.gift_resolver import enrich_identity_with_collection_registry, enrich_identity_with_tonapi
from app.services.financial_analytics import (
    calculate_arpu,
    calculate_mrr,
    calculate_revenue_summary,
    conversion_summary,
    format_financial_report,
    revenue_by_plan,
)
from app.services.accuracy_report import build_admin_accuracy_report
from app.services.backtesting import format_backtest_report, journal_rows_to_backtest_pairs, run_backtest
from app.services.calibration_dataset_builder import (
    build_scenarios_from_trade_journal,
    export_calibration_scenarios_json,
    format_dataset_builder_report,
)
from app.services.pricing_tuner import (
    analyze_pricing_accuracy,
    format_pricing_config_current,
    format_pricing_config_suggest,
    format_pricing_tuning_report,
)
from app.services.trade_import import (
    format_trade_import_preview,
    format_trade_import_result,
    import_trades_for_user,
    parse_trade_csv,
    validate_trade_row,
)
from app.services.market_cache import clear_market_cache, format_cache_status
from app.services.product_analytics import (
    calculate_activation_metrics,
    calculate_feature_usage,
    calculate_funnel_metrics,
    calculate_payment_ops_metrics,
    calculate_retention_metrics,
    format_beta_metrics_report,
)
from app.services.accuracy_digest import build_owner_accuracy_digest_text
from app.services.beta_dataset_workflow import (
    build_beta_dataset_summary,
    export_bad_signals_dataset,
    export_good_signals_dataset,
    export_reviewed_signals_dataset,
    format_beta_dataset_report,
)
from app.services.pricing_change_policy import evaluate_pricing_change_readiness, format_pricing_change_policy_report
from app.services.signal_accuracy_dashboard import build_admin_signal_accuracy_report
from app.services.signal_quality import (
    calculate_signal_good_bad_ratio,
    format_signal_quality_report,
    summarize_signal_feedback,
)
from app.services.signal_review import build_signal_review_queue, format_signal_review_item, format_signal_review_queue
from app.services.signal_snapshots import (
    format_signal_snapshot_detail,
    parse_signal_command_body,
)
from app.services.manual_payments import (
    confirm_payment_request,
    create_payment_request,
    list_payment_requests_by_status,
    list_stale_submitted_requests,
    format_payment_instructions,
    format_payment_request_admin,
    list_pending_payment_requests,
    search_payment_requests,
    list_user_payment_requests,
    reject_payment_request,
    submit_payment_proof,
)
from app.services.reconciliation import (
    find_confirmed_without_entitlement,
    find_entitlement_without_payment,
    find_expired_entitlement_with_active_plan,
    find_payment_event_mismatch,
    format_reconciliation_report,
)
from app.sources.factory import create_market_source, describe_sources
from app.services.beta_invite_readiness import build_beta_invite_readiness
from app.services.beta_launch_readiness import build_beta_launch_readiness_report, format_beta_launch_readiness_report
from app.services.payment_readiness import build_payment_readiness
from app.services.smoke_suite import build_smoke_suite_report, format_smoke_suite_report

router = Router()


def _is_admin(user, telegram_id: int) -> bool:
    settings = get_settings()
    env_admins = {int(x.strip()) for x in settings.admin_telegram_ids.split(",") if x.strip().isdigit()}
    return user.role in {"admin", "owner"} or telegram_id in env_admins


async def _require_admin(message: Message):
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
    if not _is_admin(user, message.from_user.id):
        await message.answer("Команда доступна только admin.")
        return None
    return user


def _parse_pipe(message_text: str, command: str) -> list[str]:
    payload = (message_text or "").removeprefix(command).strip()
    return [x.strip() for x in payload.split("|")]


def _flag_set(value: str) -> str:
    return "set" if bool(value) else "missing"


def _age_human(dt: datetime) -> str:
    base = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    mins = int((datetime.now(timezone.utc) - base).total_seconds() // 60)
    if mins < 60:
        return f"{mins}m"
    if mins < 1440:
        return f"{mins // 60}h"
    return f"{mins // 1440}d"


def _priority_valid(priority: str) -> bool:
    return priority in {"low", "normal", "high", "urgent"}


def _health_label(value: float, *, good: float, warning: float) -> str:
    if value >= good:
        return "good"
    if value >= warning:
        return "warning"
    return "bad"


def _status_rank(status: str) -> int:
    return {"GO": 0, "GO_WITH_WARNINGS": 1, "NO_GO": 2}.get(status, 2)


def _merge_status(current: str, incoming: str) -> str:
    return incoming if _status_rank(incoming) > _status_rank(current) else current


async def _owner_setup_snapshot(session, settings) -> dict:
    expected_owner_tg = 943071273
    users = UserRepository(session)
    billing = BillingRepository(session)
    owner = await users.get_by_telegram_id(expected_owner_tg)
    role = owner.role if owner is not None else "missing"
    plan = owner.plan if owner is not None else "n/a"
    entitlement = await billing.get_entitlement(owner.id) if owner is not None else None
    entitlement_text = f"{entitlement.status}/{entitlement.plan}" if entitlement is not None else "none"
    admin_ids = {int(x.strip()) for x in settings.admin_telegram_ids.split(",") if x.strip().isdigit()}
    warnings = []
    if owner is None:
        warnings.append("owner user not found")
    if owner is not None and owner.role != "owner":
        warnings.append(f"owner role is {owner.role}")
    if expected_owner_tg not in admin_ids:
        warnings.append("owner not in ADMIN_TELEGRAM_IDS")
    if not settings.owner_crypto_wallet_ton:
        warnings.append("OWNER_CRYPTO_WALLET_TON missing")
    return {
        "expected_owner_tg": expected_owner_tg,
        "owner_found": owner is not None,
        "role": role,
        "plan": plan,
        "entitlement": entitlement_text,
        "owner_in_admin_ids": expected_owner_tg in admin_ids,
        "wallet_configured": bool(settings.owner_crypto_wallet_ton),
        "billing_enabled": settings.billing_enabled,
        "billing_provider": settings.billing_provider,
        "beta_mode": settings.beta_mode,
        "warnings": warnings,
    }


async def _release_check_snapshot(session, settings) -> dict:
    status = "GO"
    checks: list[tuple[str, str, str]] = []
    try:
        await session.execute(text("SELECT 1"))
        checks.append(("DB connection", "ok", "connected"))
    except Exception as exc:
        checks.append(("DB connection", "block", f"failed: {exc}"))
        status = _merge_status(status, "NO_GO")
    current_revision = "n/a"
    head_revision = "n/a"
    try:
        rev = await session.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
        row = rev.first()
        current_revision = str(row[0]) if row else "n/a"
        cfg = Config("alembic.ini")
        head_revision = ScriptDirectory.from_config(cfg).get_current_head() or "n/a"
        checks.append(("Alembic revision", "ok", f"{current_revision}/{head_revision}"))
    except Exception as exc:
        checks.append(("Alembic revision", "warn", f"unavailable: {exc}"))
        status = _merge_status(status, "GO_WITH_WARNINGS")
    required_envs = [
        ("BOT_TOKEN", bool(settings.bot_token)),
        ("DATABASE_URL", bool(settings.database_url)),
        ("OWNER_CRYPTO_WALLET_TON", bool(settings.owner_crypto_wallet_ton)),
        ("ADMIN_TELEGRAM_IDS", bool(settings.admin_telegram_ids.strip())),
    ]
    for name, ok in required_envs:
        if ok:
            checks.append((name, "ok", "set"))
        else:
            checks.append((name, "block", "missing"))
            status = _merge_status(status, "NO_GO")
    if settings.tonapi_api_key.strip():
        checks.append(("TONAPI_API_KEY", "ok", "set"))
    else:
        checks.append(("TONAPI_API_KEY", "warn", "missing (optional for beta)"))
        status = _merge_status(status, "GO_WITH_WARNINGS")
    checks.append(("BETA_MODE", "ok", str(settings.beta_mode)))
    checks.append(("manual payments", "ok" if settings.manual_payment_enabled else "warn", f"enabled={settings.manual_payment_enabled}"))
    if not settings.manual_payment_enabled:
        status = _merge_status(status, "GO_WITH_WARNINGS")
    scheduler_ready = all(
        x is not None
        for x in [
            runtime_state.last_price_alert_check,
            runtime_state.last_smart_alert_check,
            runtime_state.last_digest_check,
        ]
    )
    checks.append(("scheduler runtime state", "ok" if scheduler_ready else "warn", "ready" if scheduler_ready else "n/a"))
    if not scheduler_ready:
        status = _merge_status(status, "GO_WITH_WARNINGS")
    if settings.beta_require_invite:
        active_invites = await BetaInviteRepository(session).count_active()
        if active_invites > 0:
            checks.append(("active invites", "ok", str(active_invites)))
        else:
            checks.append(("active invites", "block", "none while BETA_REQUIRE_INVITE=true"))
            status = _merge_status(status, "NO_GO")
    owner_snapshot = await _owner_setup_snapshot(session, settings)
    if owner_snapshot["warnings"]:
        checks.append(("owner setup", "block", ", ".join(owner_snapshot["warnings"])))
        status = _merge_status(status, "NO_GO")
    else:
        checks.append(("owner setup", "ok", "configured"))
    checks.append(("privacy/disclaimer", "ok", "commands available"))
    return {"status": status, "checks": checks, "current_revision": current_revision, "head_revision": head_revision}


async def _format_admin_payment_rows(session, rows, title: str) -> str:
    users = UserRepository(session)
    lines: list[str] = [title]
    for r in rows[:20]:
        u = await users.get_by_id(r.user_id)
        uname = f"@{u.username}" if (u and u.username) else "n/a"
        tg = str(u.telegram_id) if u else "n/a"
        proof_short = (r.tx_hash or r.proof_text or "n/a")
        if len(proof_short) > 36:
            proof_short = proof_short[:33] + "..."
        lines.append(
            f"#{r.id} user={tg}/{uname} plan={r.requested_plan} "
            f"amount={r.amount} {r.currency} status={r.status} age={_age_human(r.created_at)} "
            f"proof={proof_short} created={r.created_at}"
        )
    return "\n".join(lines)


def privacy_text() -> str:
    return (
        "🔐 Privacy\n"
        "- Храним: telegram id, username, gifts/watchlist, manual market data, alerts/incidents.\n"
        "- Также храним subscription status, entitlement state и billing/manual payment events (включая provider event ids).\n"
        "- Не храним данные банковских карт.\n"
        "- Не храним: seed phrase, private keys.\n"
        "- Бот не подключает wallet и не подписывает транзакции."
    )


def disclaimer_text() -> str:
    return (
        "⚠️ Disclaimer\n"
        "- Бот не является финансовым советником.\n"
        "- Подписка дает доступ к аналитическим функциям, но не гарантирует результат.\n"
        "- Прибыль не гарантируется.\n"
        "- Все сделки пользователь принимает самостоятельно.\n"
        "- NFT/crypto активы высокорисковые."
    )


@router.message(Command("pay"))
async def pay_handler(message: Message) -> None:
    plan = (message.text or "").removeprefix("/pay").strip().lower()
    if plan not in {"starter", "pro", "trader"}:
        await message.answer("Используйте: /pay <starter|pro|trader>")
        return
    settings = get_settings()
    if not settings.manual_payment_enabled:
        await message.answer("Manual payment сейчас отключен.")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        req = await create_payment_request(session, user.id, plan)
    await message.answer(format_payment_instructions(req, settings.owner_crypto_wallet_ton))


@router.message(Command("payment_sent"))
async def payment_sent_handler(message: Message) -> None:
    parts = _parse_pipe(message.text or "", "/payment_sent")
    if len(parts) < 2 or not parts[0].isdigit():
        await message.answer("Используйте: /payment_sent <request_id> | <tx_hash_or_note>")
        return
    request_id = int(parts[0])
    proof = parts[1]
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        try:
            row = await submit_payment_proof(session, user.id, request_id, proof)
        except ValueError as exc:
            await message.answer(str(exc))
            return
        if row is None:
            await message.answer("Заявка не найдена.")
            return
        await log_audit(
            session,
            user_id=user.id,
            action="manual_payment_submitted",
            entity_type="manual_payment_request",
            entity_id=str(row.id),
        )
    await message.answer("✅ Подтверждение оплаты отправлено. Ожидайте ручной проверки админом.")


@router.message(Command("my_payments"))
async def my_payments_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        rows = await list_user_payment_requests(session, user.id)
    if not rows:
        await message.answer("У вас пока нет payment requests. Используйте /pay pro или /pay trader.")
        return
    settings = get_settings()
    lines = []
    for r in rows[:10]:
        extra = ""
        if r.status == "submitted" and (datetime.now(timezone.utc) - (r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=timezone.utc))).total_seconds() >= settings.manual_payment_submitted_sla_hours * 3600:
            extra = " (ожидает ручной проверки)"
        if r.status == "rejected" and r.admin_note:
            extra = f" (reason: {r.admin_note[:120]})"
        lines.append(
            f"#{r.id} {r.requested_plan} {r.amount} {r.currency} status={r.status} age={_age_human(r.created_at)} "
            f"tx={r.tx_hash or 'n/a'} created={r.created_at}{extra}"
        )
    await message.answer("🧾 My payments\n" + "\n".join(lines))


@router.message(Command("payments"))
async def payments_alias_handler(message: Message) -> None:
    await my_payments_handler(message)


@router.message(Command("my_plan"))
async def my_plan_handler(message: Message) -> None:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        ent = await sync_user_plan_from_entitlement(session, user)
    limits = get_plan_limits(ent["plan"])
    features = [k for k, v in limits.items() if isinstance(v, bool) and v]
    await message.answer(
        "💳 My Plan\n"
        f"{format_entitlement_status(user, ent)}\n\n"
        f"Limits: gifts={limits.get('max_gifts')}, universe={limits.get('max_universe_collections')}\n"
        f"Features: {', '.join(sorted(features)) if features else 'none'}\n"
        f"{'⚠️ У вас grace period. Продлите план.' if ent['status']=='grace' else ''}"
    )


@router.message(Command("plan"))
async def plan_alias_handler(message: Message) -> None:
    await my_plan_handler(message)


@router.message(Command("redeem"))
async def redeem_handler(message: Message) -> None:
    parts = (message.text or "").split()
    async with SessionLocal() as session:
        users = UserRepository(session)
        user = await users.get_or_create(message.from_user.id, message.from_user.username)
        if len(parts) < 2:
            if _is_admin(user, message.from_user.id):
                await message.answer(
                    "Тебя закрытая бета не ограничивает (admin/owner/tester в БД или id в ADMIN_TELEGRAM_IDS).\n\n"
                    "Дальше по шагам:\n"
                    "1) Просто пользоваться ботом: /start или /home — команды уже доступны.\n"
                    "2) Промо-план (trader и т.д.) по коду — только если нужен план в биллинге:\n"
                    "   — создай: /admin_create_invite mycode | trader | 30 | 5\n"
                    "   — активируй у себя: /redeem mycode\n"
                    "   — проверь: /billing_status\n"
                    "3) Тестерам даёшь их код; они пишут: /redeem <код>\n\n"
                    "Список активных инвайтов: /admin_invites"
                )
            else:
                await message.answer("Используйте: /redeem <code>")
            return
        code = parts[1].strip().lower()
        invites = BetaInviteRepository(session)
        invite = await invites.get_by_code(code)
        if invite is None:
            await message.answer("Invite code не найден.")
            return
        ok, reason = await invites.can_redeem(invite, user.id)
        if not ok:
            await message.answer(reason or "Invite code недоступен.")
            return
        await invites.redeem(invite, user.id)
        expires = datetime.now(timezone.utc) + timedelta(days=invite.days)
        await grant_entitlement(session, user.id, invite.plan, "promo", expires, f"invite:{invite.code}")
        await BillingRepository(session).create_billing_event(
            user_id=user.id,
            event_type="promo_redeemed",
            provider="promo",
            plan=invite.plan,
            status="confirmed",
            metadata_json=f"code={invite.code}",
        )
        await log_audit(
            session,
            user_id=user.id,
            action="promo_redeemed",
            entity_type="beta_invite",
            entity_id=str(invite.id),
            metadata_json={"code": invite.code, "plan": invite.plan, "days": invite.days},
        )
        await sync_user_plan_from_entitlement(session, user)
        await message.answer(f"✅ Invite активирован. План {invite.plan} на {invite.days} дней.")


@router.message(Command("billing_status"))
async def billing_status_handler(message: Message) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        ent = await get_effective_entitlement(session, user)
        events = await BillingRepository(session).list_billing_events(user.id, limit=5)
        webhooks = [w for w in await PaymentWebhookRepository(session).list_recent_webhook_events(limit=20) if w.user_id == user.id][:5]
        payments = await list_user_payment_requests(session, user.id)
        mismatches = await find_confirmed_without_entitlement(session)
    events_text = "\n".join(f"- {e.created_at}: {e.event_type} ({e.status or 'n/a'})" for e in events) or "- none"
    webhooks_text = "\n".join(f"- {w.created_at}: {w.event_type or 'n/a'} [{w.status}]" for w in webhooks) or "- none"
    payments_text = "\n".join(
        f"- #{p.id} {p.requested_plan} {p.amount} {p.currency} ({p.status}) tx={p.tx_hash or 'n/a'}"
        for p in payments[:5]
    ) or "- none"
    pending_count = len([p for p in payments if p.status == "pending"])
    submitted_count = len([p for p in payments if p.status == "submitted"])
    confirmed = [p for p in payments if p.status == "confirmed"]
    last_confirmed = confirmed[0] if confirmed else None
    has_mismatch = any(p.user_id == user.id for p in mismatches)
    await message.answer(
        "🧾 Billing Status\n"
        f"Enabled: {settings.billing_enabled}\n"
        f"Provider: {settings.billing_provider}\n"
        f"Plan: {ent['plan']}\n"
        f"Status: {ent['status']}\n"
        f"Expires: {ent.get('expires_at') or 'n/a'}\n"
        f"Payment summary: pending={pending_count}, submitted={submitted_count}\n"
        f"Last confirmed payment: #{last_confirmed.id if last_confirmed else 'n/a'}\n"
        f"{'⚠️ Entitlement mismatch detected, contact admin.' if has_mismatch else ''}\n"
        f"Recent manual payment requests:\n{payments_text}\n"
        f"Recent billing events:\n{events_text}\n"
        f"Recent webhook events:\n{webhooks_text}"
    )


@router.message(Command("admin_user"))
async def admin_user_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Используйте: /admin_user <telegram_id>")
        return
    telegram_id = int(parts[1])
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        gift_repo = GiftRepository(session)
        alert_repo = AlertRepository(session)
        target = await user_repo.get_by_telegram_id(telegram_id)
        if target is None:
            await message.answer("Пользователь не найден.")
            return
        gifts_count = await gift_repo.count_by_user(target.id)
        alerts_count = await alert_repo.count_alert_rules(target.id)
        incidents_count = await alert_repo.count_incidents(target.id)
    await message.answer(
        f"👤 Admin user {telegram_id}\n"
        f"user id: {target.id}\n"
        f"role: {target.role}\n"
        f"plan: {target.plan}\n"
        f"plan expires: {target.plan_expires_at or 'n/a'}\n"
        f"blocked: {target.is_blocked}\n"
        f"gifts: {gifts_count}\n"
        f"alerts: {alerts_count}\n"
        f"incidents: {incidents_count}"
    )


@router.message(Command("admin_set_plan"))
async def admin_set_plan_handler(message: Message) -> None:
    actor = await _require_admin(message)
    if actor is None:
        return
    parts = _parse_pipe(message.text or "", "/admin_set_plan")
    if len(parts) < 2 or not parts[0].isdigit():
        await message.answer("Используйте: /admin_set_plan <telegram_id> | <plan> | <days optional>")
        return
    plan = parts[1].lower()
    if plan not in {"free", "starter", "pro", "trader"}:
        await message.answer("План должен быть free/starter/pro/trader.")
        return
    expires = None
    if len(parts) > 2 and parts[2].isdigit():
        expires = datetime.now(timezone.utc) + timedelta(days=int(parts[2]))
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        target = await user_repo.get_by_telegram_id(int(parts[0]))
        if target is None:
            await message.answer("Пользователь не найден.")
            return
        await user_repo.set_plan(target.id, plan, expires)
        await log_audit(
            session,
            user_id=actor.id,
            action="admin_set_plan",
            entity_type="user",
            entity_id=str(target.id),
            metadata_json={"plan": plan, "expires_at": str(expires)},
        )
    await message.answer("✅ План обновлен.")


@router.message(Command("admin_set_role"))
async def admin_set_role_handler(message: Message) -> None:
    actor = await _require_admin(message)
    if actor is None:
        return
    parts = _parse_pipe(message.text or "", "/admin_set_role")
    if len(parts) != 2 or not parts[0].isdigit():
        await message.answer("Используйте: /admin_set_role <telegram_id> | <role>")
        return
    role = parts[1].lower()
    if role not in {"user", "admin", "tester", "owner"}:
        await message.answer("Role должен быть user/admin/tester/owner.")
        return
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        target = await user_repo.get_by_telegram_id(int(parts[0]))
        if target is None:
            await message.answer("Пользователь не найден.")
            return
        await user_repo.set_role(target.id, role)
        await log_audit(
            session,
            user_id=actor.id,
            action="admin_set_role",
            entity_type="user",
            entity_id=str(target.id),
            metadata_json={"role": role},
        )
    await message.answer("✅ Роль обновлена.")


@router.message(Command("admin_block"))
async def admin_block_handler(message: Message) -> None:
    actor = await _require_admin(message)
    if actor is None:
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Используйте: /admin_block <telegram_id>")
        return
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        target = await user_repo.get_by_telegram_id(int(parts[1]))
        if target is None:
            await message.answer("Пользователь не найден.")
            return
        await user_repo.set_blocked(target.id, True)
        await log_audit(session, user_id=actor.id, action="admin_block", entity_type="user", entity_id=str(target.id))
    await message.answer("⛔ Пользователь заблокирован.")


@router.message(Command("admin_unblock"))
async def admin_unblock_handler(message: Message) -> None:
    actor = await _require_admin(message)
    if actor is None:
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Используйте: /admin_unblock <telegram_id>")
        return
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        target = await user_repo.get_by_telegram_id(int(parts[1]))
        if target is None:
            await message.answer("Пользователь не найден.")
            return
        await user_repo.set_blocked(target.id, False)
        await log_audit(session, user_id=actor.id, action="admin_unblock", entity_type="user", entity_id=str(target.id))
    await message.answer("✅ Пользователь разблокирован.")


@router.message(Command("admin_stats"))
async def admin_stats_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        alert_repo = AlertRepository(session)
        total_users = await user_repo.count_all()
        active_7d = await user_repo.count_recent_created(days=7)
        plans = await user_repo.plans_breakdown()
        alerts_count = await alert_repo.count_alert_rules()
        incidents_count = await alert_repo.count_incidents()
    plans_text = ", ".join(f"{k}:{v}" for k, v in sorted(plans.items())) or "n/a"
    await message.answer(
        f"📈 Admin stats\n"
        f"total users: {total_users}\n"
        f"active users last 7d: {active_7d}\n"
        f"plans: {plans_text}\n"
        f"alerts count: {alerts_count}\n"
        f"incidents count: {incidents_count}"
    )


@router.message(Command("admin_grant_plan"))
async def admin_grant_plan_handler(message: Message) -> None:
    actor = await _require_admin(message)
    if actor is None:
        return
    parts = _parse_pipe(message.text or "", "/admin_grant_plan")
    if len(parts) < 3 or not parts[0].isdigit() or not parts[2].isdigit():
        await message.answer("Используйте: /admin_grant_plan <telegram_id> | <plan> | <days> | <reason optional>")
        return
    plan = parts[1].lower()
    if plan not in {"free", "starter", "pro", "trader"}:
        await message.answer("План должен быть free/starter/pro/trader.")
        return
    days = int(parts[2])
    reason = parts[3] if len(parts) > 3 else None
    expires = datetime.now(timezone.utc) + timedelta(days=days)
    async with SessionLocal() as session:
        users = UserRepository(session)
        target = await users.get_by_telegram_id(int(parts[0]))
        if target is None:
            await message.answer("Пользователь не найден.")
            return
        await grant_entitlement(session, target.id, plan, "admin", expires, reason)
        await log_audit(
            session,
            user_id=actor.id,
            action="admin_grant_plan",
            entity_type="user",
            entity_id=str(target.id),
            metadata_json={"plan": plan, "days": days, "reason": reason},
        )
    await message.answer("✅ Entitlement выдан.")


@router.message(Command("admin_cancel_plan"))
async def admin_cancel_plan_handler(message: Message) -> None:
    actor = await _require_admin(message)
    if actor is None:
        return
    parts = _parse_pipe(message.text or "", "/admin_cancel_plan")
    if not parts or not parts[0].isdigit():
        await message.answer("Используйте: /admin_cancel_plan <telegram_id> | <reason optional>")
        return
    reason = parts[1] if len(parts) > 1 else None
    async with SessionLocal() as session:
        users = UserRepository(session)
        target = await users.get_by_telegram_id(int(parts[0]))
        if target is None:
            await message.answer("Пользователь не найден.")
            return
        await cancel_entitlement(session, target.id, reason)
        await log_audit(session, user_id=actor.id, action="admin_cancel_plan", entity_type="user", entity_id=str(target.id), metadata_json={"reason": reason})
    await message.answer("⏸ Plan canceled.")


@router.message(Command("admin_extend_plan"))
async def admin_extend_plan_handler(message: Message) -> None:
    actor = await _require_admin(message)
    if actor is None:
        return
    parts = _parse_pipe(message.text or "", "/admin_extend_plan")
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await message.answer("Используйте: /admin_extend_plan <telegram_id> | <days> | <reason optional>")
        return
    days = int(parts[1])
    reason = parts[2] if len(parts) > 2 else None
    async with SessionLocal() as session:
        users = UserRepository(session)
        billing = BillingRepository(session)
        target = await users.get_by_telegram_id(int(parts[0]))
        if target is None:
            await message.answer("Пользователь не найден.")
            return
        ent = await billing.get_entitlement(target.id)
        if ent is None:
            await message.answer("Entitlement не найден.")
            return
        ent.expires_at = (ent.expires_at or datetime.now(timezone.utc)) + timedelta(days=days)
        ent.status = "active"
        ent.grace_until = None
        await session.commit()
        await billing.create_billing_event(user_id=target.id, event_type="extended", provider=get_settings().billing_provider, plan=ent.plan, status="active", metadata_json=reason)
        await sync_user_plan_from_entitlement(session, target)
        await log_audit(session, user_id=actor.id, action="admin_extend_plan", entity_type="user", entity_id=str(target.id), metadata_json={"days": days, "reason": reason})
    await message.answer("✅ Plan extended.")


@router.message(Command("admin_billing_user"))
async def admin_billing_user_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Используйте: /admin_billing_user <telegram_id>")
        return
    async with SessionLocal() as session:
        users = UserRepository(session)
        billing = BillingRepository(session)
        target = await users.get_by_telegram_id(int(parts[1]))
        if target is None:
            await message.answer("Пользователь не найден.")
            return
        ent = await billing.get_entitlement(target.id)
        overrides = await billing.list_overrides(target.id, limit=5)
        events = await billing.list_billing_events(target.id, limit=5)
    o_text = "\n".join(f"- {o.plan} active={o.is_active} exp={o.expires_at}" for o in overrides) or "- none"
    e_text = "\n".join(f"- {e.created_at}: {e.event_type} {e.status or ''}" for e in events) or "- none"
    await message.answer(
        f"💳 Admin billing user {parts[1]}\n"
        f"user plan: {target.plan}\n"
        f"entitlement: {(ent.status + ' ' + ent.plan) if ent else 'none'}\n"
        f"overrides:\n{o_text}\n"
        f"billing events:\n{e_text}"
    )


@router.message(Command("admin_billing_events"))
async def admin_billing_events_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Используйте: /admin_billing_events <telegram_id>")
        return
    async with SessionLocal() as session:
        users = UserRepository(session)
        billing = BillingRepository(session)
        target = await users.get_by_telegram_id(int(parts[1]))
        if target is None:
            await message.answer("Пользователь не найден.")
            return
        events = await billing.list_billing_events(target.id, limit=20)
    text = "\n".join(f"- {e.created_at}: {e.event_type} plan={e.plan or 'n/a'} status={e.status or 'n/a'}" for e in events) or "- none"
    await message.answer("🧾 Billing events\n" + text)


@router.message(Command("admin_webhook_events"))
async def admin_webhook_events_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        events = await PaymentWebhookRepository(session).list_recent_webhook_events(limit=10)
    lines = []
    for e in events:
        short_err = (e.last_error or "")[:80]
        lines.append(
            f"#{e.id} {e.provider} {e.event_type or 'n/a'} status={e.status} "
            f"user={e.user_id or 'n/a'} plan={e.plan or 'n/a'} at {e.created_at} "
            f"{('err=' + short_err) if short_err else ''}"
        )
    await message.answer("🪝 Webhook events\n" + ("\n".join(lines) if lines else "- none"))


@router.message(Command("admin_retry_webhook"))
async def admin_retry_webhook_handler(message: Message) -> None:
    actor = await _require_admin(message)
    if actor is None:
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Используйте: /admin_retry_webhook <event_id>")
        return
    event_id = int(parts[1])
    async with SessionLocal() as session:
        result = await retry_webhook_event(session, event_id)
        await log_audit(
            session,
            user_id=actor.id,
            action="admin_retry_webhook",
            entity_type="payment_webhook_event",
            entity_id=str(event_id),
            metadata_json={"result": result.get("status")},
        )
    await message.answer(f"Retry result: {result.get('status')}")


@router.message(Command("admin_payments"))
async def admin_payments_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        rows = await list_pending_payment_requests(session)
    if not rows:
        await message.answer("Pending/submitted payment requests не найдены.")
        return
    async with SessionLocal() as session:
        text = await _format_admin_payment_rows(session, rows, "💰 Admin payments (pending/submitted)")
    await message.answer(text)


@router.message(Command("admin_payments_pending"))
async def admin_payments_pending_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        rows = await list_payment_requests_by_status(session, ["pending"])
        await message.answer(await _format_admin_payment_rows(session, rows, "💰 Pending requests"))


@router.message(Command("admin_payments_submitted"))
async def admin_payments_submitted_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        rows = await list_payment_requests_by_status(session, ["submitted"])
        await message.answer(await _format_admin_payment_rows(session, rows, "📥 Submitted requests"))


@router.message(Command("admin_payments_stale"))
async def admin_payments_stale_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        rows = await list_stale_submitted_requests(session)
        await message.answer(await _format_admin_payment_rows(session, rows, "⚠️ Stale submitted requests"))


@router.message(Command("admin_payments_confirmed"))
async def admin_payments_confirmed_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        rows = await list_payment_requests_by_status(session, ["confirmed"])
        await message.answer(await _format_admin_payment_rows(session, rows, "✅ Confirmed requests"))


@router.message(Command("admin_payments_rejected"))
async def admin_payments_rejected_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        rows = await list_payment_requests_by_status(session, ["rejected"])
        await message.answer(await _format_admin_payment_rows(session, rows, "⛔ Rejected requests"))


@router.message(Command("admin_payment_search"))
async def admin_payment_search_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    query = (message.text or "").removeprefix("/admin_payment_search").strip()
    if not query:
        await message.answer("Используйте: /admin_payment_search <query>")
        return
    async with SessionLocal() as session:
        rows = await search_payment_requests(session, query)
        users = await UserRepository(session).list_all()
        user_matches = []
        q = query.lower()
        for u in users:
            if q in str(u.telegram_id) or (u.username and q in u.username.lower()):
                user_matches.append(u.id)
        if user_matches:
            extra = await list_payment_requests_by_status(
                session,
                ["pending", "submitted", "confirmed", "rejected", "expired"],
                limit=200,
            )
            rows_by_id = {r.id: r for r in rows}
            for r in extra:
                if r.user_id in user_matches:
                    rows_by_id[r.id] = r
            rows = list(rows_by_id.values())
        await message.answer(await _format_admin_payment_rows(session, rows, f"🔎 Payment search: {query}"))


@router.message(Command("admin_payment"))
async def admin_payment_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Используйте: /admin_payment <id>")
        return
    async with SessionLocal() as session:
        row = await ManualPaymentRepository(session).get_by_id(int(parts[1]))
    if row is None:
        await message.answer("Payment request не найден.")
        return
    tx_short = (row.tx_hash[:8] + "..." + row.tx_hash[-6:]) if row.tx_hash and len(row.tx_hash) > 18 else (row.tx_hash or "n/a")
    stale_flag = ""
    if row.status == "submitted":
        created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - created).total_seconds() >= get_settings().manual_payment_submitted_sla_hours * 3600:
            stale_flag = "\n⚠️ Stale submitted payment."
    status_warning = ""
    if row.status in {"confirmed", "rejected"}:
        status_warning = f"\n⚠️ Request already {row.status}."
    await message.answer(
        "💳 Payment details\n"
        + format_payment_request_admin(row)
        + f"\nshort tx: {tx_short}"
        + stale_flag
        + status_warning
        + f"\n\nAction hints:\n/admin_confirm_payment {row.id} | 30 | paid in TON\n/admin_reject_payment {row.id} | reason"
    )


@router.message(Command("admin_confirm_payment"))
async def admin_confirm_payment_handler(message: Message) -> None:
    actor = await _require_admin(message)
    if actor is None:
        return
    parts = _parse_pipe(message.text or "", "/admin_confirm_payment")
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await message.answer("Используйте: /admin_confirm_payment <id> | <days> | <note optional>")
        return
    request_id = int(parts[0])
    days = int(parts[1])
    note = parts[2] if len(parts) > 2 else None
    user_telegram_id = None
    async with SessionLocal() as session:
        row = await confirm_payment_request(session, actor.id, request_id, days, note)
        if row is None:
            await message.answer("Payment request не найден.")
            return
        target = await UserRepository(session).get_by_id(row.user_id)
        user_telegram_id = target.telegram_id if target else None
    if user_telegram_id:
        await message.bot.send_message(chat_id=user_telegram_id, text="✅ Ваш платеж подтвержден. План активирован.")
    await message.answer("✅ Payment confirmed. Entitlement выдан.")


@router.message(Command("admin_reject_payment"))
async def admin_reject_payment_handler(message: Message) -> None:
    actor = await _require_admin(message)
    if actor is None:
        return
    parts = _parse_pipe(message.text or "", "/admin_reject_payment")
    if len(parts) < 2 or not parts[0].isdigit():
        await message.answer("Используйте: /admin_reject_payment <id> | <reason>")
        return
    request_id = int(parts[0])
    reason = parts[1]
    user_telegram_id = None
    async with SessionLocal() as session:
        row = await reject_payment_request(session, actor.id, request_id, reason)
        if row is None:
            await message.answer("Payment request не найден.")
            return
        target = await UserRepository(session).get_by_id(row.user_id)
        user_telegram_id = target.telegram_id if target else None
    if user_telegram_id:
        await message.bot.send_message(chat_id=user_telegram_id, text=f"⛔ Платеж отклонен: {reason}")
    await message.answer("⛔ Payment rejected.")


@router.message(Command("admin_finance"))
async def admin_finance_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        revenue = await calculate_revenue_summary(session, period_days=30)
        mrr = await calculate_mrr(session)
        arpu = await calculate_arpu(session, period_days=30)
        by_plan = await revenue_by_plan(session, period_days=30)
        conversion = await conversion_summary(session, period_days=30)
    await message.answer(
        format_financial_report(
            revenue_summary=revenue,
            mrr=mrr,
            arpu=arpu,
            by_plan=by_plan,
            conversion=conversion,
        )
    )


@router.message(Command("admin_reconcile"))
async def admin_reconcile_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        cwe = await find_confirmed_without_entitlement(session)
        ewp = await find_entitlement_without_payment(session)
        pem = await find_payment_event_mismatch(session)
        eap = await find_expired_entitlement_with_active_plan(session)
    await message.answer(
        format_reconciliation_report(
            confirmed_without_entitlement=cwe,
            entitlement_without_payment=ewp,
            payment_event_mismatch=pem,
            expired_with_active_plan=eap,
        )
    )


@router.message(Command("admin_repair_user_gifts"))
async def admin_repair_user_gifts_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Используйте: /admin_repair_user_gifts <telegram_id>")
        return
    telegram_id = int(parts[1])
    settings = get_settings()
    fixed = enriched = 0
    async with SessionLocal() as session:
        user = await UserRepository(session).get_by_telegram_id(telegram_id)
        if user is None:
            await message.answer("Пользователь не найден.")
            return
        gift_repo = GiftRepository(session)
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
                    collection=gift.collection,
                    number=gift.number,
                    nft_address=gift.nft_address,
                    normalized_collection=norm,
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
    dup_lines = "\n".join(f"- {k}: {v}" for k, v in list(dups.items())[:8]) if dups else "нет"
    await message.answer(
        f"🔧 Admin repair gifts for tg={telegram_id}\n"
        f"Обновлено полей: {fixed}\nTonAPI enrich: {enriched}\nДубли:\n{dup_lines}"
    )


@router.message(Command("feedback"))
async def feedback_handler(message: Message) -> None:
    text = (message.text or "").removeprefix("/feedback").strip()
    if not text:
        await message.answer("Используйте: /feedback <text>")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        item = await FeedbackRepository(session).create_item(user_id=user.id, item_type="feedback", message=text)
    await message.answer(f"✅ Спасибо! Feedback #{item.id} получен.")


@router.message(Command("bug"))
async def bug_handler(message: Message) -> None:
    text = (message.text or "").removeprefix("/bug").strip()
    if not text:
        await message.answer("Используйте: /bug <text>")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        item = await FeedbackRepository(session).create_item(user_id=user.id, item_type="bug", message=text)
    await message.answer(f"🐞 Bug report #{item.id} сохранен. Спасибо!")


@router.message(Command("feature"))
async def feature_handler(message: Message) -> None:
    text = (message.text or "").removeprefix("/feature").strip()
    if not text:
        await message.answer("Используйте: /feature <text>")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        item = await FeedbackRepository(session).create_item(user_id=user.id, item_type="feature", message=text)
    await message.answer(f"✨ Feature request #{item.id} сохранен.")


@router.message(Command("deal_case"))
async def deal_case_handler(message: Message) -> None:
    text = (message.text or "").removeprefix("/deal_case").strip()
    if not text:
        await message.answer("Используйте: /deal_case <text>")
        return
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        item = await FeedbackRepository(session).create_item(user_id=user.id, item_type="deal_case", message=text)
    await message.answer(f"📌 Deal case #{item.id} принят.")


@router.message(Command("signal_good"))
async def signal_good_handler(message: Message) -> None:
    sid, note, legacy = parse_signal_command_body(message.text or "", "/signal_good")
    msg = note or legacy or "signal was useful"
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        snap_id = None
        rating = None
        if sid is not None:
            snap = await SignalSnapshotRepository(session).get_for_user(sid, user.id)
            if snap:
                snap_id = snap.id
                rating = "good"
                msg = note or "good"
            else:
                msg = note or f"unlinked signal id {sid}"
        item = await FeedbackRepository(session).create_item(
            user_id=user.id,
            item_type="signal_good",
            message=msg,
            signal_snapshot_id=snap_id,
            signal_rating=rating,
            reviewer_note=note,
        )
        await ProductEventRepository(session).create_event(
            user_id=user.id,
            event_type="feedback_created",
            command="/signal_good",
            metadata_json=f"type=signal_good,snapshot={snap_id}",
        )
    extra = f" (linked #{snap_id})" if snap_id else ""
    await message.answer(f"✅ Signal feedback #{item.id} сохранен.{extra}")


@router.message(Command("signal_bad"))
async def signal_bad_handler(message: Message) -> None:
    sid, note, legacy = parse_signal_command_body(message.text or "", "/signal_bad")
    msg = note or legacy or "signal was bad"
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        snap_id = None
        rating = None
        if sid is not None:
            snap = await SignalSnapshotRepository(session).get_for_user(sid, user.id)
            if snap:
                snap_id = snap.id
                rating = "bad"
                msg = note or "bad"
            else:
                msg = note or f"unlinked signal id {sid}"
        item = await FeedbackRepository(session).create_item(
            user_id=user.id,
            item_type="signal_bad",
            message=msg,
            signal_snapshot_id=snap_id,
            signal_rating=rating,
            reviewer_note=note,
        )
        await ProductEventRepository(session).create_event(
            user_id=user.id,
            event_type="feedback_created",
            command="/signal_bad",
            metadata_json=f"type=signal_bad,snapshot={snap_id}",
        )
    extra = f" (linked #{snap_id})" if snap_id else ""
    await message.answer(f"✅ Signal feedback #{item.id} сохранен.{extra}")


@router.message(Command("signal_unclear"))
async def signal_unclear_handler(message: Message) -> None:
    sid, note, legacy = parse_signal_command_body(message.text or "", "/signal_unclear")
    msg = note or legacy or "unclear signal"
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        snap_id = None
        rating = None
        if sid is not None:
            snap = await SignalSnapshotRepository(session).get_for_user(sid, user.id)
            if snap:
                snap_id = snap.id
                rating = "unclear"
                msg = note or "unclear"
            else:
                msg = note or f"unlinked signal id {sid}"
        item = await FeedbackRepository(session).create_item(
            user_id=user.id,
            item_type="signal_unclear",
            message=msg,
            signal_snapshot_id=snap_id,
            signal_rating=rating,
            reviewer_note=note,
        )
        await ProductEventRepository(session).create_event(
            user_id=user.id,
            event_type="feedback_created",
            command="/signal_unclear",
            metadata_json=f"type=signal_unclear,snapshot={snap_id}",
        )
    extra = f" (linked #{snap_id})" if snap_id else ""
    await message.answer(f"✅ Signal feedback #{item.id} сохранен.{extra}")


@router.message(Command("signal_outcome"))
async def signal_outcome_handler(message: Message) -> None:
    parts = _parse_pipe(message.text or "", "/signal_outcome")
    if len(parts) < 2 or not parts[0].isdigit():
        await message.answer("Используйте: /signal_outcome <signal_id> | bought|skipped|missed|sold|bad_price|no_liquidity | заметка")
        return
    sid = int(parts[0])
    hint = parts[1].strip().lower()
    allowed = {"bought", "skipped", "missed", "sold", "bad_price", "no_liquidity"}
    if hint not in allowed:
        await message.answer(f"outcome должен быть одним из: {', '.join(sorted(allowed))}")
        return
    note = parts[2] if len(parts) > 2 else None
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        snap = await SignalSnapshotRepository(session).get_for_user(sid, user.id)
        if snap is None:
            await message.answer("Signal ID не найден для этого пользователя.")
            return
        item = await FeedbackRepository(session).create_item(
            user_id=user.id,
            item_type="signal_outcome",
            message=note or f"outcome={hint}",
            signal_snapshot_id=snap.id,
            signal_rating="neutral",
            outcome_hint=hint,
            reviewer_note=note,
        )
    await message.answer(f"✅ Outcome #{item.id} сохранен для Signal #{sid}.")


@router.message(Command("admin_create_invite"))
async def admin_create_invite_handler(message: Message) -> None:
    actor = await _require_admin(message)
    if actor is None:
        return
    parts = _parse_pipe(message.text or "", "/admin_create_invite")
    if len(parts) < 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await message.answer("Используйте: /admin_create_invite <code> | <plan> | <days> | <max_uses>")
        return
    code = parts[0].lower()
    plan = parts[1].lower()
    days = int(parts[2])
    max_uses = int(parts[3])
    async with SessionLocal() as session:
        repo = BetaInviteRepository(session)
        exists = await repo.get_by_code(code)
        if exists is not None:
            await message.answer("Такой invite code уже существует.")
            return
        invite = await repo.create_invite(code=code, plan=plan, days=days, max_uses=max_uses, created_by_user_id=actor.id)
        await log_audit(
            session,
            user_id=actor.id,
            action="admin_create_invite",
            entity_type="beta_invite",
            entity_id=str(invite.id),
            metadata_json={"code": code, "plan": plan, "days": days, "max_uses": max_uses},
        )
    await message.answer(f"✅ Invite создан: {invite.code} ({invite.plan}, {invite.days}d, max={invite.max_uses})")


@router.message(Command("admin_invites"))
async def admin_invites_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        rows = await BetaInviteRepository(session).list_active(limit=100)
    if not rows:
        await message.answer("Активных invite codes нет.")
        return
    lines = [f"- {x.code} plan={x.plan} days={x.days} used={x.used_count}/{x.max_uses} exp={x.expires_at or 'n/a'}" for x in rows]
    await message.answer("🎟 Active invite codes\n" + "\n".join(lines))


@router.message(Command("admin_disable_invite"))
async def admin_disable_invite_handler(message: Message) -> None:
    actor = await _require_admin(message)
    if actor is None:
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Используйте: /admin_disable_invite <code>")
        return
    code = parts[1].lower().strip()
    async with SessionLocal() as session:
        ok = await BetaInviteRepository(session).disable_invite(code)
        if not ok:
            await message.answer("Invite code не найден.")
            return
        await log_audit(session, user_id=actor.id, action="admin_disable_invite", entity_type="beta_invite", entity_id=code)
    await message.answer("⛔ Invite code отключен.")


@router.message(Command("admin_feedback"))
async def admin_feedback_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    parts = (message.text or "").split()
    async with SessionLocal() as session:
        repo = FeedbackRepository(session)
        if len(parts) > 1 and parts[1].isdigit():
            row = await repo.get_by_id(int(parts[1]))
            if row is None:
                await message.answer("Feedback item не найден.")
                return
            await message.answer(
                f"#{row.id} [{row.type}] status={row.status}\n"
                f"user_id={row.user_id}\n"
                f"message={row.message}\n"
                f"admin_note={row.admin_note or 'n/a'}"
            )
            return
        rows = await repo.list_items(limit=30)
    lines = [f"#{x.id} [{x.type}] status={x.status} user={x.user_id} created={x.created_at}" for x in rows]
    await message.answer("🗂 Feedback queue\n" + ("\n".join(lines) if lines else "- none"))


@router.message(Command("admin_feedback_close"))
async def admin_feedback_close_handler(message: Message) -> None:
    actor = await _require_admin(message)
    if actor is None:
        return
    parts = _parse_pipe(message.text or "", "/admin_feedback_close")
    if not parts or not parts[0].isdigit():
        await message.answer("Используйте: /admin_feedback_close <id> | <note optional>")
        return
    note = parts[1] if len(parts) > 1 else None
    async with SessionLocal() as session:
        row = await FeedbackRepository(session).close_item(int(parts[0]), note)
        if row is None:
            await message.answer("Feedback item не найден.")
            return
        await log_audit(
            session,
            user_id=actor.id,
            action="admin_feedback_close",
            entity_type="feedback_item",
            entity_id=str(row.id),
            metadata_json={"note": note},
        )
    await message.answer("✅ Feedback item закрыт.")


@router.message(Command("admin_feedback_review"))
async def admin_feedback_review_handler(message: Message) -> None:
    actor = await _require_admin(message)
    if actor is None:
        return
    parts = _parse_pipe(message.text or "", "/admin_feedback_review")
    if not parts or not parts[0].isdigit():
        await message.answer("Используйте: /admin_feedback_review <id> | <priority optional> | <note optional>")
        return
    item_id = int(parts[0])
    priority = parts[1].lower() if len(parts) > 1 and parts[1] else None
    note = parts[2] if len(parts) > 2 else None
    if priority and not _priority_valid(priority):
        await message.answer("Priority должен быть low|normal|high|urgent.")
        return
    async with SessionLocal() as session:
        row = await FeedbackRepository(session).review_item(item_id, reviewer_user_id=actor.id, priority=priority, note=note)
        if row is None:
            await message.answer("Feedback item не найден.")
            return
    await message.answer(f"✅ Feedback #{row.id} отмечен как reviewed (priority={row.priority}).")


@router.message(Command("admin_feedback_priority"))
async def admin_feedback_priority_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    parts = _parse_pipe(message.text or "", "/admin_feedback_priority")
    if len(parts) < 2 or not parts[0].isdigit():
        await message.answer("Используйте: /admin_feedback_priority <id> | <low|normal|high|urgent>")
        return
    priority = parts[1].lower()
    if not _priority_valid(priority):
        await message.answer("Priority должен быть low|normal|high|urgent.")
        return
    async with SessionLocal() as session:
        row = await FeedbackRepository(session).set_priority(int(parts[0]), priority)
        if row is None:
            await message.answer("Feedback item не найден.")
            return
    await message.answer(f"✅ Priority обновлен: #{row.id} -> {row.priority}")


@router.message(Command("admin_feedback_sla"))
async def admin_feedback_sla_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        metrics = await FeedbackRepository(session).calculate_sla_metrics()
    await message.answer(
        "🧭 Feedback SLA\n"
        f"New feedback count: {metrics['new_feedback_count']}\n"
        f"Urgent/high count: {metrics['urgent_high_count']}\n"
        f"Oldest new feedback age: {metrics['oldest_new_feedback_age']}\n"
        f"Average close time: {metrics['average_close_time_hours']:.1f}h\n"
        f"Overdue feedback >48h: {metrics['overdue_feedback_48h']}"
    )


@router.message(Command("admin_signal_feedback"))
async def admin_signal_feedback_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        repo = FeedbackRepository(session)
        users = UserRepository(session)
        rows = await repo.list_signal_feedback(limit=20)
        lines = []
        for row in rows:
            user = await users.get_by_id(row.user_id)
            uname = f"@{user.username}" if user and user.username else f"id:{row.user_id}"
            sig_type = "good" if row.type == "signal_good" else "bad" if row.type == "signal_bad" else row.type
            snap_part = f" snap#{row.signal_snapshot_id}" if row.signal_snapshot_id else ""
            lines.append(f"- {uname} | {sig_type}{snap_part} | {row.message[:100]} | {row.created_at}")
    await message.answer("📣 Signal feedback\n" + ("\n".join(lines) if lines else "- none"))


@router.message(Command("admin_signal_queue"))
async def admin_signal_queue_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        items = await build_signal_review_queue(session, limit=25)
    await message.answer(format_signal_review_queue(items))


@router.message(Command("admin_signal"))
async def admin_signal_detail_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Используйте: /admin_signal <signal_id>")
        return
    async with SessionLocal() as session:
        snap = await SignalSnapshotRepository(session).get_by_id(int(parts[1]))
    if snap is None:
        await message.answer("Не найдено.")
        return
    await message.answer(format_signal_snapshot_detail(snap))


@router.message(Command("admin_signal_mark"))
async def admin_signal_mark_handler(message: Message) -> None:
    actor = await _require_admin(message)
    if actor is None:
        return
    parts = _parse_pipe(message.text or "", "/admin_signal_mark")
    if len(parts) < 2 or not parts[0].isdigit():
        await message.answer("Используйте: /admin_signal_mark <signal_id> | good|bad|unclear|false_positive | заметка")
        return
    sid = int(parts[0])
    rating = parts[1].strip().lower()
    allowed = {"good", "bad", "unclear", "false_positive"}
    if rating not in allowed:
        await message.answer(f"rating: {', '.join(sorted(allowed))}")
        return
    note = parts[2] if len(parts) > 2 else None
    async with SessionLocal() as session:
        snap = await SignalSnapshotRepository(session).get_by_id(sid)
        if snap is None:
            await message.answer("Signal не найден.")
            return
        eff_rating = "bad" if rating == "false_positive" else rating
        rn = note or ("false_positive" if rating == "false_positive" else None)
        await FeedbackRepository(session).create_item(
            user_id=actor.id,
            item_type="admin_signal_review",
            message=f"admin_mark={rating}",
            signal_snapshot_id=snap.id,
            signal_rating=eff_rating,
            reviewer_note=rn,
        )
    await message.answer(f"✅ Отмечен signal #{sid} как {rating}.")


@router.message(Command("admin_signal_note"))
async def admin_signal_note_handler(message: Message) -> None:
    actor = await _require_admin(message)
    if actor is None:
        return
    parts = _parse_pipe(message.text or "", "/admin_signal_note")
    if len(parts) < 2 or not parts[0].isdigit():
        await message.answer("Используйте: /admin_signal_note <signal_id> | текст")
        return
    sid = int(parts[0])
    note = parts[1]
    async with SessionLocal() as session:
        snap = await SignalSnapshotRepository(session).get_by_id(sid)
        if snap is None:
            await message.answer("Signal не найден.")
            return
        await FeedbackRepository(session).create_item(
            user_id=actor.id,
            item_type="admin_signal_review",
            message="admin_note",
            signal_snapshot_id=snap.id,
            reviewer_note=note,
        )
    await message.answer(f"✅ Заметка к signal #{sid} сохранена.")


@router.message(Command("admin_signal_outcomes"))
async def admin_signal_outcomes_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        rows = await FeedbackRepository(session).list_outcome_feedback(limit=30)
    if not rows:
        await message.answer("Нет signal_outcome записей.")
        return
    lines = [f"- #{r.id} snap#{r.signal_snapshot_id} {r.outcome_hint} | {r.message[:80]}" for r in rows]
    await message.answer("📌 Signal outcomes\n" + "\n".join(lines))


@router.message(Command("admin_signal_accuracy"))
async def admin_signal_accuracy_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        text = await build_admin_signal_accuracy_report(session, days=7)
    await message.answer(text[:3900])


@router.message(Command("admin_dataset_status"))
async def admin_dataset_status_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        s = await build_beta_dataset_summary(session)
    await message.answer(format_beta_dataset_report(s))


@router.message(Command("admin_export_bad_signals"))
async def admin_export_bad_signals_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        jsonl, csv_path = await export_bad_signals_dataset(session)
        s = await build_beta_dataset_summary(session)
    await message.answer(format_beta_dataset_report(s, jsonl_path=jsonl) + f"\nCSV: {csv_path}")


@router.message(Command("admin_export_good_signals"))
async def admin_export_good_signals_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        jsonl, csv_path = await export_good_signals_dataset(session)
        s = await build_beta_dataset_summary(session)
    await message.answer(format_beta_dataset_report(s, jsonl_path=jsonl) + f"\nCSV: {csv_path}")


@router.message(Command("admin_export_reviewed_signals"))
async def admin_export_reviewed_signals_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        jsonl, csv_path = await export_reviewed_signals_dataset(session)
        s = await build_beta_dataset_summary(session)
    await message.answer(format_beta_dataset_report(s, jsonl_path=jsonl) + f"\nCSV: {csv_path}")


@router.message(Command("admin_accuracy_digest_now"))
async def admin_accuracy_digest_now_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    settings = get_settings()
    async with SessionLocal() as session:
        text = await build_owner_accuracy_digest_text(session, settings)
    chunk = 3800
    for i in range(0, len(text), chunk):
        await message.answer(text[i : i + chunk])


@router.message(Command("admin_pricing_change_policy"))
async def admin_pricing_change_policy_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    settings = get_settings()
    async with SessionLocal() as session:
        data = await evaluate_pricing_change_readiness(session, settings)
    await message.answer(format_pricing_change_policy_report(data)[:3900])


@router.message(Command("admin_beta_metrics"))
async def admin_beta_metrics_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        activation = await calculate_activation_metrics(session, period_days=7)
        retention = await calculate_retention_metrics(session, period_days=7)
        funnel = await calculate_funnel_metrics(session, period_days=7)
        feature = await calculate_feature_usage(session, period_days=7)
    await message.answer(format_beta_metrics_report(activation=activation, retention=retention, funnel=funnel, feature=feature))


@router.message(Command("admin_beta_status"))
async def admin_beta_status_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    settings = get_settings()
    async with SessionLocal() as session:
        users_repo = UserRepository(session)
        invites_repo = BetaInviteRepository(session)
        feedback_repo = FeedbackRepository(session)
        payments_repo = ManualPaymentRepository(session)
        total_users = await users_repo.count_all()
        active_invites = await invites_repo.count_active()
        redeemed = await invites_repo.count_redemptions()
        plans = await users_repo.plans_breakdown()
        feedback_new = await feedback_repo.count_new()
        submitted = await payments_repo.list_by_status(["submitted"], limit=200)
        stale = await list_stale_submitted_requests(session)
    warnings = []
    if stale:
        warnings.append(f"stale submitted payments={len(stale)}")
    if feedback_new > 20:
        warnings.append(f"feedback backlog={feedback_new}")
    if active_invites == 0:
        warnings.append("no active invites")
    await message.answer(
        "🧪 Beta Status\n"
        f"total users: {total_users}\n"
        f"beta invites active: {active_invites}\n"
        f"invites redeemed: {redeemed}\n"
        f"pro/trader users: {plans.get('pro', 0) + plans.get('trader', 0)}\n"
        f"feedback new: {feedback_new}\n"
        f"manual payments submitted/stale: {len(submitted)}/{len(stale)}\n"
        f"top warnings: {', '.join(warnings) if warnings else 'none'}\n"
        f"SLA hours: {settings.manual_payment_submitted_sla_hours}"
    )


@router.message(Command("admin_weekly_summary"))
async def admin_weekly_summary_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        activation = await calculate_activation_metrics(session, period_days=7)
        retention = await calculate_retention_metrics(session, period_days=7)
        funnel = await calculate_funnel_metrics(session, period_days=7)
        feature = await calculate_feature_usage(session, period_days=7)
        finance7 = await calculate_revenue_summary(session, period_days=7)
        finance30 = await calculate_revenue_summary(session, period_days=30)
        stale = await list_stale_submitted_requests(session)
        feedback_sla = await FeedbackRepository(session).calculate_sla_metrics()
        open_incidents = await AlertRepository(session).count_incidents()
    warnings: list[str] = []
    if activation["activation_rate"] < 0.3:
        warnings.append("activation rate below 30%")
    if len(stale) > 0:
        warnings.append(f"stale submitted payments: {len(stale)}")
    if feedback_sla["overdue_feedback_48h"] > 0:
        warnings.append(f"feedback overdue >48h: {feedback_sla['overdue_feedback_48h']}")
    await message.answer(
        "🗓 Owner Weekly Summary\n\n"
        + format_beta_metrics_report(activation=activation, retention=retention, funnel=funnel, feature=feature)
        + "\n\n💰 Finance summary\n"
        f"7d: {finance7['revenue_ton']:.2f} TON ({finance7['payments_count']} payments)\n"
        f"30d: {finance30['revenue_ton']:.2f} TON ({finance30['payments_count']} payments)\n\n"
        "⚙️ Ops\n"
        f"Manual payment queue (stale): {len(stale)}\n"
        f"Feedback SLA overdue: {feedback_sla['overdue_feedback_48h']}\n"
        f"Incident summary (open): {open_incidents}\n"
        f"Top bugs/features: feedback new={feedback_sla['new_feedback_count']}\n"
        f"Product warnings: {', '.join(warnings) if warnings else 'none'}"
    )


@router.message(Command("admin_beta_checklist"))
async def admin_beta_checklist_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    settings = get_settings()
    async with SessionLocal() as session:
        owner_snap = await _owner_setup_snapshot(session, settings)
        users_repo = UserRepository(session)
        total_users = await users_repo.count_all()
        activation = await calculate_activation_metrics(session, period_days=7)
        feedback_sla = await FeedbackRepository(session).calculate_sla_metrics()
        payment_ops = await calculate_payment_ops_metrics(session, period_days=7)
        try:
            active_invites = await BetaInviteRepository(session).count_active()
        except Exception:
            active_invites = 0
        open_incidents = int(
            await session.scalar(select(func.count(SmartAlertIncident.id)).where(SmartAlertIncident.status == "open"))
            or 0
        )
        g7, b7, _u7 = await SignalSnapshotRepository(session).count_linked_bad_good_signals(7)
        bad_rate_7d = b7 / max(g7 + b7, 1)
        stale_n = int(payment_ops.get("stale_submitted_48h", 0) or 0)
        digest_at = runtime_state.last_accuracy_digest_check
        inv_rd = await build_beta_invite_readiness(session, settings)
        pay_rd = await build_payment_readiness(session, settings)
    owner_ok = owner_snap["owner_found"] and owner_snap["role"] == "owner" and not owner_snap["warnings"]
    admin_cfg = "configured" if settings.admin_telegram_ids.strip() else "empty"
    digest_line = "ещё не отправлялся (scheduler)"
    if digest_at is not None:
        digest_line = f"{_age_human(digest_at)} назад"
    recs: list[str] = []
    if owner_snap["warnings"]:
        recs.append("Проверь owner и кошелёк: /owner_setup_check")
    if not settings.admin_telegram_ids.strip():
        recs.append("Заполни ADMIN_TELEGRAM_IDS в .env")
    if settings.beta_require_invite and active_invites == 0:
        recs.append("Нет активных инвайтов при включённом gate — /admin_invites")
    if stale_n > 0:
        recs.append(f"Застрявшие оплаты (48h+): {stale_n} — /admin_payments_stale")
    if feedback_sla["new_feedback_count"] > 10:
        recs.append("Много нового feedback — /admin_feedback")
    if open_incidents > 15:
        recs.append("Много открытых инцидентов — smart alerts / расследование")
    if bad_rate_7d > 0.45 and (g7 + b7) >= 8:
        recs.append("Высокий bad signal rate 7d — /admin_signal_queue")
    if not recs:
        recs.append("Онлайн-сводка: /admin_beta_health; отчёт: /admin_weekly_summary")
    body = (
        "✅ Admin beta checklist\n\n"
        f"Owner: {'ok' if owner_ok else 'нужна настройка'} (expected tg {owner_snap['expected_owner_tg']})\n"
        f"ADMIN_TELEGRAM_IDS: {admin_cfg}\n"
        f"Beta mode: {settings.beta_mode}, require_invite: {settings.beta_require_invite}\n"
        f"Active invites: {active_invites}\n"
        f"Users total: {total_users}\n"
        f"Active 7d (distinct users, product events): {activation['active_users']}\n"
        f"Feedback new: {feedback_sla['new_feedback_count']}\n"
        f"Bad signal rate 7d (linked): {bad_rate_7d:.0%} (n={g7 + b7})\n"
        f"Stale submitted payments (48h+): {stale_n}\n"
        f"Open incidents: {open_incidents}\n"
        f"Last accuracy digest: {digest_line}\n"
        f"Invites: valid={inv_rd.valid_active_invites}, remaining≈{inv_rd.remaining_redemptions_capacity}, "
        f"expired_flagged={inv_rd.expired_still_flagged_active}\n"
        f"Payments: manual={pay_rd.manual_enabled}, wallet={'set' if pay_rd.wallet_configured else 'missing'}, "
        f"prices_ok={pay_rd.prices_configured}, submitted={pay_rd.submitted_total}, stale_sla≈{pay_rd.stale_submitted_count}\n\n"
        "Рекомендовано дальше:\n" + "\n".join(f"• {x}" for x in recs[:6])
    )
    if owner_snap["warnings"]:
        body += "\n\nOwner warnings: " + ", ".join(owner_snap["warnings"][:5])
    await message.answer(body[:4090])


@router.message(Command("admin_beta_health"))
async def admin_beta_health_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        activation = await calculate_activation_metrics(session, period_days=7)
        feedback_sla = await FeedbackRepository(session).calculate_sla_metrics()
        payment_ops = await calculate_payment_ops_metrics(session, period_days=7)
        open_incidents = await AlertRepository(session).count_incidents()
        try:
            release = await _release_check_snapshot(session, get_settings())
        except Exception:
            release = {"status": "n/a"}
        try:
            signal_summary = await summarize_signal_feedback(session, period_days=7)
            signal_ratio = await calculate_signal_good_bad_ratio(session, period_days=7)
        except Exception:
            signal_summary = {"signal_good_count": 0, "signal_bad_count": 0}
            signal_ratio = 0.0
        try:
            funnel = await calculate_funnel_metrics(session, period_days=7)
        except Exception:
            funnel = {"pay_started": 0, "payment_submitted": 0}
        try:
            active_invites = await BetaInviteRepository(session).count_active()
        except Exception:
            active_invites = 0
        try:
            q_sig = await build_signal_review_queue(session, limit=40)
            queue_n = len(q_sig)
            g7, b7, _u7 = await SignalSnapshotRepository(session).count_linked_bad_good_signals(7)
            bad_rate_7d = b7 / max(g7 + b7, 1)
            unreviewed_bad = sum(1 for x in q_sig if x.bad_count > 0 and x.good_count == 0)
            pol = await evaluate_pricing_change_readiness(session, get_settings())
            pricing_ready = "ready" if pol["ready"] else "not_ready"
        except Exception:
            queue_n = 0
            bad_rate_7d = 0.0
            unreviewed_bad = 0
            pricing_ready = "n/a"
    activation_health = _health_label(activation["activation_rate"], good=0.4, warning=0.3)
    feedback_health = "bad" if feedback_sla["overdue_feedback_48h"] > 5 else "warning" if feedback_sla["overdue_feedback_48h"] > 0 else "good"
    payment_health = "bad" if payment_ops["stale_submitted_48h"] > 3 else "warning" if payment_ops["stale_submitted_48h"] > 0 else "good"
    incident_health = "bad" if open_incidents > 20 else "warning" if open_incidents > 8 else "good"
    data_quality_health = "warning" if activation["active_users"] == 0 else "good"
    states = [activation_health, feedback_health, payment_health, incident_health, data_quality_health]
    overall = "bad" if "bad" in states else "warning" if "warning" in states else "good"
    emoji = {"good": "🟢", "warning": "🟡", "bad": "🔴"}[overall]
    problems: list[str] = []
    if activation["activation_rate"] < 0.3:
        problems.append("Activation rate below 30%")
    if payment_ops["stale_submitted_48h"] > 0:
        problems.append(f"{payment_ops['stale_submitted_48h']} stale submitted payments")
    if feedback_sla["overdue_feedback_48h"] > 0:
        problems.append(f"{feedback_sla['overdue_feedback_48h']} feedback items older than 48h")
    if open_incidents > 8:
        problems.append(f"Incident noise high: {open_incidents} open incidents")
    if activation["active_users"] == 0:
        problems.append("No activity tracked in last 7 days")
    if funnel["pay_started"] > (funnel["payment_submitted"] * 2 + 1):
        problems.append("Payment funnel drop: pay_started much higher than payment_submitted")
    actions = [
        "- simplify /start",
        "- process /admin_payments_stale",
        "- review /admin_feedback_sla",
    ]
    await message.answer(
        f"{emoji} Beta Health: {overall}\n\n"
        f"activation health: {activation_health}\n"
        f"feedback health: {feedback_health}\n"
        f"payment ops health: {payment_health}\n"
        f"incident noise health: {incident_health}\n"
        f"data quality health: {data_quality_health}\n\n"
        f"release readiness: {release.get('status', 'n/a')}\n"
        f"smoke test last result: {(runtime_state.last_smoke_test_result or {}).get('status', 'n/a')}\n"
        f"signal quality ratio: {signal_ratio:.2f} ({signal_summary['signal_good_count']}/{signal_summary['signal_bad_count']})\n"
        f"signal review queue (approx): {queue_n}\n"
        f"bad signal rate 7d (linked): {bad_rate_7d:.0%}\n"
        f"unreviewed bad-leaning queue items: {unreviewed_bad}\n"
        f"pricing change policy: {pricing_ready}\n"
        f"beta gate enabled: {get_settings().beta_require_invite}\n"
        f"active invite count: {active_invites}\n\n"
        "Problems:\n"
        + ("\n".join([f"{idx + 1}. {p}" for idx, p in enumerate(problems[:5])]) if problems else "1. none")
        + "\n\nActions:\n"
        + "\n".join(actions)
    )


@router.message(Command("owner_setup_check"))
async def owner_setup_check_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    settings = get_settings()
    async with SessionLocal() as session:
        data = await _owner_setup_snapshot(session, settings)
    warning_text = ", ".join(data["warnings"]) if data["warnings"] else "none"
    commands = (
        "\n\nSetup commands:\n"
        "/admin_set_role 943071273 | owner\n"
        "/admin_grant_plan 943071273 | trader | 36500 | owner lifetime access"
        if data["warnings"]
        else ""
    )
    await message.answer(
        "🧩 Owner Setup Check\n"
        f"Expected owner telegram id: {data['expected_owner_tg']}\n"
        f"Owner found: {data['owner_found']}\n"
        f"Role: {data['role']}\n"
        f"Plan: {data['plan']}\n"
        f"Entitlement: {data['entitlement']}\n"
        f"ADMIN_TELEGRAM_IDS has owner: {data['owner_in_admin_ids']}\n"
        f"Manual TON wallet: {'configured' if data['wallet_configured'] else 'missing'}\n"
        f"Billing: enabled={data['billing_enabled']} provider={data['billing_provider']}\n"
        f"Beta mode: {data['beta_mode']}\n"
        f"Critical warnings: {warning_text}"
        f"{commands}"
    )


@router.message(Command("release_check"))
async def release_check_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    settings = get_settings()
    async with SessionLocal() as session:
        data = await _release_check_snapshot(session, settings)
    marker = {"ok": "✅", "warn": "⚠️", "block": "❌"}
    lines = [f"{marker[level]} {name}: {detail}" for name, level, detail in data["checks"]]
    await message.answer("🚦 Release Check\n" + "\n".join(lines) + f"\n\nResult: {data['status']}")


@router.message(Command("smoke_test"))
async def smoke_test_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    passed: list[str] = []
    failed: list[str] = []
    settings = get_settings()
    async with SessionLocal() as session:
        try:
            user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
            passed.append("create/read user context")
        except Exception as exc:
            failed.append(f"user context: {exc}")
            user = None
        try:
            _ = get_plan_limits((user.plan if user else "free"))
            passed.append("feature limits")
        except Exception as exc:
            failed.append(f"feature limits: {exc}")
        try:
            if user is not None:
                await get_effective_entitlement(session, user)
            passed.append("effective entitlement")
        except Exception as exc:
            failed.append(f"effective entitlement: {exc}")
        try:
            _ = create_market_source(settings, user_id=(user.id if user else None))
            passed.append("market source factory")
        except Exception as exc:
            failed.append(f"market source factory: {exc}")
        checks = [
            ("product events repo", ProductEventRepository(session).count_events()),
            ("feedback repo", FeedbackRepository(session).count_new()),
            ("billing repo", BillingRepository(session).list_billing_events(limit=1)),
            ("manual payments repo", ManualPaymentRepository(session).list_by_status(["pending"], limit=1)),
            ("alerts repo", AlertRepository(session).count_incidents()),
        ]
        for name, coro in checks:
            try:
                await coro
                passed.append(name)
            except Exception as exc:
                failed.append(f"{name}: {exc}")
        try:
            fake_msg = type("M", (), {"from_user": type("U", (), {"id": message.from_user.id, "username": message.from_user.username})()})()
            await _render_home(fake_msg)  # noqa: SLF001
            passed.append("home formatter")
        except Exception as exc:
            failed.append(f"home formatter: {exc}")
        try:
            _ = format_beta_metrics_report(
                activation={"period_days": 7, "new_users": 0, "active_users": 0, "activated_users": 0, "activation_rate": 0.0},
                retention={"retained_users": 0},
                funnel={"invite_redeemed": 0, "checked_gift": 0, "added_gift": 0, "upgrade_viewed": 0, "pay_started": 0, "payment_submitted": 0, "feedback_count": 0},
                feature={"top_commands": []},
            )
            passed.append("beta metrics formatter")
        except Exception as exc:
            failed.append(f"beta metrics formatter: {exc}")
    status = "passed" if not failed else "failed"
    runtime_state.last_smoke_test_result = {
        "status": status,
        "passed_count": len(passed),
        "failed_count": len(failed),
        "failed_checks": failed,
        "at": datetime.now(timezone.utc),
    }
    await message.answer(
        "🧪 Smoke Test\n"
        f"Passed checks: {len(passed)}\n"
        f"Failed checks: {len(failed)}\n"
        + ("Failures:\n" + "\n".join(f"- {x}" for x in failed) + "\n" if failed else "")
        + ("Recommended action: fix failed checks before launch." if failed else "Recommended action: safe to proceed to release_check.")
    )


@router.message(Command("admin_signal_quality"))
async def admin_signal_quality_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        summary = await summarize_signal_feedback(session, period_days=7)
        ratio = await calculate_signal_good_bad_ratio(session, period_days=7)
    await message.answer(format_signal_quality_report(summary, ratio))


@router.message(Command("admin_cohort_report"))
async def admin_cohort_report_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    since = datetime.now(timezone.utc) - timedelta(days=7)
    async with SessionLocal() as session:
        users_repo = UserRepository(session)
        feedback_repo = FeedbackRepository(session)
        invites_repo = BetaInviteRepository(session)
        payments_repo = ManualPaymentRepository(session)
        all_events = await ProductEventRepository(session).list_events(since=since, limit=2000)
        source_users = await users_repo.list_all()
        users = []
        for u in source_users:
            created = u.created_at if u.created_at.tzinfo else u.created_at.replace(tzinfo=timezone.utc)
            last_seen = None
            if u.last_seen_at is not None:
                last_seen = u.last_seen_at if u.last_seen_at.tzinfo else u.last_seen_at.replace(tzinfo=timezone.utc)
            if created >= since or (last_seen and last_seen >= since):
                users.append(u)
        rows = []
        for user in users[:50]:
            user_cmds = {e.command for e in all_events if e.user_id == user.id and e.command}
            activated = len([c for c in user_cmds if c in {"/add", "/check", "/deal", "/deals", "/portfolio", "/bank_set", "/redeem"}]) >= 2
            invite = await invites_repo.has_user_redemption(user.id)
            feedback_count = await feedback_repo.count_by_user(user.id)
            payment_rows = await payments_repo.list_user_payment_requests(user.id, limit=3)
            payment_status = payment_rows[0].status if payment_rows else "n/a"
            risks = []
            last_seen = user.last_seen_at or user.created_at
            seen = last_seen if last_seen.tzinfo else last_seen.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - seen).days >= 3:
                risks.append("inactive")
            if not activated:
                risks.append("not_activated")
            if any(p.status == "submitted" for p in payment_rows):
                risks.append("payment_stuck")
            if feedback_count == 0:
                risks.append("no_feedback")
            rows.append(
                f"{user.telegram_id}/{('@'+user.username) if user.username else 'n/a'} "
                f"plan={user.plan} first={user.first_seen_at or 'n/a'} last={user.last_seen_at or 'n/a'} "
                f"cmd={user.command_count} activated={'yes' if activated else 'no'} invite={'yes' if invite else 'no'} "
                f"feedback={feedback_count} pay={payment_status} risk={','.join(risks) if risks else 'ok'}"
            )
    await message.answer("👥 Beta Cohort Report (7d)\n" + ("\n".join(rows[:20]) if rows else "- none"))


@router.message(Command("beta_go_no_go"))
async def beta_go_no_go_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    settings = get_settings()
    status = "GO"
    blockers: list[str] = []
    async with SessionLocal() as session:
        release = await _release_check_snapshot(session, settings)
        status = _merge_status(status, release["status"])
        if release["status"] == "NO_GO":
            blockers.append("release_check has blocking issues")
        owner = await _owner_setup_snapshot(session, settings)
        if owner["warnings"]:
            status = _merge_status(status, "NO_GO")
            blockers.append("owner setup not complete")
        smoke = runtime_state.last_smoke_test_result or {"status": "n/a", "failed_count": 1}
        if smoke.get("status") != "passed":
            status = _merge_status(status, "GO_WITH_WARNINGS")
            blockers.append("smoke_test not passed recently")
        feedback_sla = await FeedbackRepository(session).calculate_sla_metrics()
        if feedback_sla["overdue_feedback_48h"] > 5:
            status = _merge_status(status, "GO_WITH_WARNINGS")
            blockers.append("feedback SLA backlog too high")
        payment_ops = await calculate_payment_ops_metrics(session, period_days=7)
        if payment_ops["stale_submitted_48h"] > 3:
            status = _merge_status(status, "GO_WITH_WARNINGS")
            blockers.append("stale submitted payments > 3")
        activation = await calculate_activation_metrics(session, period_days=7)
        if activation["activation_rate"] < 0.2:
            status = _merge_status(status, "GO_WITH_WARNINGS")
            blockers.append("beta health: activation critically low")
    await message.answer(
        "🚦 Beta Go/No-Go\n"
        f"Decision: {status}\n"
        "Top blockers:\n"
        + ("\n".join(f"- {x}" for x in blockers[:5]) if blockers else "- none")
    )


@router.message(Command("beta_launch_check"))
@router.message(Command("launch_check"))
async def beta_launch_check_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    settings = get_settings()
    async with SessionLocal() as session:
        report = await build_beta_launch_readiness_report(session, settings)
    await _answer_long_admin(message, format_beta_launch_readiness_report(report))


@router.message(Command("smoke_suite"))
async def smoke_suite_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    settings = get_settings()
    async with SessionLocal() as session:
        user = await UserRepository(session).get_or_create(message.from_user.id, message.from_user.username)
        report = await build_smoke_suite_report(session, settings, user_id=user.id)
    await _answer_long_admin(message, format_smoke_suite_report(report))


@router.message(Command("beta_smoke_plan"))
async def beta_smoke_plan_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    await message.answer(BETA_SMOKE_PLAN_TEXT)


@router.message(Command("beta_user_script"))
async def beta_user_script_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    await message.answer(BETA_USER_SCRIPT_TEXT)


@router.message(Command("prod_health"))
async def prod_health_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    settings = get_settings()
    db_ok = False
    current_revision = "n/a"
    active_jobs_count = "n/a"
    launch_line = "n/a"
    active_invites_n = "n/a"
    owner_admin_line = "n/a"
    wallet_line = "n/a"
    snap_n = fb_n = 0
    pay_sub = pay_stale = "n/a"
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
            rev = await session.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
            row = rev.first()
            current_revision = str(row[0]) if row else "n/a"
            db_ok = True
            report = await build_beta_launch_readiness_report(session, settings)
            launch_line = report.overall_status
            inv_rd = await build_beta_invite_readiness(session, settings)
            active_invites_n = str(inv_rd.valid_active_invites)
            owner_snap = await _owner_setup_snapshot(session, settings)
            owner_admin_line = "ok" if not owner_snap["warnings"] and str(settings.admin_telegram_ids).strip() else "needs_setup"
            pay_rd = await build_payment_readiness(session, settings)
            wallet_line = "set" if pay_rd.wallet_configured else "missing"
            pay_sub = str(pay_rd.submitted_total)
            pay_stale = str(pay_rd.stale_submitted_count)
            snap_n = int(await session.scalar(select(func.count(SignalSnapshot.id))) or 0)
            fb_n = int(await session.scalar(select(func.count(FeedbackItem.id))) or 0)
    except Exception:
        db_ok = False
    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    head_revision = script.get_current_head() or "n/a"
    sources = describe_sources(settings)
    mock_warn = "yes" if bool(getattr(settings, "enable_mock_source", False)) else "no"
    mem_warn = "rate_limits+gifts+cache in-memory (see /beta_launch_check)"
    await message.answer(
        "🛡 Production Health\n"
        f"Beta launch readiness: {launch_line}\n"
        f"Active invites (valid): {active_invites_n}\n"
        f"Owner/admin config: {owner_admin_line}\n"
        f"Manual payment wallet: {wallet_line}\n"
        f"Mock source mode: {mock_warn}\n"
        f"Runtime: {mem_warn}\n"
        f"DB: {'ok' if db_ok else 'fail'}\n"
        f"Migrations current/head: {current_revision}/{head_revision}\n"
        f"Last price alert check: {runtime_state.last_price_alert_check or 'n/a'}\n"
        f"Last smart alert check: {runtime_state.last_smart_alert_check or 'n/a'}\n"
        f"Last digest check: {runtime_state.last_digest_check or 'n/a'}\n"
        f"Last accuracy digest: {runtime_state.last_accuracy_digest_check or 'n/a'}\n"
        f"Active jobs count: {active_jobs_count}\n"
        f"Signal snapshots (rows): {snap_n}\n"
        f"Feedback items (rows): {fb_n}\n"
        f"Manual payments submitted / stale (SLA): {pay_sub} / {pay_stale}\n"
        f"Sources: mock={sources['mock_enabled']}, getgems={sources['getgems']['enabled']}, tonapi={sources['tonapi']['enabled']}\n"
        "Env sanity (set/missing only):\n"
        f"BOT_TOKEN: {_flag_set(settings.bot_token)}\n"
        f"DATABASE_URL: {_flag_set(settings.database_url)}\n"
        f"TONAPI_API_KEY: {_flag_set(settings.tonapi_api_key)}\n"
        f"GETGEMS_API_KEY: {_flag_set(settings.getgems_api_key)}"
    )


@router.message(Command("admin_accuracy_report"))
async def admin_accuracy_report_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        rows = await TradeJournalRepository(session).list_all(limit=20_000)
    await message.answer(build_admin_accuracy_report(rows))


@router.message(Command("market_cache_status"))
async def market_cache_status_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    await message.answer(format_cache_status())


@router.message(Command("market_cache_clear"))
async def market_cache_clear_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    rest = (message.text or "").removeprefix("/market_cache_clear").strip()
    removed = clear_market_cache(rest if rest else None)
    await message.answer(f"Очищено записей кэша: {removed}" + (f" (фильтр: {rest})" if rest else ""))


async def _answer_long_admin(message: Message, text: str, chunk: int = 3500) -> None:
    if len(text) <= chunk:
        await message.answer(text)
        return
    for i in range(0, len(text), chunk):
        await message.answer(text[i : i + chunk])


@router.message(Command("admin_trade_import_preview"))
async def admin_trade_import_preview_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    parts = _parse_pipe(message.text or "", "/admin_trade_import_preview")
    if len(parts) < 2 or not parts[0].isdigit():
        await message.answer("Формат: /admin_trade_import_preview <telegram_id> | <CSV header+rows>")
        return
    tg = int(parts[0])
    csv_body = parts[1].strip()
    fields, rows = parse_trade_csv(csv_body)
    errs: list[tuple[int, str]] = []
    for i, row in enumerate(rows, start=2):
        ok, e = validate_trade_row(row, i)
        if not ok:
            errs.extend((i, x) for x in e)
    await message.answer(f"Target tg: {tg}\n" + format_trade_import_preview(fields, rows, errs))


@router.message(Command("admin_trade_import_commit"))
async def admin_trade_import_commit_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    parts = _parse_pipe(message.text or "", "/admin_trade_import_commit")
    if len(parts) < 2 or not parts[0].isdigit():
        await message.answer("Формат: /admin_trade_import_commit <telegram_id> | <CSV...>")
        return
    tg = int(parts[0])
    _, rows = parse_trade_csv(parts[1].strip())
    async with SessionLocal() as session:
        urepo = UserRepository(session)
        target = await urepo.get_by_telegram_id(tg)
        if target is None:
            await message.answer("Пользователь с таким telegram_id не найден.")
            return
        res = await import_trades_for_user(session, target.id, rows)
    await message.answer(f"User id {target.id} (tg {tg}):\n" + format_trade_import_result(res))


@router.message(Command("admin_pricing_tuning_report"))
async def admin_pricing_tuning_report_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    settings = get_settings()
    async with SessionLocal() as session:
        rows = await TradeJournalRepository(session).list_all(limit=25_000)
    rep = analyze_pricing_accuracy(rows, settings=settings)
    await _answer_long_admin(message, format_pricing_tuning_report(rep))


@router.message(Command("admin_pricing_config_current"))
async def admin_pricing_config_current_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    await message.answer(format_pricing_config_current(get_settings()))


@router.message(Command("admin_pricing_config_suggest"))
async def admin_pricing_config_suggest_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    await message.answer(format_pricing_config_suggest())


@router.message(Command("admin_build_calibration_dataset"))
async def admin_build_calibration_dataset_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    root = Path(__file__).resolve().parents[3]
    out_dir = root / "tests" / "fixtures" / "calibration" / "scenarios" / "generated"
    async with SessionLocal() as session:
        rows = await TradeJournalRepository(session).list_all(limit=25_000)
    scenarios, skipped = build_scenarios_from_trade_journal(rows)
    res = export_calibration_scenarios_json(scenarios, out_dir)
    await message.answer(format_dataset_builder_report(res, out_dir, extra_skipped=skipped))


@router.message(Command("admin_backtest_trades"))
async def admin_backtest_trades_handler(message: Message) -> None:
    if await _require_admin(message) is None:
        return
    async with SessionLocal() as session:
        rows = await TradeJournalRepository(session).list_all(limit=25_000)
    pairs = journal_rows_to_backtest_pairs(rows)
    if not pairs:
        await message.answer("Нет закрытых сделок для бэктеста.")
        return
    rep = run_backtest(pairs)
    await _answer_long_admin(message, format_backtest_report(rep) + "\n(агрегат по всем пользователям)")


@router.message(Command("privacy"))
async def privacy_handler(message: Message) -> None:
    await message.answer(privacy_text())


@router.message(Command("disclaimer"))
async def disclaimer_handler(message: Message) -> None:
    await message.answer(disclaimer_text())
