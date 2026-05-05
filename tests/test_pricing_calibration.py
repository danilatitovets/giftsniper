from pathlib import Path

from app.services.pricing_calibration import (
    load_calibration_scenarios,
    run_all_calibration_scenarios,
    run_calibration_scenario,
)


def test_load_calibration_scenarios_from_fixtures():
    root = Path(__file__).resolve().parent / "fixtures" / "calibration" / "scenarios"
    scenarios = load_calibration_scenarios(base=root)
    assert len(scenarios) >= 4


def test_calibration_scenarios_pass_expected_ranges():
    root = Path(__file__).resolve().parent / "fixtures" / "calibration" / "scenarios"
    results = run_all_calibration_scenarios(load_calibration_scenarios(base=root))
    failed = [r for r in results if not r.passed]
    assert not failed, "\n".join(f"{r.scenario_name}: {r.errors}" for r in failed)


def test_strong_buy_not_returned_for_no_trait_sales_rare_profile():
    from app.services.pricing_calibration import CalibrationScenario

    s = CalibrationScenario(
        name="rare_no_trait_sales",
        collection="X",
        number=1,
        attributes=[{"trait_type": "Backdrop", "trait_value": "Gold"}],
        listing_price_ton=100,
        collection_floor_ton=90,
        trait_floor_ton=300,
        recent_sales=[95, 98, 100, 102, 105],
        trait_recent_sales=[],
        expected_decision="STRONG_BUY",
    )
    r = run_calibration_scenario(s)
    assert r.actual_decision != "STRONG_BUY"
