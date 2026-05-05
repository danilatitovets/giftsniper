from datetime import datetime

import pytest

from app.services.manual_payments import create_payment_request, format_payment_instructions, submit_payment_proof


class _Session:
    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_pay_creates_pending_payment_request(monkeypatch):
    class _Repo:
        def __init__(self, _s):
            pass

        async def create_payment_request(self, **kwargs):
            return type("R", (), {"id": 1, "status": "pending", **kwargs})()

    monkeypatch.setattr("app.services.manual_payments.ManualPaymentRepository", _Repo)
    monkeypatch.setattr(
        "app.services.manual_payments.get_settings",
        lambda: type(
            "S",
            (),
            {
                "manual_payment_starter_ton": 10,
                "manual_payment_pro_ton": 25,
                "manual_payment_trader_ton": 60,
                "manual_payment_default_currency": "TON",
                "owner_crypto_wallet_ton": "UQBE72wYg608Yc6SfddpPI-_3A0f8Gv9Ap3zjr5f7xu5yec8",
            },
        )(),
    )
    row = await create_payment_request(_Session(), 1, "pro")
    assert row.status == "pending"
    assert row.requested_plan == "pro"


@pytest.mark.asyncio
async def test_payment_sent_moves_to_submitted(monkeypatch):
    class _Repo:
        def __init__(self, _s):
            pass

        async def get_by_tx_hash(self, _tx):
            return None

        async def submit_payment_proof(self, _u, _r, _proof):
            return type("R", (), {"status": "submitted"})()

    monkeypatch.setattr("app.services.manual_payments.ManualPaymentRepository", _Repo)
    row = await submit_payment_proof(_Session(), 1, 1, "tx123")
    assert row.status == "submitted"


def test_wallet_shown_private_keys_not_shown():
    req = type("R", (), {"id": 1, "requested_plan": "pro", "amount": 25.0, "currency": "TON"})()
    txt = format_payment_instructions(req, "UQBE72wYg608Yc6SfddpPI-_3A0f8Gv9Ap3zjr5f7xu5yec8").lower()
    assert "uqbe72wyg608yc6sfddppi-_3a0f8gv9ap3zjr5f7xu5yec8" in txt
    assert "private key" in txt


@pytest.mark.asyncio
async def test_duplicate_tx_hash_handled(monkeypatch):
    existing = type("R", (), {"id": 2})()

    class _Repo:
        def __init__(self, _s):
            pass

        async def get_by_tx_hash(self, _tx):
            return existing

    monkeypatch.setattr("app.services.manual_payments.ManualPaymentRepository", _Repo)
    with pytest.raises(ValueError):
        await submit_payment_proof(_Session(), 1, 1, "tx123")
