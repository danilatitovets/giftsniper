from app.bot.handlers.portfolio import _downside
from app.services.capital_allocation import calculate_collection_exposure


def test_downside_scenario_calculation():
    d = _downside(750)
    assert d["-10%"] == 675.0
    assert d["-25%"] == 562.5
    assert d["-40%"] == 450.0


def test_collection_exposure_calculation():
    exp = calculate_collection_exposure(
        [
            {"collection": "Ice Cream", "value_ton": 100},
            {"collection": "Ice Cream", "value_ton": 50},
            {"collection": "Berry", "value_ton": 30},
        ]
    )
    assert exp["Ice Cream"] == 150
    assert exp["Berry"] == 30
