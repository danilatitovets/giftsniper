from datetime import datetime, timedelta

import pytest

from app.services.entitlements import grant_entitlement


class _Session:
    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_admin_grant_plan_creates_entitlement_and_event(monkeypatch):
    calls = {"event": 0, "upsert": 0}

    class _BillingRepo:
        def __init__(self, _session):
            pass

        async def get_active_override(self, _uid, _now):
            return None

        async def get_entitlement(self, _uid):
            return type("E", (), {"plan": "pro", "status": "active", "source": "admin", "expires_at": None, "grace_until": None})()

        async def upsert_entitlement(self, **kwargs):
            calls["upsert"] += 1
            return type("E", (), kwargs)()

        async def create_billing_event(self, **kwargs):
            calls["event"] += 1
            return object()

    class _UsersRepo:
        def __init__(self, _session):
            pass

        async def get_by_id(self, _uid):
            return type("U", (), {"id": 1, "plan": "free"})()

        async def set_plan(self, _uid, _plan, _expires):
            return object()

    monkeypatch.setattr("app.services.entitlements.BillingRepository", _BillingRepo)
    monkeypatch.setattr("app.services.entitlements.UserRepository", _UsersRepo)
    await grant_entitlement(_Session(), 1, "pro", "admin", datetime.utcnow() + timedelta(days=30), "beta")
    assert calls["upsert"] == 1
    assert calls["event"] == 1
