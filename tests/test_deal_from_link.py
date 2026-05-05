import pytest

from app.bot.handlers import market as market_handlers
from app.services.gift_intake import GiftIdentity, GiftInput, GiftInputType


class _Msg:
    def __init__(self, text: str):
        self.text = text
        self.from_user = type("U", (), {"id": 1, "username": "u"})()
        self.out: list[str] = []

    async def answer(self, text: str, **kwargs):
        self.out.append(text)


@pytest.mark.asyncio
async def test_deal_asks_price_when_no_listing(monkeypatch):
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

    async def _resolve(user, payload, settings):
        gi = GiftInput(
            raw_text=payload,
            input_type=GiftInputType.collection_number,
            collection="Ice Cream",
            number=1,
            listing_price_ton=None,
        )
        ident = GiftIdentity(
            collection="Ice Cream",
            number=1,
            nft_address=None,
            collection_address=None,
            normalized_collection="Ice Cream",
            canonical_key="x",
            confidence=80,
            warnings=[],
        )
        return gi, ident

    monkeypatch.setattr(market_handlers, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(market_handlers, "UserRepository", _Users)
    monkeypatch.setattr(market_handlers, "resolve_gift_identity", _resolve)

    msg = _Msg("/deal Ice Cream #1")
    await market_handlers.deal_check(msg)
    assert any("Нужна цена" in x for x in msg.out)


@pytest.mark.asyncio
async def test_deal_uses_listing_price_from_resolver(monkeypatch):
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

    async def _resolve(user, payload, settings):
        gi = GiftInput(
            raw_text=payload,
            input_type=GiftInputType.marketplace_url,
            listing_price_ton=180.0,
        )
        ident = GiftIdentity(
            collection="Ice Cream",
            number=1,
            nft_address=None,
            collection_address=None,
            normalized_collection="Ice Cream",
            canonical_key="x",
            confidence=80,
            warnings=[],
        )
        return gi, ident

    class _Est:
        recommendation = "HOLD"
        fair_price_ton = 200.0
        list_price_ton = 210.0
        expected_net_sale_ton = 200.0
        expected_roi_percent = 1.0
        confidence_score = 50
        risk_score = 50

    class _An:
        last_data_quality = type("Q", (), {"is_mock_data": False, "is_partial_data": False, "warnings": [], "sources_used": []})()
        last_market_stats = {}

        async def analyze_gift(self, *a, **kw):
            assert kw.get("buy_price_ton") == 180.0
            return _Est()

    class _SnapRepo:
        def __init__(self, _s):
            pass

        async def create(self, **kwargs):
            return type("Sn", (), {"id": 77})()

    monkeypatch.setattr(market_handlers, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(market_handlers, "UserRepository", _Users)
    monkeypatch.setattr(market_handlers, "SignalSnapshotRepository", _SnapRepo)
    monkeypatch.setattr(market_handlers, "resolve_gift_identity", _resolve)
    monkeypatch.setattr(market_handlers, "AnalyzerService", lambda *a, **kw: _An())
    monkeypatch.setattr(market_handlers, "create_market_source", lambda *a, **kw: object())
    monkeypatch.setattr(
        market_handlers,
        "calculate_opportunity_score",
        lambda *a, **kw: type("S", (), {"total_score": 0, "final_rank_label": "n/a", "roi_score": 0, "profit_score": 0, "liquidity_score": 0, "confidence_score": 0, "freshness_score": 0, "source_quality_score": 0, "risk_penalty": 0})(),
    )
    monkeypatch.setattr(market_handlers, "format_score_breakdown", lambda s: "")

    msg = _Msg("/deal https://getgems.io/nft/foo")
    await market_handlers.deal_check(msg)
    assert any("Сделка" in x for x in msg.out)
