"""Доставка результата /check (TonAPI): одно сообщение — правка progress."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services import gift_analysis_flow as gaf
from app.services.real_market_collection_scan import (
    FullMarketNftReport,
    SellPricePlan,
    TargetNftInfo,
    TraitComps,
    format_nft_check_compact_caption_html,
)


def _tc(trait: str, val: str | None) -> TraitComps:
    return TraitComps(trait_type=trait, trait_value=val, listings_count=0, floor=None, median=None)


def _sample_report(
    *,
    image_url: str | None,
    rich_preview_url: str | None = None,
    rich_preview_kind: str | None = None,
) -> FullMarketNftReport:
    tgt = TargetNftInfo(
        name="Ice Gift",
        number=1,
        address="EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c",
        collection_name="Демо коллекция",
        collection_address="EQColl__________________________________________900",
        model="Zen",
        backdrop="Azure",
        symbol="Star",
        image_url=image_url,
        rich_preview_url=rich_preview_url,
        rich_preview_kind=rich_preview_kind,
    )
    sp = SellPricePlan(
        quick_sell_ton=10.0,
        normal_list_ton=12.0,
        high_list_ton=15.0,
        dont_list_below_ton=8.0,
        confidence="medium",
        confidence_reason="Достаточно листингов.",
    )
    return FullMarketNftReport(
        target=tgt,
        loaded_count=100,
        listings_count=40,
        collection_floor=5.0,
        collection_median=7.0,
        same_model=_tc("model", "Zen"),
        same_backdrop=_tc("backdrop", "Azure"),
        same_symbol=_tc("symbol", "Star"),
        close_comps=[],
        sell_plan=sp,
        is_partial_scan=False,
        source_label="TonAPI, реальные листинги",
    )


@pytest.mark.asyncio
async def test_check_edits_progress_only_no_extra_media():
    report = _sample_report(
        image_url="https://cdn.tonapi.example/nft.png",
        rich_preview_url="https://cdn.tonapi.example/nft.mp4",
        rich_preview_kind="video",
    )
    edits: list[dict] = []

    class _Bot:
        async def edit_message_text(self, *a, **k):
            edits.append({"args": a, "kwargs": k})
            return None

    class _Msg:
        def __init__(self):
            self.chat = type("C", (), {"id": 1})()
            self.bot = _Bot()

        async def answer_photo(self, **_k):
            raise AssertionError("answer_photo must not be used")

        async def answer_animation(self, **_k):
            raise AssertionError("answer_animation must not be used")

        async def answer_video(self, **_k):
            raise AssertionError("answer_video must not be used")

        async def answer(self, *_a, **_k):
            raise AssertionError("answer must not be used when edit succeeds")

    message = _Msg()
    progress = type("P", (), {"message_id": 42, "chat": message.chat})()
    await gaf.deliver_full_market_nft_check_result(message, progress, report, telegram_id=4242)
    assert len(edits) == 1
    body = edits[0]["args"][0]
    assert "Проверка NFT" in body
    assert "✅ Готово" not in body
    assert edits[0]["kwargs"].get("reply_markup") is not None


@pytest.mark.asyncio
async def test_check_falls_back_to_answer_when_edit_fails():
    report = _sample_report(image_url=None)
    answers: list[str] = []

    class _Bot:
        async def edit_message_text(self, *a, **k):
            raise RuntimeError("cannot edit")

    class _Msg:
        def __init__(self):
            self.chat = type("C", (), {"id": 1})()
            self.bot = _Bot()

        async def answer(self, text: str = "", **kwargs):
            answers.append(text)
            return MagicMock()

    message = _Msg()
    progress = type("P", (), {"message_id": 99, "chat": message.chat})()
    await gaf.deliver_full_market_nft_check_result(message, progress, report, telegram_id=4242)
    assert len(answers) == 1
    assert "Проверка NFT" in answers[0]


def test_photo_caption_helper_still_valid_for_other_flows():
    cap = format_nft_check_compact_caption_html(_sample_report(image_url="https://x/y.png"))
    assert "Ice Gift" in cap
    assert "10" in cap or "12" in cap
    assert "TonAPI" in cap


def test_no_mock_words_in_photo_caption():
    cap = format_nft_check_compact_caption_html(_sample_report(image_url=None))
    low = cap.lower()
    assert "mock" not in low
    assert "test" not in low
    assert "тест" not in low
    assert "заглушка" not in low


def test_caption_not_too_long():
    cap = format_nft_check_compact_caption_html(_sample_report(image_url=None))
    assert len(cap) <= 1024
    from app.services.real_market_collection_scan import NFT_CHECK_PHOTO_CAPTION_SAFE

    assert len(cap) <= NFT_CHECK_PHOTO_CAPTION_SAFE + 200
