from app.services.trade_import import format_trade_import_preview, parse_trade_csv, validate_trade_row


def test_parse_trade_csv_basic():
    raw = "collection,buy_price_ton\nIce,10.5\nCake,20\n"
    fields, rows = parse_trade_csv(raw)
    assert "collection" in fields
    assert len(rows) == 2
    assert rows[0]["buy_price_ton"] == "10.5"


def test_validate_good_and_bad_rows():
    ok, _ = validate_trade_row({"collection": "A", "buy_price_ton": "5"}, 2)
    assert ok
    ok2, err = validate_trade_row({"collection": "", "buy_price_ton": "5"}, 3)
    assert not ok2
    ok3, err3 = validate_trade_row({"collection": "A", "buy_price_ton": "-1"}, 4)
    assert not ok3


def test_format_preview():
    fields, rows = parse_trade_csv("collection,buy_price_ton\nX,1\n")
    txt = format_trade_import_preview(fields, rows, [])
    assert "Import preview" in txt or "Импорт" in txt


