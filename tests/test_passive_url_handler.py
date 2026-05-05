from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext

from app.bot.handlers import passive_gift as passive


def _fsm_ctx() -> FSMContext:
    m = MagicMock(spec=FSMContext)
    m.clear = AsyncMock()
    return m
from app.services.real_market_collection_scan import TargetNftInfo
from app.services.universal_nft_resolver import ResolvedNft


class _Msg:
    def __init__(self, text: str):
        self.text = text
        self.from_user = type("U", (), {"id": 1, "username": "u"})()
        self.chat = type("C", (), {"id": 1})()
        self.bot = type("B", (), {"edit_message_text": self._edit})()
        self.out: list[str] = []
        self._kb = None
        self.photos: list[dict] = []
        self.animations: list[dict] = []
        self.videos: list[dict] = []

    async def _edit(self, text: str, **kwargs):
        self.out.append(text)
        self._kb = kwargs.get("reply_markup")

    async def answer(self, text: str, **kwargs):
        self.out.append(text)
        self._kb = kwargs.get("reply_markup")
        return type("R", (), {"message_id": 11})()

    async def answer_photo(self, **kwargs):
        self.photos.append(kwargs)
        return type("R", (), {"message_id": 12})()

    async def answer_animation(self, **kwargs):
        self.animations.append(kwargs)
        return type("R", (), {"message_id": 13})()

    async def answer_video(self, **kwargs):
        self.videos.append(kwargs)
        return type("R", (), {"message_id": 14})()


def _resolved_target() -> TargetNftInfo:
    return TargetNftInfo(
        name="Pretty Posy #28864",
        number=28864,
        address="EQ_ADDR_1",
        collection_name="Pretty Posy",
        collection_address="EQ_COLL_1",
        model="Aurora",
        backdrop="Blue",
        symbol="Star",
        image_url=None,
    )


def _resolved_preview() -> ResolvedNft:
    tgt = _resolved_target()
    return ResolvedNft(
        original_payload="Pretty Posy #28864",
        nft_address=tgt.address,
        collection_address=tgt.collection_address,
        nft_name=tgt.name,
        collection_name=tgt.collection_name,
        item_number=tgt.number,
        image_url=tgt.image_url,
        traits={"model": tgt.model, "backdrop": tgt.backdrop, "symbol": tgt.symbol},
        sale_price_ton=1.2,
        for_sale=True,
        source="tonapi",
        learned=False,
        target=tgt,
        nft_raw={
            "sale": {"price": {"value": "1200000000", "decimals": 9, "token_name": "TON"}},
            "metadata": {
                "attributes": [
                    {"trait_type": "Aura", "trait_value": "Soft"},
                    {"trait_type": "Rarity", "trait_value": "Rare"},
                    {"trait_type": "Mood", "trait_value": "Joy"},
                    {"trait_type": "Ignored", "trait_value": "Extra"},
                ]
            },
        },
    )


def _resolved_preview_listed_800() -> ResolvedNft:
    tgt = _resolved_target()
    return ResolvedNft(
        original_payload="https://getgems.io/nft/abc",
        nft_address=tgt.address,
        collection_address=tgt.collection_address,
        nft_name="Vintage Cigar #8922",
        collection_name="Vintage Cigars",
        item_number=8922,
        image_url=tgt.image_url,
        traits={"model": "Warm Glow", "backdrop": "Black", "symbol": "Anchor"},
        sale_price_ton=800.0,
        for_sale=True,
        source="tonapi",
        learned=False,
        target=tgt,
        nft_raw={"sale": {"price": {"value": "800000000000", "decimals": 9, "token_name": "TON"}}},
    )


@pytest.mark.asyncio
async def test_passive_nft_like_does_not_show_actions_before_resolve(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    class _Ton:
        def __init__(self, _s):
            pass

        async def get_nft(self, _a):
            return None

    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(
        passive,
        "resolve_universal_nft",
        lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(None, "not_found"))),
    )
    monkeypatch.setattr(passive, "TonAPICollectionClient", _Ton)

    msg = _Msg("Pretty Posy #28864")
    await passive.passive_gift_text(msg, _fsm_ctx())
    assert msg.out
    blob = "\n".join(msg.out)
    assert "не нашёл" in blob.lower()
    assert "/check" not in blob and "/add" not in blob and "/deal" not in blob
    assert msg._kb is not None
    btns = [b.text for row in msg._kb.inline_keyboard for b in row]
    assert "❌ Закрыть" in btns
    assert "✅ Добавить в список" not in btns


@pytest.mark.asyncio
async def test_passive_resolved_nft_shows_preview_card(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    class _Ton:
        def __init__(self, _s):
            pass

        async def get_nft(self, _a):
            return {"sale": {"price": {"value": "1200000000", "decimals": 9, "token_name": "TON"}}}

    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(
        passive,
        "resolve_universal_nft",
        lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(_resolved_preview(), None))),
    )
    monkeypatch.setattr(passive, "TonAPICollectionClient", _Ton)
    monkeypatch.setattr(
        passive,
        "extract_nft_preview_media",
        lambda *_a, **_k: type("M", (), {"url": None, "kind": "none", "mime_type": None, "source_field": None})(),
    )
    monkeypatch.setattr(passive.runtime_state, "nft_action_session_put", lambda *_a, **_k: "tok1")

    msg = _Msg("Pretty Posy #28864")
    await passive.passive_gift_text(msg, _fsm_ctx())
    blob = "\n".join(msg.out)
    assert "Pretty Posy #28864" in blob
    assert "Коллекция" in blob
    assert "Трейты" in blob
    assert "Model: Aurora" in blob
    assert "Листинг" in blob
    assert "Источник: TonAPI" in blob


@pytest.mark.asyncio
async def test_passive_resolved_nft_sends_photo_when_image_exists(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    class _Ton:
        def __init__(self, _s):
            pass

        async def get_nft(self, _a):
            return {}

    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(
        passive,
        "resolve_universal_nft",
        lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(_resolved_preview(), None))),
    )
    monkeypatch.setattr(passive, "TonAPICollectionClient", _Ton)
    monkeypatch.setattr(
        passive,
        "extract_nft_preview_media",
        lambda *_a, **_k: type("M", (), {"url": "https://img.png", "kind": "photo", "mime_type": None, "source_field": "image"})(),
    )
    monkeypatch.setattr(passive.runtime_state, "nft_action_session_put", lambda *_a, **_k: "tok1")

    msg = _Msg("Pretty Posy #28864")
    await passive.passive_gift_text(msg, _fsm_ctx())
    assert msg.photos


@pytest.mark.asyncio
async def test_passive_resolved_nft_falls_back_to_text_without_image(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    class _Ton:
        def __init__(self, _s):
            pass

        async def get_nft(self, _a):
            return {}

    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(
        passive,
        "resolve_universal_nft",
        lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(_resolved_preview(), None))),
    )
    monkeypatch.setattr(passive, "TonAPICollectionClient", _Ton)
    monkeypatch.setattr(
        passive,
        "extract_nft_preview_media",
        lambda *_a, **_k: type("M", (), {"url": None, "kind": "none", "mime_type": None, "source_field": None})(),
    )
    monkeypatch.setattr(passive.runtime_state, "nft_action_session_put", lambda *_a, **_k: "tok1")

    msg = _Msg("Pretty Posy #28864")
    await passive.passive_gift_text(msg, _fsm_ctx())
    assert not msg.photos
    assert any("Что сделать?" in x for x in msg.out)


@pytest.mark.asyncio
async def test_no_action_buttons_on_tonapi_404(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(
        passive,
        "resolve_universal_nft",
        lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(None, "404"))),
    )

    msg = _Msg("EQA0EzRYX5wm_q46_NX8b7EYhtOkXfXgsr06ETbov1a7StZl")
    await passive.passive_gift_text(msg, _fsm_ctx())
    btns = [b.text for row in msg._kb.inline_keyboard for b in row]
    assert "🔎 Проверить рынок" not in btns


@pytest.mark.asyncio
async def test_getgems_startapp_does_not_show_no_number_or_address_message(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    class _Ton:
        def __init__(self, _s):
            pass

        async def get_nft(self, _a):
            return {}

    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(
        passive,
        "resolve_universal_nft",
        lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(_resolved_preview(), None))),
    )
    monkeypatch.setattr(passive, "TonAPICollectionClient", _Ton)
    monkeypatch.setattr(
        passive,
        "extract_nft_preview_media",
        lambda *_a, **_k: type("M", (), {"url": None, "kind": "none", "mime_type": None, "source_field": None})(),
    )
    monkeypatch.setattr(passive.runtime_state, "nft_action_session_put", lambda *_a, **_k: "tok1")

    url = (
        "https://t.me/GetgemsNftBot/gems?startapp="
        "L2NvbGxlY3Rpb24vRVFBMEV6UllYNXdtX3E0Nl9OWDhiN0VZaHRPa1hmWGdzcjA2RVRib3YxYTdTdFpsL0VRZl90"
        "Z19naWZ0X19fX19fX19fX19fX19fX19fX184cXRGNGZBQUJ3d0wtZQ"
    )
    msg = _Msg(url)
    await passive.passive_gift_text(msg, _fsm_ctx())
    blob = "\n".join(msg.out)
    assert "в ней нет номера или адреса" not in blob.lower()
    assert "Что сделать?" in blob


@pytest.mark.asyncio
async def test_getgems_startapp_preview_card_success(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    class _Ton:
        def __init__(self, _s):
            pass

        async def get_nft(self, _a):
            return {"sale": {"price": {"value": "1000000000", "decimals": 9, "token_name": "TON"}}}

    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(
        passive,
        "resolve_universal_nft",
        lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(_resolved_preview(), None))),
    )
    monkeypatch.setattr(passive, "TonAPICollectionClient", _Ton)
    monkeypatch.setattr(
        passive,
        "extract_nft_preview_media",
        lambda *_a, **_k: type("M", (), {"url": "https://img.png", "kind": "photo", "mime_type": None, "source_field": "image"})(),
    )
    monkeypatch.setattr(passive.runtime_state, "nft_action_session_put", lambda *_a, **_k: "tok1")

    url = (
        "https://t.me/GetgemsNftBot/gems?startapp="
        "L2NvbGxlY3Rpb24vRVFBMEV6UllYNXdtX3E0Nl9OWDhiN0VZaHRPa1hmWGdzcjA2RVRib3YxYTdTdFpsL0VRZl90"
        "Z19naWZ0X19fX19fX19fX19fX19fX19fX184cXRGNGZBQUJ3d0wtZQ"
    )
    msg = _Msg(url)
    await passive.passive_gift_text(msg, _fsm_ctx())
    assert msg.photos
    assert "Что сделать?" in (msg.photos[0].get("caption") or "")


@pytest.mark.asyncio
async def test_preview_card_shows_target_sale_price(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(
        passive,
        "resolve_universal_nft",
        lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(_resolved_preview_listed_800(), None))),
    )
    monkeypatch.setattr(
        passive,
        "extract_nft_preview_media",
        lambda *_a, **_k: type("M", (), {"url": None, "kind": "none", "mime_type": None, "source_field": None})(),
    )
    monkeypatch.setattr(passive.runtime_state, "nft_action_session_put", lambda *_a, **_k: "tok1")

    msg = _Msg("Pretty Posy #28864")
    await passive.passive_gift_text(msg, _fsm_ctx())
    blob = "\n".join(msg.out)
    assert "Сейчас выставлен: 800 TON" in blob


@pytest.mark.asyncio
async def test_preview_card_external_hint_not_confirmed(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    res = _resolved_preview()
    res.sale_price_ton = None
    res.for_sale = False
    res.external_sale_hint = True
    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(
        passive,
        "resolve_universal_nft",
        lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(res, None))),
    )
    monkeypatch.setattr(
        passive,
        "extract_nft_preview_media",
        lambda *_a, **_k: type("M", (), {"url": None, "kind": "none", "mime_type": None, "source_field": None})(),
    )
    monkeypatch.setattr(passive.runtime_state, "nft_action_session_put", lambda *_a, **_k: "tok1")
    msg = _Msg("Pretty Posy #28864")
    await passive.passive_gift_text(msg, _fsm_ctx())
    blob = "\n".join(msg.out).lower()
    assert "листинг не подтверждён tonapi" in blob


@pytest.mark.asyncio
async def test_getgems_startapp_404_friendly_error(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(
        passive,
        "resolve_universal_nft",
        lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(None, "404"))),
    )

    url = (
        "https://t.me/GetgemsNftBot/gems?startapp="
        "L2NvbGxlY3Rpb24vRVFBMEV6UllYNXdtX3E0Nl9OWDhiN0VZaHRPa1hmWGdzcjA2RVRib3YxYTdTdFpsL0VRZl90"
        "Z19naWZ0X19fX19fX19fX19fX19fX19fX184cXRGNGZBQUJ3d0wtZQ"
    )
    msg = _Msg(url)
    await passive.passive_gift_text(msg, _fsm_ctx())
    blob = "\n".join(msg.out)
    assert "Не нашёл NFT" in blob
    assert "mock" not in blob.lower()
    assert "legacy" not in blob.lower()
    assert "collections.json" not in blob.lower()


@pytest.mark.asyncio
async def test_collection_only_startapp_friendly_error(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)

    url = (
        "https://t.me/GetgemsNftBot/gems?startapp="
        "L2NvbGxlY3Rpb24vRVFBMEV6UllYNXdtX3E0Nl9OWDhiN0VZaHRPa1hmWGdzcjA2RVRib3YxYTdTdFps"
    )
    msg = _Msg(url)
    await passive.passive_gift_text(msg, _fsm_ctx())
    blob = "\n".join(msg.out)
    assert "ссылка на коллекцию" in blob.lower()


@pytest.mark.asyncio
async def test_photo_send_error_fallbacks_to_text(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(
        passive,
        "resolve_universal_nft",
        lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(_resolved_preview(), None))),
    )
    monkeypatch.setattr(
        passive,
        "extract_nft_preview_media",
        lambda *_a, **_k: type("M", (), {"url": "https://img.png", "kind": "photo", "mime_type": None, "source_field": "image"})(),
    )
    monkeypatch.setattr(passive.runtime_state, "nft_action_session_put", lambda *_a, **_k: "tok1")

    msg = _Msg("Pretty Posy #28864")

    async def _boom(**_kwargs):
        raise RuntimeError("photo failed")

    msg.answer_photo = _boom
    await passive.passive_gift_text(msg, _fsm_ctx())
    assert any("Что сделать?" in x for x in msg.out)


@pytest.mark.asyncio
async def test_passive_resolve_only_shows_preview_no_market_scan(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    called = {"n": 0}

    async def _boom_scan(*_a, **_k):
        called["n"] += 1
        raise AssertionError("Market scan must not start in passive resolve")

    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(
        passive,
        "resolve_universal_nft",
        lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(_resolved_preview(), None))),
    )
    monkeypatch.setattr(
        "app.bot.handlers.analysis.execute_check_payload",
        _boom_scan,
    )
    monkeypatch.setattr(
        passive,
        "extract_nft_preview_media",
        lambda *_a, **_k: type("M", (), {"url": None, "kind": "none", "mime_type": None, "source_field": None})(),
    )
    monkeypatch.setattr(passive.runtime_state, "nft_action_session_put", lambda *_a, **_k: "tok1")

    msg = _Msg("https://getgems.io/nft/EQ_ADDR_1")
    await passive.passive_gift_text(msg, _fsm_ctx())
    assert called["n"] == 0
    assert len(msg.out) == 1


@pytest.mark.asyncio
async def test_preview_card_does_not_show_raw_address(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(
        passive,
        "resolve_universal_nft",
        lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(_resolved_preview(), None))),
    )
    monkeypatch.setattr(
        passive,
        "extract_nft_preview_media",
        lambda *_a, **_k: type("M", (), {"url": None, "kind": "none", "mime_type": None, "source_field": None})(),
    )
    monkeypatch.setattr(passive.runtime_state, "nft_action_session_put", lambda *_a, **_k: "tok1")

    msg = _Msg("Pretty Posy #28864")
    await passive.passive_gift_text(msg, _fsm_ctx())
    blob = "\n".join(msg.out)
    assert "EQ_ADDR_1" not in blob


@pytest.mark.asyncio
async def test_preview_sends_animation_when_available(monkeypatch):
    class _Sess:
        async def __aenter__(self): return object()
        async def __aexit__(self, exc_type, exc, tb): return False

    class _UR:
        def __init__(self, _s): pass
        async def get_or_create(self, *_): return type("U", (), {"id": 1, "plan": "free"})()

    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(passive, "resolve_universal_nft", lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(_resolved_preview(), None))))
    monkeypatch.setattr(
        passive,
        "extract_nft_preview_media",
        lambda *_a, **_k: type("M", (), {"url": "https://x/a.gif", "kind": "animation", "mime_type": "image/gif", "source_field": "animation_url"})(),
    )
    monkeypatch.setattr(passive.runtime_state, "nft_action_session_put", lambda *_a, **_k: "tok1")
    msg = _Msg("Pretty Posy #28864")
    await passive.passive_gift_text(msg, _fsm_ctx())
    assert msg.animations


@pytest.mark.asyncio
async def test_preview_sends_video_when_available(monkeypatch):
    class _Sess:
        async def __aenter__(self): return object()
        async def __aexit__(self, exc_type, exc, tb): return False

    class _UR:
        def __init__(self, _s): pass
        async def get_or_create(self, *_): return type("U", (), {"id": 1, "plan": "free"})()

    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(passive, "resolve_universal_nft", lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(_resolved_preview(), None))))
    monkeypatch.setattr(
        passive,
        "extract_nft_preview_media",
        lambda *_a, **_k: type("M", (), {"url": "https://x/a.mp4", "kind": "video", "mime_type": "video/mp4", "source_field": "video"})(),
    )
    monkeypatch.setattr(passive.runtime_state, "nft_action_session_put", lambda *_a, **_k: "tok1")
    msg = _Msg("Pretty Posy #28864")
    await passive.passive_gift_text(msg, _fsm_ctx())
    assert msg.videos


@pytest.mark.asyncio
async def test_preview_sends_photo_when_only_image(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    class _Ton:
        def __init__(self, _s):
            pass

        async def get_nft(self, _a):
            return {}

    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(
        passive,
        "resolve_universal_nft",
        lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(_resolved_preview(), None))),
    )
    monkeypatch.setattr(passive, "TonAPICollectionClient", _Ton)
    monkeypatch.setattr(
        passive,
        "extract_nft_preview_media",
        lambda *_a, **_k: type(
            "M",
            (),
            {"url": "https://img.png", "kind": "photo", "mime_type": None, "source_field": "image"},
        )(),
    )
    monkeypatch.setattr(passive.runtime_state, "nft_action_session_put", lambda *_a, **_k: "tok1")
    msg = _Msg("Pretty Posy #28864")
    await passive.passive_gift_text(msg, _fsm_ctx())
    assert msg.photos
    assert msg.photos[0].get("reply_markup") is not None


@pytest.mark.asyncio
async def test_preview_text_fallback_when_no_media(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    class _Ton:
        def __init__(self, _s):
            pass

        async def get_nft(self, _a):
            return {}

    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(
        passive,
        "resolve_universal_nft",
        lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(_resolved_preview(), None))),
    )
    monkeypatch.setattr(passive, "TonAPICollectionClient", _Ton)
    monkeypatch.setattr(
        passive,
        "extract_nft_preview_media",
        lambda *_a, **_k: type("M", (), {"url": None, "kind": "none", "mime_type": None, "source_field": None})(),
    )
    monkeypatch.setattr(passive.runtime_state, "nft_action_session_put", lambda *_a, **_k: "tok1")
    msg = _Msg("Pretty Posy #28864")
    await passive.passive_gift_text(msg, _fsm_ctx())
    assert not msg.photos and not msg.animations and not msg.videos
    assert any("Что сделать?" in x for x in msg.out)


@pytest.mark.asyncio
async def test_preview_text_fallback_when_media_send_fails(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(
        passive,
        "resolve_universal_nft",
        lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(_resolved_preview(), None))),
    )
    monkeypatch.setattr(
        passive,
        "extract_nft_preview_media",
        lambda *_a, **_k: type(
            "M",
            (),
            {"url": "https://img.png", "kind": "photo", "mime_type": None, "source_field": "image"},
        )(),
    )
    monkeypatch.setattr(passive.runtime_state, "nft_action_session_put", lambda *_a, **_k: "tok1")
    msg = _Msg("Pretty Posy #28864")

    async def _boom(**_kwargs):
        raise RuntimeError("telegram rejected")

    msg.answer_photo = _boom
    await passive.passive_gift_text(msg, _fsm_ctx())
    assert any("Что сделать?" in x for x in msg.out)


@pytest.mark.asyncio
async def test_preview_buttons_attached_to_media_or_fallback(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    class _Ton:
        def __init__(self, _s):
            pass

        async def get_nft(self, _a):
            return {}

    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(
        passive,
        "resolve_universal_nft",
        lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(_resolved_preview(), None))),
    )
    monkeypatch.setattr(passive, "TonAPICollectionClient", _Ton)
    monkeypatch.setattr(
        passive,
        "extract_nft_preview_media",
        lambda *_a, **_k: type(
            "M",
            (),
            {"url": "https://img.png", "kind": "photo", "mime_type": None, "source_field": "image"},
        )(),
    )
    monkeypatch.setattr(passive.runtime_state, "nft_action_session_put", lambda *_a, **_k: "tok1")
    msg = _Msg("Pretty Posy #28864")
    await passive.passive_gift_text(msg, _fsm_ctx())
    kb = msg.photos[0].get("reply_markup")
    assert kb is not None
    texts = [b.text for row in kb.inline_keyboard for b in row]
    assert any(t.startswith("🔎 Проверить рынок") for t in texts)


@pytest.mark.asyncio
async def test_preview_caption_length_safe(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    class _Ton:
        def __init__(self, _s):
            pass

        async def get_nft(self, _a):
            return {}

    monkeypatch.setattr(passive, "_TELEGRAM_CAPTION_SAFE", 80)
    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(
        passive,
        "resolve_universal_nft",
        lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(_resolved_preview(), None))),
    )
    monkeypatch.setattr(passive, "TonAPICollectionClient", _Ton)
    monkeypatch.setattr(
        passive,
        "extract_nft_preview_media",
        lambda *_a, **_k: type(
            "M",
            (),
            {"url": "https://img.png", "kind": "photo", "mime_type": None, "source_field": "image"},
        )(),
    )
    monkeypatch.setattr(passive.runtime_state, "nft_action_session_put", lambda *_a, **_k: "tok1")
    msg = _Msg("Pretty Posy #28864")
    await passive.passive_gift_text(msg, _fsm_ctx())
    assert len(msg.photos) == 1
    cap = msg.photos[0].get("caption") or ""
    assert len(cap) < len("\n".join(x for x in msg.out if "Model:" in x))
    assert "Коллекция" in cap
    assert any("Model:" in x and "Что сделать?" in x for x in msg.out)


@pytest.mark.asyncio
async def test_no_user_facing_media_error_traceback(monkeypatch):
    class _Sess:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _UR:
        def __init__(self, _s):
            pass

        async def get_or_create(self, *_):
            return type("U", (), {"id": 1, "plan": "free"})()

    monkeypatch.setattr(passive, "SessionLocal", lambda: _Sess())
    monkeypatch.setattr(passive, "UserRepository", _UR)
    monkeypatch.setattr(
        passive,
        "resolve_universal_nft",
        lambda *_a, **_k: (__import__("asyncio").sleep(0, result=(_resolved_preview(), None))),
    )
    monkeypatch.setattr(
        passive,
        "extract_nft_preview_media",
        lambda *_a, **_k: type(
            "M",
            (),
            {"url": "https://x/bad.png", "kind": "photo", "mime_type": None, "source_field": "image"},
        )(),
    )
    monkeypatch.setattr(passive.runtime_state, "nft_action_session_put", lambda *_a, **_k: "tok1")
    msg = _Msg("Pretty Posy #28864")

    async def _boom(**_kwargs):
        raise RuntimeError("internal telegram error details")

    msg.answer_photo = _boom
    await passive.passive_gift_text(msg, _fsm_ctx())
    blob = "\n".join(msg.out)
    assert "traceback" not in blob.lower()
    assert "internal telegram" not in blob.lower()
    assert "Что сделать?" in blob


