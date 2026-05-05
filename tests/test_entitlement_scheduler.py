from datetime import datetime, timedelta

import pytest

from app.services.entitlements import downgrade_expired_users


class _Session:
    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_scheduler_transitions_active_to_grace_and_expired(monkeypatch):
    now = datetime.utcnow()
    ent_active = type(
        "E",
        (),
        {"user_id": 1, "status": "active", "plan": "pro", "expires_at": now - timedelta(minutes=1), "grace_until": None, "last_checked_at": None},
    )()
    ent_grace = type(
        "E",
        (),
        {"user_id": 2, "status": "grace", "plan": "pro", "expires_at": now - timedelta(days=5), "grace_until": now - timedelta(minutes=1), "last_checked_at": None},
    )()

    class _BillingRepo:
        def __init__(self, _session):
            pass

        async def list_expiration_candidates(self):
            return [ent_active, ent_grace]

        async def create_billing_event(self, **kwargs):
            return object()

    class _UsersRepo:
        def __init__(self, _session):
            pass

        async def set_plan(self, _uid, _plan, _expires):
            return object()

    monkeypatch.setattr("app.services.entitlements.BillingRepository", _BillingRepo)
    monkeypatch.setattr("app.services.entitlements.UserRepository", _UsersRepo)
    changed = await downgrade_expired_users(_Session())
    assert 1 in changed
    assert 2 in changed
    assert ent_active.status == "grace"
    assert ent_grace.status == "expired"
