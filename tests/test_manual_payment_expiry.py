from datetime import datetime, timedelta, timezone

import pytest

from app.services.manual_payments import expire_old_pending_requests, list_stale_submitted_requests


class _Session:
    pass


@pytest.mark.asyncio
async def test_pending_older_ttl_expires_and_logs(monkeypatch):
    expired_row = type("R", (), {"id": 12, "user_id": 3, "requested_plan": "pro", "amount": 25.0, "currency": "TON"})()
    calls = {"billing": 0, "audit": 0}

    class _Repo:
        def __init__(self, _s):
            pass

        async def expire_pending_older_than(self, _older_than):
            return [expired_row]

    class _Billing:
        def __init__(self, _s):
            pass

        async def create_billing_event(self, **kwargs):
            calls["billing"] += 1
            return kwargs

    async def _audit(*args, **kwargs):
        calls["audit"] += 1

    monkeypatch.setattr("app.services.manual_payments.ManualPaymentRepository", _Repo)
    monkeypatch.setattr("app.services.manual_payments.BillingRepository", _Billing)
    monkeypatch.setattr("app.services.manual_payments.log_audit", _audit)
    monkeypatch.setattr(
        "app.services.manual_payments.get_settings",
        lambda: type("S", (), {"manual_payment_request_ttl_hours": 24, "manual_payment_submitted_sla_hours": 6})(),
    )
    rows = await expire_old_pending_requests(_Session())
    assert len(rows) == 1
    assert calls["billing"] == 1
    assert calls["audit"] == 1


@pytest.mark.asyncio
async def test_submitted_older_sla_listed_as_stale(monkeypatch):
    row = type("R", (), {"id": 7, "status": "submitted", "created_at": datetime.now(timezone.utc) - timedelta(hours=7)})()

    class _Repo:
        def __init__(self, _s):
            pass

        async def list_stale_submitted(self, _older_than):
            return [row]

    monkeypatch.setattr("app.services.manual_payments.ManualPaymentRepository", _Repo)
    monkeypatch.setattr(
        "app.services.manual_payments.get_settings",
        lambda: type("S", (), {"manual_payment_submitted_sla_hours": 6})(),
    )
    rows = await list_stale_submitted_requests(_Session())
    assert rows and rows[0].id == 7
