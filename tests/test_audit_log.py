import pytest

from app.services.audit import log_audit


class _FakeSession:
    pass


@pytest.mark.asyncio
async def test_audit_log_records_plan_change(monkeypatch):
    called = {}

    class _FakeRepo:
        def __init__(self, _session):
            pass

        async def create(self, **kwargs):
            called.update(kwargs)
            return object()

    monkeypatch.setattr("app.services.audit.AuditLogRepository", _FakeRepo)
    await log_audit(
        _FakeSession(),
        user_id=1,
        action="admin_set_plan",
        entity_type="user",
        entity_id="1",
        metadata_json={"plan": "pro"},
    )
    assert called["action"] == "admin_set_plan"
    assert called["metadata_json"]["plan"] == "pro"
