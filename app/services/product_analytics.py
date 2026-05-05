from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BetaInviteRedemption, FeedbackItem, ManualPaymentRequest, ProductEvent, User

ACTIVATION_COMMANDS = {"/add", "/check", "/deal", "/deals", "/portfolio", "/bank_set", "/redeem"}


def _since(period_days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=period_days)


async def calculate_activation_metrics(session: AsyncSession, period_days: int = 7) -> dict:
    since = _since(period_days)
    new_users = int(await session.scalar(select(func.count(User.id)).where(User.created_at >= since)) or 0)
    active_users = int(await session.scalar(select(func.count(func.distinct(ProductEvent.user_id))).where(ProductEvent.created_at >= since, ProductEvent.user_id.is_not(None))) or 0)

    rows = (
        await session.execute(
            select(ProductEvent.user_id, ProductEvent.command)
            .where(ProductEvent.created_at >= since, ProductEvent.user_id.is_not(None), ProductEvent.command.is_not(None))
        )
    ).all()
    by_user: dict[int, set[str]] = {}
    for user_id, command in rows:
        if command in ACTIVATION_COMMANDS:
            by_user.setdefault(int(user_id), set()).add(str(command))
    activated_users = len([uid for uid, cmds in by_user.items() if len(cmds) >= 2])
    activation_rate = (activated_users / new_users) if new_users else 0.0
    return {
        "period_days": period_days,
        "new_users": new_users,
        "active_users": active_users,
        "activated_users": activated_users,
        "activation_rate": activation_rate,
    }


async def calculate_retention_metrics(session: AsyncSession, period_days: int = 7) -> dict:
    since = _since(period_days)
    prev_since = since - timedelta(days=period_days)
    prev_active_rows = (
        await session.execute(
            select(func.distinct(ProductEvent.user_id)).where(
                ProductEvent.created_at >= prev_since,
                ProductEvent.created_at < since,
                ProductEvent.user_id.is_not(None),
            )
        )
    ).all()
    current_active_rows = (
        await session.execute(
            select(func.distinct(ProductEvent.user_id)).where(ProductEvent.created_at >= since, ProductEvent.user_id.is_not(None))
        )
    ).all()
    prev_active = {int(x[0]) for x in prev_active_rows if x[0] is not None}
    current_active = {int(x[0]) for x in current_active_rows if x[0] is not None}
    retained = len(prev_active.intersection(current_active))
    retention_rate = (retained / len(prev_active)) if prev_active else 0.0
    return {"period_days": period_days, "retained_users": retained, "retention_rate": retention_rate, "previous_active_users": len(prev_active)}


async def calculate_funnel_metrics(session: AsyncSession, period_days: int = 7) -> dict:
    since = _since(period_days)
    return {
        "invite_redeemed": int(await session.scalar(select(func.count(BetaInviteRedemption.id)).where(BetaInviteRedemption.redeemed_at >= since)) or 0),
        "checked_gift": int(await session.scalar(select(func.count(ProductEvent.id)).where(ProductEvent.created_at >= since, ProductEvent.event_type == "check_used")) or 0),
        "added_gift": int(await session.scalar(select(func.count(ProductEvent.id)).where(ProductEvent.created_at >= since, ProductEvent.event_type == "gift_added")) or 0),
        "upgrade_viewed": int(await session.scalar(select(func.count(ProductEvent.id)).where(ProductEvent.created_at >= since, ProductEvent.event_type == "upgrade_viewed")) or 0),
        "pay_started": int(await session.scalar(select(func.count(ProductEvent.id)).where(ProductEvent.created_at >= since, ProductEvent.event_type == "pay_started")) or 0),
        "payment_submitted": int(
            await session.scalar(
                select(func.count(ProductEvent.id)).where(ProductEvent.created_at >= since, ProductEvent.event_type == "payment_submitted")
            )
            or 0
        ),
        "feedback_count": int(await session.scalar(select(func.count(FeedbackItem.id)).where(FeedbackItem.created_at >= since)) or 0),
    }


async def calculate_feature_usage(session: AsyncSession, period_days: int = 7) -> dict:
    since = _since(period_days)
    rows = (
        await session.execute(
            select(ProductEvent.command, func.count(ProductEvent.id))
            .where(ProductEvent.created_at >= since, ProductEvent.command.is_not(None))
            .group_by(ProductEvent.command)
            .order_by(func.count(ProductEvent.id).desc())
            .limit(5)
        )
    ).all()
    return {"top_commands": [(str(command), int(count)) for command, count in rows]}


async def calculate_payment_ops_metrics(session: AsyncSession, period_days: int = 7) -> dict:
    since = _since(period_days)
    stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    submitted = await session.scalar(
        select(func.count(ManualPaymentRequest.id)).where(ManualPaymentRequest.created_at >= since, ManualPaymentRequest.status == "submitted")
    )
    stale = await session.scalar(
        select(func.count(ManualPaymentRequest.id)).where(ManualPaymentRequest.status == "submitted", ManualPaymentRequest.created_at < stale_cutoff)
    )
    return {"submitted_7d": int(submitted or 0), "stale_submitted_48h": int(stale or 0)}


def format_beta_metrics_report(*, activation: dict, retention: dict, funnel: dict, feature: dict) -> str:
    top = feature.get("top_commands", [])
    top_lines = "\n".join([f"{idx + 1}. {cmd} — {cnt}" for idx, (cmd, cnt) in enumerate(top)]) or "- none"
    return (
        f"📈 Beta Metrics — {activation['period_days']} days\n\n"
        f"New users: {activation['new_users']}\n"
        f"Active users: {activation['active_users']}\n"
        f"Activated: {activation['activated_users']}\n"
        f"Activation rate: {activation['activation_rate'] * 100:.0f}%\n"
        f"Retained users: {retention['retained_users']}\n\n"
        "Funnel:\n"
        f"Invite redeemed: {funnel['invite_redeemed']}\n"
        f"Checked gift: {funnel['checked_gift']}\n"
        f"Added gift: {funnel['added_gift']}\n"
        f"Opened upgrade: {funnel['upgrade_viewed']}\n"
        f"Started payment: {funnel['pay_started']}\n"
        f"Payment submitted: {funnel['payment_submitted']}\n"
        f"Feedback count: {funnel['feedback_count']}\n\n"
        "Top commands:\n"
        f"{top_lines}"
    )
