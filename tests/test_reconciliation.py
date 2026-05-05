import pytest

from app.services.reconciliation import (
    find_confirmed_without_entitlement,
    find_entitlement_without_payment,
    find_expired_entitlement_with_active_plan,
    find_payment_event_mismatch,
)


class _Session:
    def __init__(self, rows):
        self.rows = rows

    async def scalars(self, _stmt):
        class _Res:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        return _Res(self.rows)


@pytest.mark.asyncio
async def test_reconciliation_finders():
    rows = [type("R", (), {"id": 1})()]
    s = _Session(rows)
    a = await find_confirmed_without_entitlement(s)
    b = await find_entitlement_without_payment(s)
    c = await find_payment_event_mismatch(s)
    d = await find_expired_entitlement_with_active_plan(s)
    assert len(a) == 1
    assert len(b) == 1
    assert len(c) == 1
    assert len(d) == 1
