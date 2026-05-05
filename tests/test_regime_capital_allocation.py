from types import SimpleNamespace

from app.services.capital_allocation import allocate_capital_dynamic


def _user():
    return SimpleNamespace(bankroll_ton=500, reserve_percent=20, max_deal_percent=25, max_collection_percent=40)


def _opp(tier="A_TIER"):
    return {
        "listing": SimpleNamespace(collection="Ice Cream", number=1, price_ton=100),
        "estimate": SimpleNamespace(expected_profit_ton=20, confidence_score=70, risk_score=40),
        "score": SimpleNamespace(final_rank_label=tier, total_score=78),
        "real_sales_count": 2,
        "freshness_label": "fresh",
    }


def test_risk_off_lowers_allocation():
    neutral = allocate_capital_dynamic([_opp()], _user(), [], regime="neutral")
    risk_off = allocate_capital_dynamic([_opp()], _user(), [], regime="risk_off")
    assert neutral.selected_opportunities[0].allocated_ton > risk_off.selected_opportunities[0].allocated_ton


def test_data_poor_blocks_aggressive_buy():
    plan = allocate_capital_dynamic([_opp(tier="B_TIER")], _user(), [], regime="data_poor")
    assert len(plan.selected_opportunities) == 0
