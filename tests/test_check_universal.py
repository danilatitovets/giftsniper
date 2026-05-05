from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import analysis
from app.services import gift_analysis_flow
from app.services.gift_intake import GiftIdentity, GiftInput, GiftInputType


class _Msg:
    def __init__(self, text: str):
        self.text = text
        self.from_user = type("U", (), {"id": 1, "username": "u"})()
        self.out: list[str] = []

    async def answer(self, text: str, **kwargs):
        self.out.append(text)


async def _legacy_nft_route(*_a, **_k):
    return ("legacy", False)


@pytest.mark.asyncio
async def test_check_universal_collection_number(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "risk_mode": "normal"})()

    class _Est:
        recommendation = "HOLD"
        fair_price_ton = 200.0
        buy_zone_min_ton = 150.0
        buy_zone_max_ton = 180.0
        list_price_ton = 220.0
        expected_roi_percent = 5.0
        confidence_score = 55
        risk_score = 50
        reasons = []

    class _An:
        last_data_quality = type("Q", (), {"is_mock_data": False, "is_partial_data": False, "warnings": [], "sources_used": []})()
        last_market_stats = {}

        async def analyze_gift(self, *a, **kw):
            return _Est()

    async def _resolve(user, payload, settings):
        gi = GiftInput(
            raw_text=payload,
            input_type=GiftInputType.collection_number,
            collection="Ice Cream",
            number=3,
        )
        ident = GiftIdentity(
            collection="Ice Cream",
            number=3,
            nft_address=None,
            collection_address=None,
            normalized_collection="Ice Cream",
            canonical_key="ice_cream#3",
            confidence=80,
            warnings=[],
        )
        return gi, ident

    monkeypatch.setattr(gift_analysis_flow, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(gift_analysis_flow, "UserRepository", _Users)
    monkeypatch.setattr(gift_analysis_flow, "resolve_gift_identity", _resolve)
    monkeypatch.setattr(gift_analysis_flow, "AnalyzerService", lambda *a, **kw: _An())
    monkeypatch.setattr(gift_analysis_flow, "create_market_source", lambda *a, **kw: object())

    class _SnapRepo:
        def __init__(self, _s):
            pass

        async def create(self, **kwargs):
            return type("Sn", (), {"id": 501})()

    monkeypatch.setattr(analysis, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(analysis, "UserRepository", _Users)
    monkeypatch.setattr(analysis, "SignalSnapshotRepository", _SnapRepo)
    monkeypatch.setattr(analysis.gift_flow, "deliver_nft_check_tonapi_only", _legacy_nft_route)

    msg = _Msg("/check Ice Cream #3")
    await analysis.check_handler(msg, AsyncMock())
    assert msg.out and "Ice Cream" in msg.out[0]


@pytest.mark.asyncio
async def test_check_nft_address_path(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "risk_mode": "normal"})()

    class _Est:
        recommendation = "HOLD"
        fair_price_ton = 1.0
        buy_zone_min_ton = 1.0
        buy_zone_max_ton = 2.0
        list_price_ton = 3.0
        expected_roi_percent = 0.0
        confidence_score = 50
        risk_score = 50
        reasons = []

    class _An:
        last_data_quality = type("Q", (), {"is_mock_data": True, "is_partial_data": True, "warnings": [], "sources_used": []})()
        last_market_stats = {}

        async def analyze_gift(self, *a, **kw):
            return _Est()

    addr = "EQ" + "A" * 46

    async def _resolve(user, payload, settings):
        gi = GiftInput(raw_text=payload, input_type=GiftInputType.nft_address, nft_address=addr)
        ident = GiftIdentity(
            collection="On-chain NFT",
            number=0,
            nft_address=addr,
            collection_address=None,
            normalized_collection="on-chain nft",
            canonical_key=f"addr:{addr}",
            confidence=50,
            warnings=[],
        )
        return gi, ident

    monkeypatch.setattr(gift_analysis_flow, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(gift_analysis_flow, "UserRepository", _Users)
    monkeypatch.setattr(gift_analysis_flow, "resolve_gift_identity", _resolve)
    monkeypatch.setattr(gift_analysis_flow, "AnalyzerService", lambda *a, **kw: _An())
    monkeypatch.setattr(gift_analysis_flow, "create_market_source", lambda *a, **kw: object())

    class _SnapRepo:
        def __init__(self, _s):
            pass

        async def create(self, **kwargs):
            return type("Sn", (), {"id": 502})()

    monkeypatch.setattr(analysis, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(analysis, "UserRepository", _Users)
    monkeypatch.setattr(analysis, "SignalSnapshotRepository", _SnapRepo)
    monkeypatch.setattr(analysis.gift_flow, "deliver_nft_check_tonapi_only", _legacy_nft_route)

    msg = _Msg(f"/check {addr}")
    await analysis.check_handler(msg, AsyncMock())
    assert msg.out
