"""UX прогресса и финала market check (/check)."""

from __future__ import annotations

import pytest

from app.services import gift_analysis_flow as gaf
from app.services.real_market_collection_scan import (
    FullMarketNftReport,
    SellPricePlan,
    TargetNftInfo,
    TraitComps,
    format_progress_message,
)


def _tc(trait: str, val: str | None) -> TraitComps:
    return TraitComps(trait_type=trait, trait_value=val, listings_count=0, floor=None, median=None)


def _report() -> FullMarketNftReport:
    tgt = TargetNftInfo(
        name="N",
        number=1,
        address="EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c",
        collection_name="C",
        collection_address="EQColl__________________________________________900",
        model="M",
        backdrop="B",
        symbol="S",
        image_url=None,
    )
    sp = SellPricePlan(
        quick_sell_ton=1.0,
        normal_list_ton=2.0,
        high_list_ton=3.0,
        dont_list_below_ton=0.5,
        confidence="low",
        confidence_reason="test",
    )
    return FullMarketNftReport(
        target=tgt,
        loaded_count=3000,
        listings_count=187,
        collection_floor=1.0,
        collection_median=2.0,
        same_model=_tc("model", "M"),
        same_backdrop=_tc("backdrop", "B"),
        same_symbol=_tc("symbol", "S"),
        close_comps=[],
        sell_plan=sp,
        is_partial_scan=False,
        source_label="TonAPI",
    )


@pytest.mark.asyncio
async def test_market_check_uses_single_progress_message():
    report = _report()
    edits: list[str] = []

    class _Bot:
        async def edit_message_text(self, text: str, **_k):
            edits.append(text)
            return None

    class _Msg:
        def __init__(self):
            self.chat = type("C", (), {"id": 1})()
            self.bot = _Bot()

        async def answer(self, *_a, **_k):
            raise AssertionError("no extra messages")

    message = _Msg()
    progress = type("P", (), {"message_id": 1, "chat": message.chat})()
    await gaf.deliver_full_market_nft_check_result(message, progress, report, telegram_id=1)
    assert len(edits) == 1


@pytest.mark.asyncio
async def test_final_report_edits_progress_message():
    report = _report()
    seen_mid: list[int] = []

    class _Bot:
        async def edit_message_text(self, _text: str, *, chat_id: int, message_id: int, **_k):
            seen_mid.append(message_id)
            return None

    class _Msg:
        def __init__(self):
            self.chat = type("C", (), {"id": 9})()
            self.bot = _Bot()

        async def answer(self, *_a, **_k):
            raise AssertionError("no answer")

    message = _Msg()
    progress = type("P", (), {"message_id": 77, "chat": message.chat})()
    await gaf.deliver_full_market_nft_check_result(message, progress, report, telegram_id=1)
    assert seen_mid == [77]


@pytest.mark.asyncio
async def test_no_done_message_before_final_report():
    report = _report()
    bodies: list[str] = []

    class _Bot:
        async def edit_message_text(self, text: str, **_k):
            bodies.append(text)
            return None

    class _Msg:
        def __init__(self):
            self.chat = type("C", (), {"id": 1})()
            self.bot = _Bot()

        async def answer(self, *_a, **_k):
            raise AssertionError("no answer")

    message = _Msg()
    progress = type("P", (), {"message_id": 1, "chat": message.chat})()
    await gaf.deliver_full_market_nft_check_result(message, progress, report, telegram_id=1)
    assert all("✅ Готово" not in b for b in bodies)


def test_no_collecting_prices_extra_message():
    """Прогресс скана не использует старый текст «Собираю цены…»."""
    txt = format_progress_message("X", 100, 5, phase="scan", lang="ru")
    assert "Собираю" not in txt
    assert "цены из открытых" not in txt.lower()


def test_progress_text_user_friendly():
    txt = format_progress_message("TestColl", 3000, 187, phase="scan", lang="ru")
    assert "⏳" in txt
    assert "3 000" in txt
    assert "187" in txt
    assert "TonAPI" in txt
    assert "Лимит страницы" not in txt


def test_long_report_is_compacted_not_split_into_spam(monkeypatch: pytest.MonkeyPatch):
    import app.services.real_market_collection_scan as rmcs

    report = _report()
    monkeypatch.setattr(rmcs, "format_full_market_nft_report", lambda _r: "Z" * 5000)
    out = rmcs.format_full_market_nft_report_for_telegram_edit(report, max_len=4090)
    assert len(out) <= 4090
    assert "кратко" in out.lower() or "…" in out
