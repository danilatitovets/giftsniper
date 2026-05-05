from app.bot.handlers.portfolio import _effective_universe
from app.services.opportunity_scoring import rank_opportunities


def test_empty_universe_fallback_to_watchlist():
    out = _effective_universe([], ["Ice Cream", "Plush Pepe"])
    assert out == ["Ice Cream", "Plush Pepe"]


def test_universe_active_overrides_watchlist():
    out = _effective_universe(["Berry"], ["Ice Cream"])
    assert out == ["Berry"]


def test_universe_dedupes_watchlist():
    out = _effective_universe([], ["Ice Cream", "Ice Cream", "Berry"])
    assert out == ["Ice Cream", "Berry"]


def test_scan_universe_ranks_across_collections():
    ranked = rank_opportunities(
        [
            {"listing": type("L", (), {"collection": "Ice Cream"})(), "score": type("S", (), {"total_score": 60})()},
            {"listing": type("L", (), {"collection": "Plush Pepe"})(), "score": type("S", (), {"total_score": 80})()},
        ]
    )
    assert ranked[0]["listing"].collection == "Plush Pepe"
