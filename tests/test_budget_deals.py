from app.services.capital_multiplier import CapitalMultiplierPlan, FlipCandidate, format_capital_multiplier_plan


def test_budget_deals_compact_format_still_has_core_prices():
    plan = CapitalMultiplierPlan(
        starting_budget_ton=100,
        reserve_ton=20,
        available_after_reserve_ton=80,
        max_per_deal_ton=25,
        max_speculative_deal_ton=15,
        selected_candidates=[
            FlipCandidate(
                collection="C",
                number=1,
                buy_price_ton=20,
                max_buy_price_ton=25,
                safe_buy_price_ton=22,
                list_price_ton=30,
                high_list_price_ton=32,
                quick_sell_price_ton=28,
                stop_loss_price_ton=18,
                expected_profit_ton=5,
                expected_roi_percent=25,
                sale_probability_percent=60.0,
                capital_efficiency_score=35.0,
                risk_score=50,
                confidence_score=65,
            )
        ],
    )
    t = format_capital_multiplier_plan(plan, compact=True)
    assert "Quick sell" in t
    assert "max buy" in t.lower() or "Купить до" in t
