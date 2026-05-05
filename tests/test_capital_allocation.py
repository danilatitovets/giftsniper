from types import SimpleNamespace

from app.services.capital_allocation import allocate_capital, calculate_bankroll_limits


def _user(bankroll=500, max_deal=25, max_collection=40, reserve=20):
    return SimpleNamespace(
        bankroll_ton=bankroll,
        max_deal_percent=max_deal,
        max_collection_percent=max_collection,
        reserve_percent=reserve,
    )


def _opp(price=100, tier="A_TIER", score=75, freshness="fresh", real_sales=1):
    listing = SimpleNamespace(collection="Ice Cream", number=1, price_ton=price)
    estimate = SimpleNamespace(expected_profit_ton=20.0)
    score_obj = SimpleNamespace(final_rank_label=tier, total_score=score)
    return {
        "listing": listing,
        "estimate": estimate,
        "score": score_obj,
        "freshness_label": freshness,
        "real_sales_count": real_sales,
    }


def test_bankroll_limits_calculation():
    limits = calculate_bankroll_limits(_user())
    assert limits["reserve_ton"] == 100.0
    assert limits["max_per_deal_ton"] == 125.0
    assert limits["max_per_collection_ton"] == 200.0


def test_allocation_skips_low_tier():
    plan = allocate_capital([_opp(tier="C_TIER")], _user(), [])
    assert not plan.selected_opportunities
    assert plan.skipped_opportunities


def test_allocation_respects_max_deal_percent():
    plan = allocate_capital([_opp(price=170)], _user(), [])
    assert not plan.selected_opportunities
    assert "max per deal" in plan.skipped_opportunities[0].reason


def test_allocation_respects_collection_exposure():
    plan = allocate_capital([_opp(price=90)], _user(), [{"collection": "Ice Cream", "value_ton": 180.0}])
    assert not plan.selected_opportunities
    assert "Лимит по коллекции" in plan.skipped_opportunities[0].reason


def test_downside_scenario_present():
    plan = allocate_capital([_opp(price=100, tier="A_TIER")], _user(), [])
    assert "-10%" in plan.downside_scenario_ton
    assert "-25%" in plan.downside_scenario_ton
    assert "-40%" in plan.downside_scenario_ton
