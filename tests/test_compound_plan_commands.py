from app.services.flip_ladder import build_flip_ladder, format_flip_ladder


def test_compound_plan_output_has_scenario_disclaimer():
    plan = build_flip_ladder(100.0, 250.0, risk_mode="normal")
    text = format_flip_ladder(plan)
    assert "сценарий" in text.lower()
    assert "гарантированно" not in text.lower()
