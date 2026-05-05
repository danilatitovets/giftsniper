from app.services.capital_multiplier import CapitalMultiplierPlan, format_capital_multiplier_plan
from app.services.flip_ladder import build_flip_ladder, format_flip_ladder


def test_m4_style_bundle_contains_disclaimer_fragments():
    ladder = format_flip_ladder(build_flip_ladder(300.0, 900.0, risk_mode="normal"))
    plan_text = format_capital_multiplier_plan(
        CapitalMultiplierPlan(
            starting_budget_ton=300,
            reserve_ton=60,
            available_after_reserve_ton=240,
            max_per_deal_ton=75,
            max_speculative_deal_ton=45,
        )
    )
    combo = ladder + "\n" + plan_text
    assert "сценарий" in combo.lower()
    assert "гарантированно" not in combo.lower()
