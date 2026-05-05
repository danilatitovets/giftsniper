"""Read-only smoke checks for deploy (no external HTTP, no user messages)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FeedbackItem, SignalSnapshot, TradeJournal
from app.services.feature_limits import PLAN_LIMITS
from app.services import runtime_state
from app.sources.collections import load_collection_registry
from app.sources.factory import create_market_source, describe_sources


@dataclass
class SmokeCheck:
    key: str
    title: str
    status: Literal["pass", "warn", "fail"]
    details: str
    command_hint: str | None = None


@dataclass
class SmokeSuiteReport:
    overall_status: Literal["GO", "GO_WITH_WARNINGS", "NO_GO"]
    checks: list[SmokeCheck] = field(default_factory=list)
    recommended_commands: list[str] = field(default_factory=list)


def _overall(checks: list[SmokeCheck]) -> Literal["GO", "GO_WITH_WARNINGS", "NO_GO"]:
    if any(c.status == "fail" for c in checks):
        return "NO_GO"
    if any(c.status == "warn" for c in checks):
        return "GO_WITH_WARNINGS"
    return "GO"


async def build_smoke_suite_report(
    session: AsyncSession,
    settings,
    user_id: int | None = None,
) -> SmokeSuiteReport:
    checks: list[SmokeCheck] = []

    def add(c: SmokeCheck) -> None:
        checks.append(c)

    try:
        reg = load_collection_registry(settings.collection_registry_path)
        n = len(reg)
    except Exception as exc:
        n = 0
        add(
            SmokeCheck(
                key="registry",
                title="Collection registry",
                status="fail",
                details=f"cannot load registry: {exc!s}"[:300],
                command_hint="/market_cache_status",
            )
        )
    else:
        mock_ok = bool(getattr(settings, "enable_mock_source", False))
        if n > 0 or mock_ok:
            add(
                SmokeCheck(
                    key="registry",
                    title="Collection registry / mock",
                    status="pass",
                    details=f"collections={n}, mock_source={mock_ok}",
                    command_hint=None,
                )
            )
        else:
            add(
                SmokeCheck(
                    key="registry",
                    title="Collection registry",
                    status="warn",
                    details="registry empty and mock disabled",
                    command_hint="ENABLE_MOCK_SOURCE=true for lab or add collections.json",
                )
            )

    try:
        create_market_source(settings, user_id=user_id)
        add(SmokeCheck(key="source_factory", title="Market source factory", status="pass", details="create_market_source ok", command_hint=None))
    except Exception as exc:
        add(
            SmokeCheck(
                key="source_factory",
                title="Market source factory",
                status="fail",
                details=str(exc)[:400],
                command_hint="/prod_health",
            )
        )

    desc = describe_sources(settings)
    manual_on = bool((desc.get("manual") or {}).get("enabled"))
    if manual_on or bool(getattr(settings, "enable_mock_source", False)):
        add(SmokeCheck(key="manual_market", title="Manual / fallback market", status="pass", details="manual or mock available", command_hint=None))
    else:
        add(SmokeCheck(key="manual_market", title="Manual market", status="warn", details="verify ManualSource in stack", command_hint=None))

    if PLAN_LIMITS:
        add(SmokeCheck(key="feature_gates", title="Feature gates (plans)", status="pass", details=f"{len(PLAN_LIMITS)} plans", command_hint=None))
    else:
        add(SmokeCheck(key="feature_gates", title="Feature gates", status="fail", details="PLAN_LIMITS empty", command_hint=None))

    prov = str(getattr(settings, "billing_provider", "") or "").strip()
    if prov:
        add(SmokeCheck(key="billing", title="Billing provider", status="pass", details=prov, command_hint=None))
    else:
        add(SmokeCheck(key="billing", title="Billing provider", status="warn", details="not set", command_hint=None))

    try:
        await session.scalar(select(func.count(SignalSnapshot.id)))
        add(SmokeCheck(key="signal_table", title="Signal snapshots table", status="pass", details="readable", command_hint=None))
    except Exception as exc:
        add(SmokeCheck(key="signal_table", title="Signal snapshots", status="fail", details=str(exc)[:200], command_hint=None))

    try:
        await session.scalar(select(func.count(TradeJournal.id)))
        add(SmokeCheck(key="trade_journal", title="Trade journal table", status="pass", details="readable", command_hint=None))
    except Exception as exc:
        add(SmokeCheck(key="trade_journal", title="Trade journal", status="fail", details=str(exc)[:200], command_hint=None))

    try:
        await session.scalar(select(func.count(FeedbackItem.id)))
        add(SmokeCheck(key="feedback_table", title="Feedback table", status="pass", details="readable", command_hint=None))
    except Exception as exc:
        add(SmokeCheck(key="feedback_table", title="Feedback", status="fail", details=str(exc)[:200], command_hint=None))

    try:
        _ = runtime_state.last_price_alert_check
        _ = runtime_state.pending_gift_inputs
        add(
            SmokeCheck(
                key="scheduler_runtime",
                title="Scheduler runtime state",
                status="pass",
                details="runtime_state module reachable",
                command_hint="/scheduler_status",
            )
        )
    except Exception as exc:
        add(SmokeCheck(key="scheduler_runtime", title="Runtime state", status="warn", details=str(exc)[:200], command_hint=None))

    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        add(SmokeCheck(key="db", title="Database session", status="fail", details=str(exc)[:200], command_hint=None))

    overall = _overall(checks)
    recs = list(
        dict.fromkeys(
            [c.command_hint for c in checks if c.command_hint and c.status != "pass"],
        )
    )[:8]
    if "/beta_launch_check" not in recs and overall != "GO":
        recs.insert(0, "/beta_launch_check")
    return SmokeSuiteReport(overall_status=overall, checks=checks, recommended_commands=recs)


def format_smoke_suite_report(report: SmokeSuiteReport) -> str:
    lines = ["🧪 Smoke suite (read-only)", f"Overall: {report.overall_status}", ""]
    for c in report.checks:
        emoji = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(c.status, "•")
        lines.append(f"{emoji} {c.title}: {c.details}")
        if c.command_hint:
            lines.append(f"   hint: {c.command_hint}")
    if report.recommended_commands:
        lines.extend(["", "Try:", *[f"• {x}" for x in report.recommended_commands]])
    return "\n".join(lines)[:4090]
