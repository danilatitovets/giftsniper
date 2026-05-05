"""Beta / production launch readiness (read-only; no env mutation)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.known_commands import KNOWN_BOT_COMMANDS
from app.db.models import FeedbackItem, ProductEvent, SignalSnapshot, TradeJournal
from app.db.repositories.users import UserRepository
from app.services import runtime_state
from app.services.beta_invite_readiness import build_beta_invite_readiness
from app.services.payment_readiness import build_payment_readiness, manual_prices_configured
from app.services.source_readiness import build_source_readiness_summary


@dataclass
class ReadinessCheck:
    key: str
    title: str
    status: Literal["pass", "warn", "fail"]
    details: str
    action: str | None = None


@dataclass
class BetaLaunchReadinessReport:
    overall_status: Literal["GO", "GO_WITH_WARNINGS", "NO_GO"]
    checks: list[ReadinessCheck] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)


def _emoji(st: str) -> str:
    return {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(st, "•")


async def _migration_heads(session: AsyncSession) -> tuple[str, str, bool]:
    current = "n/a"
    try:
        rev = await session.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
        row = rev.first()
        current = str(row[0]) if row else "n/a"
    except Exception:
        return "n/a", "n/a", False
    try:
        cfg = Config("alembic.ini")
        head = ScriptDirectory.from_config(cfg).get_current_head() or "n/a"
    except Exception:
        head = "n/a"
    ok = current == head and current != "n/a"
    return current, head, ok


async def build_beta_launch_readiness_report(session: AsyncSession, settings) -> BetaLaunchReadinessReport:
    checks: list[ReadinessCheck] = []

    def add(c: ReadinessCheck) -> None:
        checks.append(c)

    if not str(getattr(settings, "bot_token", "") or "").strip():
        add(
            ReadinessCheck(
                key="bot_token",
                title="BOT_TOKEN",
                status="fail",
                details="BOT_TOKEN missing — bot cannot run.",
                action="Set BOT_TOKEN in environment.",
            )
        )
    else:
        add(ReadinessCheck(key="bot_token", title="BOT_TOKEN", status="pass", details="set", action=None))

    if not str(getattr(settings, "database_url", "") or "").strip():
        add(
            ReadinessCheck(
                key="database_url",
                title="DATABASE_URL",
                status="fail",
                details="DATABASE_URL missing.",
                action="Configure database connection.",
            )
        )
    else:
        add(ReadinessCheck(key="database_url", title="DATABASE_URL", status="pass", details="set", action=None))

    db_ok = False
    mig_ok = False
    cur_rev, head_rev = "n/a", "n/a"
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
        cur_rev, head_rev, mig_ok = await _migration_heads(session)
    except Exception as exc:
        add(
            ReadinessCheck(
                key="db_connect",
                title="Database connectivity / migrations",
                status="fail",
                details=f"DB unreachable or alembic check failed: {exc!s}"[:500],
                action="Fix DATABASE_URL and run alembic upgrade head.",
            )
        )

    if str(getattr(settings, "database_url", "") or "").strip() and db_ok:
        st = "pass" if mig_ok else "warn"
        add(
            ReadinessCheck(
                key="db_migrations",
                title="Alembic revision vs head",
                status=st,
                details=f"current={cur_rev} head={head_rev}",
                action=None if mig_ok else "Run: python -m alembic upgrade head",
            )
        )

    from app.bot.handlers.admin import _owner_setup_snapshot

    owner_snap = await _owner_setup_snapshot(session, settings)
    admin_ids_configured = bool(str(getattr(settings, "admin_telegram_ids", "") or "").strip())

    if not admin_ids_configured and not owner_snap["owner_found"]:
        add(
            ReadinessCheck(
                key="admin_owner",
                title="Owner / admin configuration",
                status="fail",
                details="No ADMIN_TELEGRAM_IDS and owner user not found in DB.",
                action="Set ADMIN_TELEGRAM_IDS and /admin_set_role for owner.",
            )
        )
    elif owner_snap["warnings"] and not admin_ids_configured:
        add(
            ReadinessCheck(
                key="admin_owner",
                title="Owner / admin configuration",
                status="fail",
                details="Owner warnings: " + "; ".join(owner_snap["warnings"][:3]),
                action="/owner_setup_check",
            )
        )
    elif owner_snap["warnings"]:
        add(
            ReadinessCheck(
                key="admin_owner",
                title="Owner / admin configuration",
                status="warn",
                details="Owner setup warnings: " + "; ".join(owner_snap["warnings"][:3]),
                action="/owner_setup_check",
            )
        )
    else:
        add(
            ReadinessCheck(
                key="admin_owner",
                title="Owner / admin configuration",
                status="pass",
                details="owner role and admin ids look configured",
                action=None,
            )
        )

    pay = await build_payment_readiness(session, settings)
    if pay.manual_enabled and not pay.wallet_configured:
        add(
            ReadinessCheck(
                key="manual_wallet",
                title="Manual payments wallet",
                status="fail",
                details="Manual payments enabled but OWNER_CRYPTO_WALLET_TON missing.",
                action="Set receive-only TON address in OWNER_CRYPTO_WALLET_TON.",
            )
        )
    elif pay.manual_enabled:
        add(
            ReadinessCheck(
                key="manual_wallet",
                title="Manual payments wallet",
                status="pass",
                details="wallet configured",
                action=None,
            )
        )
    else:
        add(
            ReadinessCheck(
                key="manual_wallet",
                title="Manual payments",
                status="warn",
                details="manual_payment_enabled=false",
                action=None,
            )
        )

    prod = bool(getattr(settings, "production_mode", False))
    if prod and not admin_ids_configured:
        add(
            ReadinessCheck(
                key="prod_admin_ids",
                title="Production admin IDs",
                status="fail",
                details="PRODUCTION_MODE with empty ADMIN_TELEGRAM_IDS.",
                action="Set ADMIN_TELEGRAM_IDS before production traffic.",
            )
        )
    elif prod:
        add(ReadinessCheck(key="prod_admin_ids", title="Production admin IDs", status="pass", details="configured", action=None))

    inv = await build_beta_invite_readiness(session, settings)
    if inv.require_invite_gate and inv.valid_active_invites == 0:
        add(
            ReadinessCheck(
                key="beta_invites",
                title="Beta invites (gate on)",
                status="fail",
                details="BETA_REQUIRE_INVITE=true but no valid active invites.",
                action="/admin_create_invite …",
            )
        )
    elif inv.expired_still_flagged_active > 0:
        add(
            ReadinessCheck(
                key="beta_invites",
                title="Beta invites",
                status="warn",
                details=f"{inv.expired_still_flagged_active} invite(s) still active but expired — cleanup.",
                action="/admin_invites",
            )
        )
    else:
        add(
            ReadinessCheck(
                key="beta_invites",
                title="Beta invites",
                status="pass",
                details=f"valid_active={inv.valid_active_invites}, remaining_slots≈{inv.remaining_redemptions_capacity}",
                action=None,
            )
        )

    if pay.manual_enabled and not manual_prices_configured(settings):
        add(
            ReadinessCheck(
                key="payment_prices",
                title="Manual payment prices",
                status="warn",
                details="Manual payments on but starter/pro/trader TON prices look unset or zero.",
                action="Set MANUAL_PAYMENT_*_TON in .env",
            )
        )

    if not str(getattr(settings, "tonapi_api_key", "") or "").strip():
        add(
            ReadinessCheck(
                key="tonapi_key",
                title="TONAPI_API_KEY",
                status="warn",
                details="missing — TonAPI features degraded",
                action="Optional: set TONAPI_API_KEY",
            )
        )
    else:
        add(ReadinessCheck(key="tonapi_key", title="TONAPI_API_KEY", status="pass", details="set", action=None))

    if not str(getattr(settings, "getgems_api_key", "") or "").strip() and bool(getattr(settings, "getgems_enabled", True)):
        add(
            ReadinessCheck(
                key="getgems_key",
                title="GETGEMS_API_KEY",
                status="warn",
                details="missing while Getgems enabled",
                action="Optional: set key or disable source",
            )
        )

    if prod and bool(getattr(settings, "enable_mock_source", False)):
        allow_mock = bool(getattr(settings, "allow_mock_in_production", False))
        block = bool(getattr(settings, "block_trading_verdict_on_mock", True))
        st: Literal["pass", "warn", "fail"] = "fail" if (not allow_mock and block) else "warn"
        add(
            ReadinessCheck(
                key="mock_prod",
                title="Mock source in production",
                status=st,
                details="ENABLE_MOCK_SOURCE=true with PRODUCTION_MODE — trading verdicts from mock are unsafe.",
                action="Set ENABLE_MOCK_SOURCE=false or ALLOW_MOCK_IN_PRODUCTION=true (not recommended).",
            )
        )

    src = build_source_readiness_summary(settings)
    for w in src.warnings[:3]:
        add(ReadinessCheck(key="source_readiness", title="Sources", status="warn", details=w, action=None))

    if not bool(getattr(settings, "beta_mode", True)):
        add(
            ReadinessCheck(
                key="beta_mode_flag",
                title="BETA_MODE",
                status="warn",
                details="BETA_MODE=false",
                action="Confirm intentional for closed beta.",
            )
        )
    else:
        add(ReadinessCheck(key="beta_mode_flag", title="BETA_MODE", status="pass", details="enabled", action=None))

    users_total = await UserRepository(session).count_all()
    if users_total == 0:
        add(ReadinessCheck(key="users", title="Users", status="warn", details="no users yet", action=None))

    pe_count = int(await session.scalar(select(func.count(ProductEvent.id))) or 0)
    if pe_count == 0 and users_total > 0:
        add(ReadinessCheck(key="product_events", title="Product events", status="warn", details="no analytics events yet", action=None))

    fb_count = int(await session.scalar(select(func.count(FeedbackItem.id))) or 0)
    if fb_count == 0:
        add(ReadinessCheck(key="feedback", title="Feedback", status="warn", details="no feedback rows yet", action=None))

    snap_count = int(await session.scalar(select(func.count(SignalSnapshot.id))) or 0)
    if snap_count == 0:
        add(ReadinessCheck(key="signals", title="Signal snapshots", status="warn", details="no signal snapshots yet", action=None))

    tj_count = int(await session.scalar(select(func.count(TradeJournal.id))) or 0)
    if tj_count == 0:
        add(ReadinessCheck(key="trade_journal", title="Trade journal", status="warn", details="no trade journal rows yet", action=None))

    add(
        ReadinessCheck(
            key="rate_limit_storage",
            title="Rate limiter storage",
            status="warn",
            details="In-memory per process (resets on restart; not shared across workers).",
            action="Accept for beta or add shared store later.",
        )
    )
    add(
        ReadinessCheck(
            key="pending_gift_storage",
            title="Pending gift callbacks",
            status="warn",
            details="In-memory pending_gift_inputs (TTL); not shared across workers.",
            action=None,
        )
    )
    add(
        ReadinessCheck(
            key="market_cache",
            title="Market cache",
            status="warn",
            details="In-memory TTL cache (see market_cache.py).",
            action=None,
        )
    )
    add(
        ReadinessCheck(
            key="redis",
            title="Redis",
            status="warn",
            details="Not used by this codebase; distributed cache/limits not configured.",
            action=None,
        )
    )

    if "privacy" in KNOWN_BOT_COMMANDS and "disclaimer" in KNOWN_BOT_COMMANDS:
        add(
            ReadinessCheck(
                key="privacy_commands",
                title="Privacy / disclaimer commands",
                status="pass",
                details="/privacy and /disclaimer registered",
                action=None,
            )
        )
    else:
        add(
            ReadinessCheck(
                key="privacy_commands",
                title="Privacy / disclaimer commands",
                status="warn",
                details="expected commands missing from known set",
                action=None,
            )
        )

    add(
        ReadinessCheck(
            key="prod_health_command",
            title="prod_health command",
            status="pass",
            details="/prod_health available for admins",
            action=None,
        )
    )

    any_fail = any(c.status == "fail" for c in checks)
    any_warn = any(c.status == "warn" for c in checks)
    if any_fail:
        overall: Literal["GO", "GO_WITH_WARNINGS", "NO_GO"] = "NO_GO"
    elif any_warn:
        overall = "GO_WITH_WARNINGS"
    else:
        overall = "GO"

    blockers = [f"{c.title}: {c.details}" for c in checks if c.status == "fail"]
    warnings = [f"{c.title}: {c.details}" for c in checks if c.status == "warn"]
    recommended: list[str] = []
    seen_act: set[str] = set()
    for c in checks:
        if c.action and c.status != "pass" and c.action not in seen_act:
            seen_act.add(c.action)
            recommended.append(c.action)

    return BetaLaunchReadinessReport(
        overall_status=overall,
        checks=checks,
        blockers=blockers,
        warnings=warnings,
        recommended_actions=recommended[:12],
    )


def format_beta_launch_readiness_report(report: BetaLaunchReadinessReport) -> str:
    lines = [
        "🚀 Beta launch readiness",
        f"Overall: {report.overall_status}",
        "",
        "Checks:",
    ]
    for c in report.checks:
        lines.append(f"{_emoji(c.status)} [{c.key}] {c.title}: {c.details}")
        if c.action:
            lines.append(f"   → {c.action}")
    if report.blockers:
        lines.extend(["", "Blockers:", *[f"• {b}" for b in report.blockers[:8]]])
    if report.warnings and report.overall_status != "NO_GO":
        lines.extend(["", "Warnings (sample):", *[f"• {w}" for w in report.warnings[:8]]])
    if report.recommended_actions:
        lines.extend(["", "Recommended:", *[f"• {a}" for a in report.recommended_actions[:10]]])
    return "\n".join(lines)[:4090]
