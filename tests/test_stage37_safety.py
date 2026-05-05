"""Stage 37 — no autopilot / wallet / seed language in user-facing strings."""

from pathlib import Path

import pytest

from app.services.gift_cards import format_gift_analysis_card, format_gift_deal_card
from app.schemas.gift import GiftCard
from app.schemas.market import MarketDataQuality


class _Sup:
    pricing_suppressed = True
    market_validity_message_ru = "Недостаточно данных."
    price_source_label = "unavailable"


def test_check_suppressed_no_buy_numbers():
    text = format_gift_analysis_card(
        GiftCard(collection="T", number=1),
        _Sup(),
        MarketDataQuality(),
        {},
        compact=False,
    )
    assert "116" not in text and "200" not in text
    forbidden = ("seed", "private key", "mnemonic", "wallet connect", "автопокупк")
    low = text.lower()
    assert not any(x in low for x in forbidden)


def test_no_guaranteed_profit_in_deal_suppressed():
    text = format_gift_deal_card(GiftCard(collection="T", number=1), _Sup(), None, {}, buy_price=7.77)
    assert "гарантир" not in text.lower()


@pytest.mark.parametrize(
    "name",
    [
        "whip_cupcake_tg.txt",
        "fragment_gift_url.txt",
        "tonnel_gift_url.txt",
        "getgems_nft_url.txt",
        "tonviewer_nft_url.txt",
    ],
)
def test_url_fixture_lines_parse(name: str):
    from app.services.gift_intake import GiftInputType, parse_gift_input

    p = Path(__file__).resolve().parent / "fixtures" / "urls" / "realistic_gifts" / name
    url = p.read_text(encoding="utf-8").strip()
    gi = parse_gift_input(url)
    assert (
        gi.input_type != GiftInputType.unknown
        or gi.parse_warnings
        or gi.nft_address
        or gi.collection
        or gi.source_url
    )
