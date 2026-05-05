from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.db.repositories.billing import BillingRepository
from app.db.repositories.users import UserRepository


def _to_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def get_effective_entitlement(session, user) -> dict:
    now = datetime.now(timezone.utc)
    repo = BillingRepository(session)
    override = await repo.get_active_override(user.id, now)
    if override is not None:
        return {
            "plan": override.plan,
            "status": "manual",
            "source": "admin_override",
            "expires_at": override.expires_at,
            "grace_until": None,
            "is_override": True,
        }
    ent = await repo.get_entitlement(user.id)
    if ent is None:
        return {
            "plan": "free",
            "status": "expired",
            "source": "none",
            "expires_at": None,
            "grace_until": None,
            "is_override": False,
        }
    status = ent.status
    plan = ent.plan
    expires_at = _to_aware(ent.expires_at)
    grace_until = _to_aware(ent.grace_until)
    if ent.status in {"active", "trialing", "canceled"} and expires_at and expires_at <= now:
        status = "grace"
        plan = ent.plan
    if ent.status == "grace" and grace_until and grace_until <= now:
        status = "expired"
        plan = "free"
    if ent.status in {"expired"}:
        plan = "free"
    return {
        "plan": plan,
        "status": status,
        "source": ent.source,
        "expires_at": ent.expires_at,
        "grace_until": ent.grace_until,
        "is_override": False,
    }


async def sync_user_plan_from_entitlement(session, user):
    effective = await get_effective_entitlement(session, user)
    desired_plan = effective["plan"]
    if user.plan != desired_plan:
        await UserRepository(session).set_plan(user.id, desired_plan, effective.get("expires_at"))
        user.plan = desired_plan
    user.effective_plan = desired_plan
    user.entitlement_status = effective["status"]
    return effective


async def grant_entitlement(session, user_id: int, plan: str, source: str, expires_at: datetime | None, reason: str | None = None):
    now = datetime.now(timezone.utc)
    repo = BillingRepository(session)
    row = await repo.upsert_entitlement(
        user_id=user_id,
        plan=plan,
        status="active",
        source=source,
        starts_at=now,
        expires_at=expires_at,
        grace_until=None,
        canceled_at=None,
        last_checked_at=now,
    )
    await repo.create_billing_event(
        user_id=user_id,
        event_type="grant",
        provider=get_settings().billing_provider,
        plan=plan,
        status="active",
        metadata_json=reason,
    )
    user = await UserRepository(session).get_by_id(user_id)
    if user is not None:
        await sync_user_plan_from_entitlement(session, user)
    return row


async def cancel_entitlement(session, user_id: int, reason: str | None):
    repo = BillingRepository(session)
    ent = await repo.get_entitlement(user_id)
    if ent is None:
        return None
    ent.status = "canceled"
    ent.canceled_at = datetime.now(timezone.utc)
    await session.commit()
    await repo.create_billing_event(
        user_id=user_id,
        event_type="cancel",
        provider=get_settings().billing_provider,
        plan=ent.plan,
        status="canceled",
        metadata_json=reason,
    )
    return ent


async def apply_grace_period(session, user_id: int):
    settings = get_settings()
    repo = BillingRepository(session)
    ent = await repo.get_entitlement(user_id)
    if ent is None:
        return None
    ent.status = "grace"
    ent.grace_until = datetime.now(timezone.utc) + timedelta(days=settings.billing_grace_period_days)
    ent.last_checked_at = datetime.now(timezone.utc)
    await session.commit()
    await repo.create_billing_event(
        user_id=user_id,
        event_type="grace_started",
        provider=settings.billing_provider,
        plan=ent.plan,
        status="grace",
    )
    return ent


async def expire_entitlement(session, user_id: int):
    repo = BillingRepository(session)
    ent = await repo.get_entitlement(user_id)
    if ent is None:
        return None
    ent.status = "expired"
    ent.last_checked_at = datetime.now(timezone.utc)
    await session.commit()
    await repo.create_billing_event(
        user_id=user_id,
        event_type="expired",
        provider=get_settings().billing_provider,
        plan=ent.plan,
        status="expired",
    )
    user = await UserRepository(session).get_by_id(user_id)
    if user is not None:
        await UserRepository(session).set_plan(user.id, "free", None)
    return ent


async def downgrade_expired_users(session) -> list[int]:
    now = datetime.now(timezone.utc)
    repo = BillingRepository(session)
    users_repo = UserRepository(session)
    changed: list[int] = []
    for ent in await repo.list_expiration_candidates():
        updated = False
        expires_at = _to_aware(ent.expires_at)
        grace_until = _to_aware(ent.grace_until)
        if ent.status in {"active", "trialing", "canceled"} and expires_at and expires_at <= now:
            ent.status = "grace"
            ent.grace_until = now + timedelta(days=get_settings().billing_grace_period_days)
            updated = True
            await repo.create_billing_event(user_id=ent.user_id, event_type="grace_started", provider=get_settings().billing_provider, plan=ent.plan, status="grace")
        elif ent.status == "grace" and grace_until and grace_until <= now:
            ent.status = "expired"
            updated = True
            await users_repo.set_plan(ent.user_id, "free", None)
            await repo.create_billing_event(user_id=ent.user_id, event_type="downgraded_free", provider=get_settings().billing_provider, plan="free", status="expired")
        ent.last_checked_at = now
        if updated:
            changed.append(ent.user_id)
    await session.commit()
    return changed


async def has_active_entitlement(session, user, feature: str) -> bool:
    if user.is_blocked:
        return False
    effective = await get_effective_entitlement(session, user)
    user.effective_plan = effective["plan"]
    return effective["status"] in {"active", "trialing", "grace", "manual"}


def format_entitlement_status(user, entitlement: dict) -> str:
    return (
        f"Plan: {entitlement['plan']}\n"
        f"Status: {entitlement['status']}\n"
        f"Source: {entitlement['source']}\n"
        f"Expires: {entitlement.get('expires_at') or 'n/a'}\n"
        f"Grace until: {entitlement.get('grace_until') or 'n/a'}\n"
        f"Blocked: {user.is_blocked}"
    )
