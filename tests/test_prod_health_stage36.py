import pytest

from app.bot.handlers.admin import prod_health_handler


class _Msg:
    text = "/prod_health"
    from_user = type("U", (), {"id": 1, "username": "a"})()

    def __init__(self):
        self.out: list[str] = []

    async def answer(self, t: str, **kwargs):
        self.out.append(t)


@pytest.mark.asyncio
async def test_prod_health_requires_admin(monkeypatch):
    async def _deny(_):
        return None

    monkeypatch.setattr("app.bot.handlers.admin._require_admin", _deny)
    msg = _Msg()
    await prod_health_handler(msg)
    assert msg.out == []
