import pytest

from app.services.gift_intake import extract_buy_price_from_text, normalize_deal_subject


@pytest.mark.parametrize(
    "text,expected",
    [
        ("/deal x at 180", 180.0),
        ("/deal buy Ice Cream #1 for 180 TON", 180.0),
        ("price 199.5", 199.5),
        ("https://getgems.io/x?price=220", 220.0),
    ],
)
def test_extract_buy_price(text, expected):
    assert extract_buy_price_from_text(text) == expected


def test_normalize_deal_subject():
    assert "Ice Cream" in normalize_deal_subject("buy Ice Cream #1 for 180 TON")
