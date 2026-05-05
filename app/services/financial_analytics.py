from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ManualPaymentRequest


async def calculate_revenue_summary(session: AsyncSession, period_days: int = 30) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=period_days)
    stmt = select(func.coalesce(func.sum(ManualPaymentRequest.amount), 0.0)).where(
        ManualPaymentRequest.status == "confirmed",
        ManualPaymentRequest.created_at >= since,
        ManualPaymentRequest.currency == "TON",
    )
    revenue = float(await session.scalar(stmt) or 0.0)
    cnt_stmt = select(func.count(ManualPaymentRequest.id)).where(
        ManualPaymentRequest.status == "confirmed",
        ManualPaymentRequest.created_at >= since,
    )
    payments_count = int(await session.scalar(cnt_stmt) or 0)
    return {"period_days": period_days, "revenue_ton": revenue, "payments_count": payments_count}


async def calculate_mrr(session: AsyncSession) -> float:
    summary = await calculate_revenue_summary(session, period_days=30)
    return float(summary["revenue_ton"])


async def calculate_arpu(session: AsyncSession, period_days: int = 30) -> float:
    since = datetime.now(timezone.utc) - timedelta(days=period_days)
    revenue = float((await calculate_revenue_summary(session, period_days))["revenue_ton"])
    payers_stmt = select(func.count(func.distinct(ManualPaymentRequest.user_id))).where(
        ManualPaymentRequest.status == "confirmed",
        ManualPaymentRequest.created_at >= since,
    )
    payers = int(await session.scalar(payers_stmt) or 0)
    return float(revenue / payers) if payers else 0.0


async def revenue_by_plan(session: AsyncSession, period_days: int = 30) -> dict[str, float]:
    since = datetime.now(timezone.utc) - timedelta(days=period_days)
    stmt = (
        select(ManualPaymentRequest.requested_plan, func.coalesce(func.sum(ManualPaymentRequest.amount), 0.0))
        .where(
            ManualPaymentRequest.status == "confirmed",
            ManualPaymentRequest.created_at >= since,
        )
        .group_by(ManualPaymentRequest.requested_plan)
    )
    rows = (await session.execute(stmt)).all()
    return {str(plan): float(amount or 0.0) for plan, amount in rows}


async def conversion_summary(session: AsyncSession, period_days: int = 30) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=period_days)
    rows = (
        await session.execute(
            select(ManualPaymentRequest.status, func.count(ManualPaymentRequest.id))
            .where(ManualPaymentRequest.created_at >= since)
            .group_by(ManualPaymentRequest.status)
        )
    ).all()
    counts = {str(status): int(cnt) for status, cnt in rows}
    total = sum(counts.values())
    confirmed = counts.get("confirmed", 0)
    return {
        "counts": counts,
        "total": total,
        "confirmed_conversion": (confirmed / total) if total else 0.0,
    }


def format_financial_report(*, revenue_summary: dict, mrr: float, arpu: float, by_plan: dict[str, float], conversion: dict) -> str:
    counts = conversion.get("counts", {})
    top_plans = sorted(by_plan.items(), key=lambda x: x[1], reverse=True)[:3]
    plan_lines = ", ".join(f"{k}:{v:.2f} TON" for k, v in sorted(by_plan.items())) or "n/a"
    top_lines = ", ".join(f"{k}:{v:.2f}" for k, v in top_plans) or "n/a"
    return (
        "💼 Admin Finance (manual TON only)\n"
        f"Revenue 30d: {float(revenue_summary.get('revenue_ton', 0.0)):.2f} TON\n"
        f"MRR estimate: {mrr:.2f} TON\n"
        f"ARPU: {arpu:.2f} TON\n"
        f"Payments count 30d: {int(revenue_summary.get('payments_count', 0))}\n"
        f"Counts: confirmed={counts.get('confirmed', 0)}, rejected={counts.get('rejected', 0)}, "
        f"pending={counts.get('pending', 0)}, submitted={counts.get('submitted', 0)}\n"
        f"Revenue by plan: {plan_lines}\n"
        f"Top plans: {top_lines}\n"
        "Disclaimer: manual crypto payments only, no auto-charges."
    )
