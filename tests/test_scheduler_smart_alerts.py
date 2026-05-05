import pytest

from app.services.scheduler import check_smart_alerts_job


class _FailingUsersRepo:
    async def list_all(self):
        raise RuntimeError("boom")


class _Bot:
    async def send_message(self, chat_id, text):  # noqa: ARG002
        return None


@pytest.mark.asyncio
async def test_scheduler_error_isolation(monkeypatch):
    class _Session:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr("app.services.scheduler.UserRepository", lambda session: _FailingUsersRepo())  # noqa: ARG005
    monkeypatch.setattr("app.services.scheduler.AlertRepository", lambda session: object())  # noqa: ARG005
    monkeypatch.setattr("app.services.scheduler.GiftRepository", lambda session: object())  # noqa: ARG005
    await check_smart_alerts_job(_Bot(), lambda: _Session(), type("S", (), {})())
