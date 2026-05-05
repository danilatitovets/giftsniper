from types import SimpleNamespace

from app.services.market_regime import evaluate_collection_regime


def _opp(score=70, liq=60, risk=40, source="Getgems", freshness="fresh", sales=2):
    return {
        "listing": SimpleNamespace(collection="Ice Cream", source=source),
        "estimate": SimpleNamespace(liquidity_score=liq, risk_score=risk),
        "score": SimpleNamespace(total_score=score, final_rank_label="A_TIER"),
        "freshness_label": freshness,
        "real_sales_count": sales,
    }


def test_collection_with_better_opps_ranks_higher():
    strong = evaluate_collection_regime("Ice Cream", [_opp(score=80), _opp(score=75)])
    weak = evaluate_collection_regime("Berry", [_opp(score=40, liq=30, source="Manual", sales=0)])
    assert strong.relative_strength_score > weak.relative_strength_score


def test_overexposed_collection_can_get_reduce_exposure():
    rep = evaluate_collection_regime("Ice Cream", [_opp(score=80)], portfolio_exposure_percent=75)
    assert rep.recommendation == "REDUCE_EXPOSURE"
