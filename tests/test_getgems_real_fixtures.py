import json
from pathlib import Path

import pytest

from app.sources.mappers.getgems import parse_getgems_floor, parse_getgems_listings, parse_getgems_sales


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_real_on_sale_fixture_if_exists():
    folder = Path("tests/fixtures/getgems/real")
    files = list(folder.glob("on_sale_*.json")) if folder.exists() else []
    if not files:
        pytest.skip("No real Getgems fixtures")
    payload = _read(files[0])
    listings = parse_getgems_listings(payload, collection="Ice Cream")
    floor = parse_getgems_floor(payload, collection="Ice Cream")
    assert isinstance(listings, list)
    if listings:
        assert all(item.price_ton > 0 for item in listings)
        assert floor is not None
        assert floor.floor_ton == min(item.price_ton for item in listings)


def test_real_history_fixture_if_exists():
    folder = Path("tests/fixtures/getgems/real")
    files = list(folder.glob("history_*.json")) if folder.exists() else []
    if not files:
        pytest.skip("No real Getgems history fixtures")
    payload = _read(files[0])
    sales = parse_getgems_sales(payload, collection="Ice Cream")
    assert isinstance(sales, list)
    if sales:
        assert all(item.price_ton > 0 for item in sales)
