from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import analysis


class _Msg:
    def __init__(self, text="/check 1"):
        self.text = text
        self.from_user = type("U", (), {"id": 1, "username": "u"})()
        self.out = []

    async def answer(self, text, **kwargs):
        self.out.append(text)


@pytest.mark.asyncio
async def test_check_routes_to_analysis(monkeypatch):
    async def _run(*args, **kwargs):
        gift = type("G", (), {"collection": "Ice Cream", "number": 10, "attributes": []})()
        est = type(
            "E",
            (),
            {
                "recommendation": "BUY_ONLY_CHEAP",
                "expected_roi_percent": 12.0,
                "expected_profit_ton": 3.0,
                "reasons": [],
                "buy_zone_max_ton": 100.0,
                "list_price_ton": 120.0,
                "confidence_score": 50,
                "risk_score": 40,
                "liquidity_score": 50,
            },
        )()
        q = type("Q", (), {"warnings": [], "sources_used": ["mock"], "is_mock_data": False, "is_partial_data": False})()
        return gift, est, 100.0, q, {"floor_freshness": "fresh", "sales_freshness": "fresh", "listings_freshness": "fresh", "real_sales_count": 1}

    monkeypatch.setattr("app.services.gift_analysis_flow.run_analysis_for_watchlist", _run)

    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1})()

    class _SnapRepo:
        def __init__(self, _s):
            pass

        async def create(self, **kwargs):
            return type("Sn", (), {"id": 9})()

    monkeypatch.setattr(analysis, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(analysis, "UserRepository", _Users)
    monkeypatch.setattr(analysis, "SignalSnapshotRepository", _SnapRepo)

    async def _legacy_nft(*_a, **_k):
        return ("legacy", False)

    monkeypatch.setattr(analysis.gift_flow, "deliver_nft_check_tonapi_only", _legacy_nft)

    msg = _Msg("/check 1")
    await analysis.check_handler(msg, AsyncMock())
    assert "/analyze 1" in msg.out[0]


@pytest.mark.asyncio
async def test_deals_chooses_scan_universe_for_pro(monkeypatch):
    class _Ctx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    called = {"universe": 0}

    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "pro"})()

        async def list_universe(self, *_):
            return [type("R", (), {"is_active": True})()]

    async def _universe(_msg):
        called["universe"] += 1

    monkeypatch.setattr("app.bot.handlers.analysis.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.analysis.UserRepository", _Users)
    monkeypatch.setattr("app.bot.handlers.portfolio.scan_universe_handler", _universe)
    msg = _Msg("/deals")
    await analysis.deals_handler(msg)
    assert called["universe"] == 1


@pytest.mark.asyncio
async def test_deals_free_shows_upgrade(monkeypatch):
    class _Ctx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

        async def list_universe(self, *_):
            return []

    async def _scan(*args, **kwargs):
        return None

    monkeypatch.setattr("app.bot.handlers.analysis.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.analysis.UserRepository", _Users)
    monkeypatch.setattr("app.bot.handlers.analysis._scan_handler_impl", _scan)
    msg = _Msg("/deals")
    await analysis.deals_handler(msg)
    assert "/upgrade" in msg.out[0]
