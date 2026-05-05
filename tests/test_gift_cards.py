from app.schemas.gift import GiftCard
from app.services.gift_cards import format_gift_analysis_card, format_gift_error_help


class _Est:
    recommendation = "BUY_FOR_FLIP"
    fair_price_ton = 210.0
    buy_zone_min_ton = 165.0
    buy_zone_max_ton = 185.0
    list_price_ton = 245.0
    expected_roi_percent = 18.0
    confidence_score = 64
    risk_score = 55
    reasons = ["floor свежий"]


def test_analysis_card_has_verdict_fair_buy_confidence():
    g = GiftCard(collection="Ice Cream", number=1)
    text = format_gift_analysis_card(g, _Est(), None, {}, compact=True)
    assert "Вердикт" in text
    assert "Справедливая цена" in text
    assert "Уверенность: 64/100" in text


def test_low_confidence_softens_buy():
    class Low(_Est):
        confidence_score = 40

    g = GiftCard(collection="Ice Cream", number=1)
    text = format_gift_analysis_card(g, Low(), None, {}, compact=False)
    assert "осторожно" in text.lower() or "Данных мало" in text


def test_error_help_lists_formats():
    h = format_gift_error_help("check")
    assert "/check" in h
    assert "seed" not in h.lower()
