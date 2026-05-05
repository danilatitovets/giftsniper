from types import SimpleNamespace

from app.services.capital_allocation import allocate_capital_dynamic


def _user():
    return SimpleNamespace(bankroll_ton=500, reserve_percent=20, max_deal_percent=25, max_collection_percent=40)


def _op(tier="A_TIER", price=100, conf=70, risk=40, sales=1, freshness="fresh", score=75):
    return {
        "listing": SimpleNamespace(collection="Ice Cream", number=1, price_ton=price),
        "estimate": SimpleNamespace(expected_profit_ton=20, confidence_score=conf, risk_score=risk),
        "score": SimpleNamespace(final_rank_label=tier, total_score=score),
        "real_sales_count": sales,
        "freshness_label": freshness,
    }


def test_s_tier_gets_larger_allocation_than_b_tier():
    plan_s = allocate_capital_dynamic([_op(tier="S_TIER")], _user(), [])
    plan_b = allocate_capital_dynamic([_op(tier="B_TIER")], _user(), [])
    assert plan_s.selected_opportunities[0].allocated_ton > plan_b.selected_opportunities[0].allocated_ton


def test_stale_data_reduces_allocation():
    fresh = allocate_capital_dynamic([_op(freshness="fresh")], _user(), [])
    stale = allocate_capital_dynamic([_op(freshness="stale")], _user(), [])
    assert fresh.selected_opportunities[0].allocated_ton >= stale.selected_opportunities[0].allocated_ton


def test_no_sales_reduces_allocation():
    with_sales = allocate_capital_dynamic([_op(sales=2)], _user(), [])
    no_sales = allocate_capital_dynamic([_op(sales=0)], _user(), [])
    assert with_sales.selected_opportunities[0].allocated_ton >= no_sales.selected_opportunities[0].allocated_ton


def test_capital_plan_universe_skips_low_tier():
    plan = allocate_capital_dynamic([_op(tier="C_TIER"), _op(tier="AVOID")], _user(), [])
    assert len(plan.selected_opportunities) == 0
