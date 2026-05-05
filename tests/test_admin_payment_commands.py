import pytest

from app.services.manual_payments import confirm_payment_request, reject_payment_request


class _Session:
    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_admin_confirm_payment_grants_entitlement_and_events(monkeypatch):
    called = {"grant": 0, "billing": 0, "audit": 0}
    row = type("R", (), {"id": 1, "user_id": 10, "requested_plan": "pro", "amount": 25.0, "currency": "TON", "tx_hash": "tx", "proof_text": None})()

    class _Repo:
        def __init__(self, _s):
            pass

        async def confirm_payment_request(self, *_):
            return row

    class _BillingRepo:
        def __init__(self, _s):
            pass

        async def create_billing_event(self, **kwargs):
            called["billing"] += 1
            return object()

    class _UsersRepo:
        def __init__(self, _s):
            pass

        async def get_by_id(self, _id):
            return type("U", (), {"id": _id, "plan": "free"})()

    async def _grant(*args, **kwargs):
        called["grant"] += 1
        return object()

    async def _sync(*args, **kwargs):
        return {}

    async def _audit(*args, **kwargs):
        called["audit"] += 1

    monkeypatch.setattr("app.services.manual_payments.ManualPaymentRepository", _Repo)
    monkeypatch.setattr("app.services.manual_payments.BillingRepository", _BillingRepo)
    monkeypatch.setattr("app.services.manual_payments.UserRepository", _UsersRepo)
    monkeypatch.setattr("app.services.manual_payments.grant_entitlement", _grant)
    monkeypatch.setattr("app.services.manual_payments.sync_user_plan_from_entitlement", _sync)
    monkeypatch.setattr("app.services.manual_payments.log_audit", _audit)
    result = await confirm_payment_request(_Session(), 100, 1, 30, "ok")
    assert result is not None
    assert called["grant"] == 1
    assert called["billing"] == 1
    assert called["audit"] == 1


@pytest.mark.asyncio
async def test_admin_reject_payment_rejects_request(monkeypatch):
    row = type("R", (), {"id": 1, "user_id": 10, "requested_plan": "pro", "amount": 25.0, "currency": "TON"})()

    class _Repo:
        def __init__(self, _s):
            pass

        async def reject_payment_request(self, *_):
            return row

    class _BillingRepo:
        def __init__(self, _s):
            pass

        async def create_billing_event(self, **kwargs):
            return object()

    async def _audit(*args, **kwargs):
        return None

    monkeypatch.setattr("app.services.manual_payments.ManualPaymentRepository", _Repo)
    monkeypatch.setattr("app.services.manual_payments.BillingRepository", _BillingRepo)
    monkeypatch.setattr("app.services.manual_payments.log_audit", _audit)
    result = await reject_payment_request(_Session(), 100, 1, "bad proof")
    assert result is not None
