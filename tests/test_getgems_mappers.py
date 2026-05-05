import json
from pathlib import Path

from app.sources.mappers.getgems import parse_getgems_floor, parse_getgems_listings, parse_getgems_sales


def _load(name: str):
    path = Path("tests/fixtures/getgems") / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_parse_floor_from_fixture():
    payload = _load("collection_on_sale.json")
    floor = parse_getgems_floor(payload, collection="Ice Cream")
    assert floor is not None
    assert floor.floor_ton == 198.0


def test_parse_listings_sorted_by_price():
    payload = _load("collection_on_sale.json")
    listings = parse_getgems_listings(payload, collection="Ice Cream")
    assert len(listings) == 2
    assert listings[0].price_ton <= listings[1].price_ton


def test_parse_sales_from_fixture():
    payload = _load("collection_history.json")
    sales = parse_getgems_sales(payload, collection="Ice Cream")
    assert len(sales) == 2


def test_invalid_payload_does_not_crash():
    assert parse_getgems_floor({"bad": "shape"}) is None
    assert parse_getgems_listings({"bad": "shape"}) == []
    assert parse_getgems_sales({"bad": "shape"}) == []
