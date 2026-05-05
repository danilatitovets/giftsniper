import pytest

from app.bot.handlers.admin import release_check_handler


class _Msg:
    text = "/release_check"
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
async def test_release_check_no_go_when_owner_wallet_missing(monkeypatch):
    async def _req(_):
        return type("A", (), {"id": 1, "role": "admin"})()

    async def _snapshot(_session, _settings):
        return {"status": "NO_GO", "checks": [("OWNER_CRYPTO_WALLET_TON", "block", "missing")]}

    settings = type("S", (), {})()
    monkeypatch.setattr("app.bot.handlers.admin._require_admin", _req)
    monkeypatch.setattr("app.bot.handlers.admin.get_settings", lambda: settings)
    monkeypatch.setattr("app.bot.handlers.admin.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.admin._release_check_snapshot", _snapshot)
    msg = _Msg()
    await release_check_handler(msg)
    assert "NO_GO" in msg.out[0]


@pytest.mark.asyncio
async def test_release_check_go_with_warnings_optional_api(monkeypatch):
    async def _req(_):
        return type("A", (), {"id": 1, "role": "admin"})()

    async def _snapshot(_session, _settings):
        return {"status": "GO_WITH_WARNINGS", "checks": [("TONAPI_API_KEY", "warn", "missing")]}

    settings = type("S", (), {})()
    monkeypatch.setattr("app.bot.handlers.admin._require_admin", _req)
    monkeypatch.setattr("app.bot.handlers.admin.get_settings", lambda: settings)
    monkeypatch.setattr("app.bot.handlers.admin.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.admin._release_check_snapshot", _snapshot)
    msg = _Msg()
    await release_check_handler(msg)
    assert "GO_WITH_WARNINGS" in msg.out[0]
