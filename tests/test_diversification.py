from types import SimpleNamespace

from app.services.diversification import (
    calculate_collection_exposure,
    calculate_diversification_score,
    get_concentration_warnings,
)


def test_diversification_warning_if_one_collection_dominates():
    portfolio = [{"collection": "Ice Cream", "value_ton": 90}, {"collection": "Plush Pepe", "value_ton": 10}]
    warnings = get_concentration_warnings(portfolio, SimpleNamespace(max_collection_percent=40))
    assert any("Ice Cream" in w for w in warnings)


def test_diversification_score_drops_on_concentration():
    concentrated = calculate_diversification_score([{"collection": "Ice Cream", "value_ton": 100}])
    balanced = calculate_diversification_score(
        [{"collection": "Ice Cream", "value_ton": 50}, {"collection": "Plush Pepe", "value_ton": 50}]
    )
    assert balanced > concentrated


def test_collection_exposure_percentages():
    exp = calculate_collection_exposure(
        [{"collection": "Ice Cream", "value_ton": 80}, {"collection": "Plush Pepe", "value_ton": 20}]
    )
    assert exp["Ice Cream"] == 80.0
