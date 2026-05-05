from app.sources.mappers.getgems import parse_ton_price


def test_parse_ton_price_cases():
    assert parse_ton_price("186") == 186
    assert parse_ton_price(186) == 186
    assert parse_ton_price(186.5) == 186.5
    assert parse_ton_price("186000000000") == 186
    assert parse_ton_price({"amount": "186000000000", "currency": "TON"}) == 186
    assert parse_ton_price(None) is None
    assert parse_ton_price("invalid") is None
