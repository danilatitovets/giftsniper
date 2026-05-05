import pytest

from app.bot.handlers.admin import pay_handler
from app.bot.handlers.ton_upgrade import upgrade_command
from app.config import Settings


class _Msg:
    from_user = type("U", (), {"id": 1, "username": "u"})()

    def __init__(self, text):
        self.text = text
        self.out = []

    async def answer(self, text, **kwargs):
        self.out.append(text)


class _Ctx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_pay_contains_wallet_request_and_payment_sent(monkeypatch):
    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    async def _create(*_args, **_kwargs):
        return type("R", (), {"id": 88, "requested_plan": "pro", "amount": 25.0, "currency": "TON"})()

    settings = type(
        "S",
        (),
        {"manual_payment_enabled": True, "owner_crypto_wallet_ton": "UQ123", "billing_enabled": False},
    )()
    monkeypatch.setattr("app.bot.handlers.admin.get_settings", lambda: settings)
    monkeypatch.setattr("app.bot.handlers.admin.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.admin.UserRepository", _Users)
    monkeypatch.setattr("app.bot.handlers.admin.create_payment_request", _create)
    msg = _Msg("/pay pro")
    await pay_handler(msg)
    assert "Wallet" in msg.out[0]
    assert "/payment_sent 88" in msg.out[0]


@pytest.mark.asyncio
async def test_upgrade_text_no_automatic_access_promise(monkeypatch):
    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    st = Settings(BOT_TOKEN="x", DATABASE_URL="postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setattr("app.bot.handlers.ton_upgrade.get_settings", lambda: st)
    monkeypatch.setattr("app.bot.handlers.ton_upgrade.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.ton_upgrade.UserRepository", _Users)
    msg = _Msg("/upgrade")
    await upgrade_command(msg)
    blob = "\n".join(msg.out)
    assert "0 TON" in blob or "Preview" in blob
    low = blob.lower()
    assert "автоспис" not in low
