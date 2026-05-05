from datetime import datetime, timezone

import pytest

from app.db.repositories.manual_payments import ManualPaymentRepository


class _Session:
    async def commit(self):
        return None

    async def refresh(self, _row):
        return None


@pytest.mark.asyncio
async def test_confirm_reject_set_review_fields(monkeypatch):
    now = datetime.now(timezone.utc)
    row1 = type("R", (), {"status": "submitted", "reviewed_at": None, "reviewed_by_user_id": None, "confirmed_by_user_id": None, "confirmed_at": None, "admin_note": None})()
    row2 = type("R", (), {"status": "submitted", "reviewed_at": None, "reviewed_by_user_id": None, "confirmed_by_user_id": None, "rejected_at": None, "admin_note": None})()

    repo = ManualPaymentRepository(_Session())

    async def _get_by_id(self, request_id):
        return row1 if request_id == 1 else row2

    monkeypatch.setattr(ManualPaymentRepository, "get_by_id", _get_by_id)
    confirmed = await repo.confirm_payment_request(101, 1, "ok")
    rejected = await repo.reject_payment_request(101, 2, "bad")
    assert confirmed.reviewed_by_user_id == 101
    assert confirmed.reviewed_at is not None and confirmed.reviewed_at >= now
    assert rejected.reviewed_by_user_id == 101
    assert rejected.reviewed_at is not None and rejected.reviewed_at >= now


@pytest.mark.asyncio
async def test_search_builds_results(monkeypatch):
    rows = [type("R", (), {"id": 1})(), type("R", (), {"id": 2})()]

    class _Session2:
        async def scalars(self, _stmt):
            class _Res:
                def all(self):
                    return rows

            return _Res()

    repo = ManualPaymentRepository(_Session2())
    result = await repo.search("txhash")
    assert len(result) == 2
