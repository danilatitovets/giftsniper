import pytest

from app.bot.handlers.admin import beta_launch_check_handler, beta_smoke_plan_handler, smoke_suite_handler


class _Msg:
    from_user = type("U", (), {"id": 1, "username": "a"})()

    def __init__(self, text: str):
        self.text = text
        self.out: list[str] = []

    async def answer(self, t: str, **kwargs):
        self.out.append(t)


@pytest.mark.asyncio
async def test_beta_launch_check_requires_admin(monkeypatch):
    async def _deny(_):
        return None

    monkeypatch.setattr("app.bot.handlers.admin._require_admin", _deny)
    msg = _Msg("/beta_launch_check")
    await beta_launch_check_handler(msg)
    assert msg.out == []


@pytest.mark.asyncio
async def test_beta_smoke_plan_requires_admin(monkeypatch):
    async def _deny(_):
        return None

    monkeypatch.setattr("app.bot.handlers.admin._require_admin", _deny)
    msg = _Msg("/beta_smoke_plan")
    await beta_smoke_plan_handler(msg)
    assert msg.out == []


@pytest.mark.asyncio
async def test_smoke_suite_requires_admin(monkeypatch):
    async def _deny(_):
        return None

    monkeypatch.setattr("app.bot.handlers.admin._require_admin", _deny)
    msg = _Msg("/smoke_suite")
    await smoke_suite_handler(msg)
    assert msg.out == []
