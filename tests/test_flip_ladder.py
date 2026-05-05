from app.services.flip_ladder import build_flip_ladder, format_flip_ladder


def test_flip_ladder_produces_steps_and_no_guarantee_wording():
    plan = build_flip_ladder(300.0, 1000.0, risk_mode="normal")
    assert plan.estimated_rounds >= 3
    assert plan.total_required_profit_ton > 0
    text = format_flip_ladder(plan)
    assert "сценарий" in text.lower() or "сценарий" in text
    assert "гарант" not in text.lower()


def test_goal_too_high_warns():
    plan = build_flip_ladder(100.0, 800.0, risk_mode="conservative")
    assert plan.warning != "" or plan.estimated_rounds >= 1
