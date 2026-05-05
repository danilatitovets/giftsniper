import pytest

from app.bot.handlers.admin import owner_setup_check_handler


class _Msg:
    text = "/owner_setup_check"
    from_user = type("U", (), {"id": 1, "username": "admin"})()

    def __init__(self):
        self.out = []

    async def answer(self, text, **kwargs):
        self.out.append(text)


class _Ctx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_owner_setup_check_shows_setup_commands(monkeypatch):
    async def _req(_):
        return type("A", (), {"id": 1, "role": "admin"})()

    async def _snapshot(_session, _settings):
        return {
            "expected_owner_tg": 943071273,
            "owner_found": False,
            "role": "missing",
            "plan": "n/a",
            "entitlement": "none",
            "owner_in_admin_ids": False,
            "wallet_configured": False,
            "billing_enabled": False,
            "billing_provider": "manual",
            "beta_mode": True,
            "warnings": ["owner user not found"],
        }

    monkeypatch.setattr("app.bot.handlers.admin._require_admin", _req)
    monkeypatch.setattr("app.bot.handlers.admin._owner_setup_snapshot", _snapshot)
    monkeypatch.setattr("app.bot.handlers.admin.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.admin.get_settings", lambda: object())
    msg = _Msg()
    await owner_setup_check_handler(msg)
    assert "/admin_set_role 943071273 | owner" in msg.out[0]
