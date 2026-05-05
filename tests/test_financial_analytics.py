import pytest

from app.services.financial_analytics import (
    calculate_arpu,
    calculate_mrr,
    calculate_revenue_summary,
    conversion_summary,
    revenue_by_plan,
)


class _ScalarSession:
    def __init__(self):
        self.values = [120.0, 4, 120.0, 4, 120.0, 4, 3]

    async def scalar(self, _stmt):
        return self.values.pop(0)

    async def execute(self, _stmt):
        class _Exec:
            def all(self):
                return [("confirmed", 4), ("pending", 2), ("rejected", 1), ("submitted", 1)]

        return _Exec()


@pytest.mark.asyncio
async def test_finance_revenue_mrr_arpu_and_conversion():
    s = _ScalarSession()
    summary = await calculate_revenue_summary(s, period_days=30)
    mrr = await calculate_mrr(s)
    arpu = await calculate_arpu(s, period_days=30)
    conv = await conversion_summary(s, period_days=30)
    assert summary["revenue_ton"] == 120.0
    assert mrr == 120.0
    assert arpu == 40.0
    assert conv["counts"]["confirmed"] == 4


@pytest.mark.asyncio
async def test_revenue_by_plan():
    class _S:
        async def execute(self, _stmt):
            class _Exec:
                def all(self):
                    return [("pro", 100.0), ("trader", 50.0)]

            return _Exec()

    result = await revenue_by_plan(_S(), period_days=30)
    assert result["pro"] == 100.0
