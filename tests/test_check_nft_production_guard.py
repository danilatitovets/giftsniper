"""NFT-like /check must use TonAPI full-market only; no legacy mock in production."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot.handlers import analysis
from app.services import nft_check_limits as nft_check_limits_mod
from app.config import Settings
from app.services import gift_analysis_flow
from app.services.real_market_collection_scan import MarketNftRow, TargetNftInfo, build_full_report
from app.services.universal_nft_resolver import ResolvedNft


def _settings(**kw: object) -> Settings:
    base: dict = {
        "BOT_TOKEN": "x",
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "TONAPI_ENABLED": True,
        "TONAPI_API_KEY": "unit-test-tonapi-key",
        "PRODUCTION_MODE": True,
        "ENABLE_MOCK_SOURCE": False,
        "ALLOW_MOCK_IN_PRODUCTION": False,
        "FULL_MARKET_SCAN_ENABLED": True,
    }
    base.update(kw)
    return Settings(**base)


def _row(
    *,
    name: str,
    num: int,
    addr: str,
    price: float | None,
    model: str | None,
    backdrop: str | None,
    symbol: str | None,
) -> MarketNftRow:
    return MarketNftRow(
        name=name,
        number=num,
        address=addr,
        price_ton=Decimal(str(price)) if price is not None else None,
        for_sale=price is not None,
        model=model,
        backdrop=backdrop,
        symbol=symbol,
    )


class _Msg:
    def __init__(self) -> None:
        self.from_user = type("U", (), {"id": 1, "username": "u"})()
        self.chat = type("C", (), {"id": 4242})()
        self.out: list[str] = []
        self._mid = 0
        self.bot = _Bot(self)

    async def answer(self, text: str = "", **kwargs):
        self.out.append(text)
        self._mid += 1
        return type("R", (), {"message_id": self._mid})()

    async def answer_photo(self, **kwargs):
        cap = kwargs.get("caption") or ""
        self.out.append(cap)
        self._mid += 1
        return type("R", (), {"message_id": self._mid})()


class _Bot:
    def __init__(self, owner: _Msg) -> None:
        self._owner = owner

    async def edit_message_text(self, text: str, chat_id: int, message_id: int):
        self._owner.out.append(text)


@pytest.fixture
def analysis_execute_user_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    class _CM:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *a: object) -> bool:
            return False

    u = MagicMock(language_code="en", id=1)
    monkeypatch.setattr(analysis, "SessionLocal", lambda: _CM())
    monkeypatch.setattr(analysis.UserRepository, "get_or_create", AsyncMock(return_value=u))
    monkeypatch.setattr(nft_check_limits_mod, "record_successful_nft_check", AsyncMock(return_value=None))


@pytest.fixture
def mock_session_for_nft_deliver(monkeypatch: pytest.MonkeyPatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Users:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *a, **k):
            return type("Us", (), {"id": 1})()

    monkeypatch.setattr(gift_analysis_flow, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(gift_analysis_flow, "UserRepository", _Users)


@pytest.mark.asyncio
async def test_nft_check_never_uses_mock_in_production(
    monkeypatch: pytest.MonkeyPatch, analysis_execute_user_stub: None
):
    st = _settings(ENABLE_MOCK_SOURCE=True)
    monkeypatch.setattr(analysis, "get_settings", lambda: st)

    async def fake_deliver(message, *, telegram_id, username, payload, settings):
        await message.answer("probe")
        return ("legacy", False)

    monkeypatch.setattr(analysis.gift_flow, "deliver_nft_check_tonapi_only", fake_deliver)

    called = {"n": 0}

    async def boom(*a, **k):
        called["n"] += 1

    monkeypatch.setattr(analysis, "run_gift_check", boom)

    msg = _Msg()
    await analysis.execute_check_payload(msg, "EQA0EzRYX5wm_q46_NX8b7EYhtOkXfXgsr06ETbov1a7StZl")
    assert called["n"] == 0
    assert any("Mock/legacy" in x for x in msg.out)


@pytest.mark.asyncio
async def test_nft_like_check_never_calls_legacy_in_production(
    monkeypatch: pytest.MonkeyPatch, analysis_execute_user_stub: None
):
    st = _settings()
    monkeypatch.setattr(analysis, "get_settings", lambda: st)

    async def fake_deliver(message, *, telegram_id, username, payload, settings):
        await message.answer("probe")
        return ("legacy", False)

    monkeypatch.setattr(analysis.gift_flow, "deliver_nft_check_tonapi_only", fake_deliver)

    called = {"n": 0}

    async def boom(*a, **k):
        called["n"] += 1

    monkeypatch.setattr(analysis, "run_gift_check", boom)

    msg = _Msg()
    await analysis.execute_check_payload(msg, "Ice Cream #217467")
    assert called["n"] == 0
    assert any("Mock/legacy" in x for x in msg.out)


@pytest.mark.asyncio
async def test_missing_tonapi_key_no_mock_fallback(
    monkeypatch: pytest.MonkeyPatch, analysis_execute_user_stub: None
):
    st = _settings(TONAPI_API_KEY="")
    monkeypatch.setattr(analysis, "get_settings", lambda: st)

    called = {"n": 0}

    async def boom(*a, **k):
        called["n"] += 1

    monkeypatch.setattr(analysis, "run_gift_check", boom)

    msg = _Msg()
    await analysis.execute_check_payload(msg, "Ice Cream #217467")
    assert called["n"] == 0
    assert any("TONAPI_API_KEY" in x for x in msg.out)


@pytest.mark.asyncio
async def test_production_no_mock_without_tonapi_key(
    monkeypatch: pytest.MonkeyPatch, analysis_execute_user_stub: None
):
    st = _settings(TONAPI_API_KEY="")
    monkeypatch.setattr(analysis, "get_settings", lambda: st)
    called = {"n": 0}

    async def boom(*a, **k):
        called["n"] += 1

    monkeypatch.setattr(analysis, "run_gift_check", boom)
    msg = _Msg()
    await analysis.execute_check_payload(msg, "EQA0EzRYX5wm_q46_NX8b7EYhtOkXfXgsr06ETbov1a7StZl")
    assert called["n"] == 0
    assert any("TONAPI_API_KEY" in x for x in msg.out)


@pytest.mark.asyncio
async def test_unknown_collection_no_legacy(
    monkeypatch: pytest.MonkeyPatch,
    mock_session_for_nft_deliver: None,
    analysis_execute_user_stub: None,
):
    st = _settings()
    monkeypatch.setattr(analysis, "get_settings", lambda: st)

    err_txt = (
        "❌ Не удалось автоматически найти коллекцию «Unknown Collection».\n\n"
        "Пришли ссылку на NFT или NFT address — так я точно определю коллекцию через TonAPI."
    )

    async def fake_resolve(*a, **k):
        return None, err_txt

    monkeypatch.setattr(gift_analysis_flow, "resolve_universal_nft", fake_resolve)

    called = {"n": 0}

    async def boom(*a, **k):
        called["n"] += 1

    monkeypatch.setattr(analysis, "run_gift_check", boom)

    msg = _Msg()
    await analysis.execute_check_payload(msg, "Unknown Collection #123")
    assert called["n"] == 0
    blob = "\n".join(msg.out)
    assert "collections.json" not in blob.lower()
    assert "Unknown Collection" in blob


@pytest.mark.asyncio
async def test_non_nft_payload_can_use_legacy(
    monkeypatch: pytest.MonkeyPatch, analysis_execute_user_stub: None
):
    st = _settings()
    monkeypatch.setattr(analysis, "get_settings", lambda: st)

    async def legacy_deliver(*a, **k):
        return ("legacy", False)

    monkeypatch.setattr(analysis.gift_flow, "deliver_nft_check_tonapi_only", legacy_deliver)

    called = {"n": 0}

    async def fake_run(*a, **k):
        called["n"] += 1
        from app.services.gift_analysis_flow import UniversalCheckOutcome

        return UniversalCheckOutcome(False, error="legacy path ok")

    monkeypatch.setattr(analysis, "run_gift_check", fake_run)

    msg = _Msg()
    await analysis.execute_check_payload(msg, "totally_unknown_format_xyz_no_url_no_hash")
    assert called["n"] == 1
    assert msg.out and "legacy path ok" in msg.out[-1]


@pytest.mark.asyncio
async def test_successful_nft_check_uses_tonapi_report(
    monkeypatch: pytest.MonkeyPatch,
    mock_session_for_nft_deliver: None,
    analysis_execute_user_stub: None,
):
    st = _settings()
    monkeypatch.setattr(analysis, "get_settings", lambda: st)

    tgt = TargetNftInfo(
        name="Ice Cream #1",
        number=1,
        address="0:t",
        collection_name="Ice Creams",
        collection_address="0:c",
        model="M",
        backdrop="B",
        symbol="S",
    )
    rows = [
        _row(name="Ice Cream #2", num=2, addr="0:r2", price=7.0, model="M", backdrop="X", symbol="Y"),
        _row(name="Ice Cream #3", num=3, addr="0:r3", price=9.0, model="M", backdrop="X", symbol="Z"),
        _row(name="Ice Cream #4", num=4, addr="0:r4", price=12.0, model="M", backdrop="X", symbol="W"),
    ]
    rep = build_full_report(
        tgt,
        rows,
        loaded_count=1000,
        is_partial_scan=False,
        settings=st,
        cache_age_minutes=None,
    )

    async def ok_resolve(*a, **k):
        return (
            ResolvedNft(
                original_payload="Ice Cream #217467",
                nft_address=tgt.address,
                collection_address=tgt.collection_address,
                nft_name=tgt.name,
                collection_name=tgt.collection_name,
                item_number=tgt.number,
                image_url=None,
                traits={"model": tgt.model, "backdrop": tgt.backdrop, "symbol": tgt.symbol},
                sale_price_ton=None,
                for_sale=False,
                source="tonapi",
                learned=False,
                target=tgt,
                nft_raw=None,
            ),
            None,
        )

    async def ok_flow(*a, **k):
        return rep, None

    monkeypatch.setattr(gift_analysis_flow, "resolve_universal_nft", ok_resolve)
    monkeypatch.setattr(gift_analysis_flow, "run_full_market_analysis_flow", ok_flow)

    called = {"n": 0}

    async def boom(*a, **k):
        called["n"] += 1

    monkeypatch.setattr(analysis, "run_gift_check", boom)

    msg = _Msg()
    await analysis.execute_check_payload(msg, "Ice Cream #217467")
    assert called["n"] == 0
    blob = "\n".join(msg.out).lower()
    assert "источник" in blob and "tonapi" in blob
    for bad in ("mock", "тест", "заглушка", "116 ton", "200 ton"):
        assert bad not in blob


def test_is_nft_like_includes_hash_number_pattern():
    assert gift_analysis_flow.is_nft_like_check_payload("Whip Cupcake #57234")
    assert gift_analysis_flow.is_nft_like_check_payload("something #42 here")
    assert not gift_analysis_flow.is_nft_like_check_payload("plain fluff text")


def test_tonapi_timeout_friendly():
    msg = gift_analysis_flow._map_nft_full_market_error("timeout while requesting tonapi")
    low = msg.lower()
    assert "tonapi" in low
    assert "повтори" in low or "проверь" in low
