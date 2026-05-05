from datetime import datetime, timedelta

import pytest

from app.services.entitlements import (
    format_entitlement_status,
    get_effective_entitlement,
    has_active_entitlement,
)


class _Session:
    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_override_priority(monkeypatch):
    user = type("U", (), {"id": 1, "plan": "starter", "is_blocked": False})()

    class _Repo:
        def __init__(self, _s):
            pass

        async def get_active_override(self, _uid, _now):
            return type("O", (), {"plan": "trader", "expires_at": None})()

        async def get_entitlement(self, _uid):
            return type("E", (), {"plan": "pro", "status": "active", "source": "admin", "expires_at": None, "grace_until": None})()

    monkeypatch.setattr("app.services.entitlements.BillingRepository", _Repo)
    ent = await get_effective_entitlement(_Session(), user)
    assert ent["plan"] == "trader"
    assert ent["status"] == "manual"


@pytest.mark.asyncio
async def test_expired_entitlement_downgrades_to_free(monkeypatch):
    user = type("U", (), {"id": 2, "plan": "pro", "is_blocked": False})()
    old = datetime.utcnow() - timedelta(days=1)

    class _Repo:
        def __init__(self, _s):
            pass

        async def get_active_override(self, _uid, _now):
            return None

        async def get_entitlement(self, _uid):
            return type("E", (), {"plan": "pro", "status": "expired", "source": "provider", "expires_at": old, "grace_until": old})()

    monkeypatch.setattr("app.services.entitlements.BillingRepository", _Repo)
    ent = await get_effective_entitlement(_Session(), user)
    assert ent["plan"] == "free"


@pytest.mark.asyncio
async def test_grace_period_status(monkeypatch):
    user = type("U", (), {"id": 3, "plan": "pro", "is_blocked": False})()
    exp = datetime.utcnow() - timedelta(minutes=1)
    grace = datetime.utcnow() + timedelta(days=2)

    class _Repo:
        def __init__(self, _s):
            pass

        async def get_active_override(self, _uid, _now):
            return None

        async def get_entitlement(self, _uid):
            return type("E", (), {"plan": "pro", "status": "grace", "source": "provider", "expires_at": exp, "grace_until": grace})()

    monkeypatch.setattr("app.services.entitlements.BillingRepository", _Repo)
    ent = await get_effective_entitlement(_Session(), user)
    assert ent["status"] == "grace"
    assert ent["plan"] == "pro"


@pytest.mark.asyncio
async def test_blocked_user_still_blocked(monkeypatch):
    user = type("U", (), {"id": 4, "plan": "pro", "is_blocked": True})()
    assert await has_active_entitlement(_Session(), user, "scan_universe") is False


def test_my_plan_format_contains_fields():
    user = type("U", (), {"is_blocked": False})()
    text = format_entitlement_status(user, {"plan": "pro", "status": "active", "source": "admin", "expires_at": None, "grace_until": None})
    assert "Plan:" in text
    assert "Status:" in text
