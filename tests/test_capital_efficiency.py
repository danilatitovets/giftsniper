from app.services.capital_multiplier import FlipCandidate, calculate_capital_efficiency


def test_capital_efficiency_ranks_better_candidate_higher():
    good = FlipCandidate(
        collection="A",
        buy_price_ton=100.0,
        expected_roi_percent=30.0,
        sale_probability_percent=70.0,
        confidence_score=80,
        liquidity_score=75,
        risk_score=40,
        warnings=[],
    )
    weak = good.model_copy(
        update={
            "expected_roi_percent": 10.0,
            "sale_probability_percent": 40.0,
            "confidence_score": 50,
            "liquidity_score": 45,
            "risk_score": 75,
        }
    )
    assert calculate_capital_efficiency(good) > calculate_capital_efficiency(weak)


def test_efficiency_clamped_zero_to_hundred():
    c = FlipCandidate(
        collection="A",
        buy_price_ton=1.0,
        expected_roi_percent=200.0,
        sale_probability_percent=90.0,
        confidence_score=90,
        liquidity_score=90,
        risk_score=10,
        warnings=[],
    )
    e = calculate_capital_efficiency(c)
    assert 0 <= e <= 100
