from datetime import datetime, timedelta, timezone

import pytest

from app.sources.manual import ManualSource
from app.bot.handlers.market import _age_text


class _ScalarList:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, floor=None, trait=None):
        self.floor = floor
        self.trait = trait

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def scalar(self, stmt):  # noqa: ARG002
        text = str(stmt)
        if "trait_floors" in text:
            return self.trait
        return self.floor

    async def scalars(self, stmt):  # noqa: ARG002
        return _ScalarList([])


@pytest.mark.asyncio
async def test_manual_source_returns_latest_floor(monkeypatch):
    row = type(
        "R",
        (),
        {
            "collection": "Ice Cream",
            "floor_ton": 186.0,
            "volume_24h_ton": None,
            "listed_count": 10,
            "created_at": datetime.now(timezone.utc),
        },
    )()
    monkeypatch.setattr("app.sources.manual.SessionLocal", lambda: _FakeSession(floor=row))
    source = ManualSource(user_id=1)
    floor = await source.get_collection_floor("Ice Cream")
    assert floor is not None
    assert floor.floor_ton == 186.0


@pytest.mark.asyncio
async def test_manual_source_returns_trait_floor(monkeypatch):
    row = type("R", (), {"collection": "Ice Cream", "floor_ton": 240.0, "created_at": datetime.now(timezone.utc)})()
    monkeypatch.setattr("app.sources.manual.SessionLocal", lambda: _FakeSession(trait=row))
    source = ManualSource(user_id=1)
    floor = await source.get_trait_floor("Ice Cream", "Symbol", "Moon")
    assert floor is not None
    assert floor.floor_ton == 240.0


@pytest.mark.asyncio
async def test_manual_source_returns_empty_without_user():
    source = ManualSource(user_id=None)
    assert await source.get_collection_floor("Ice Cream") is None
    assert await source.get_recent_sales("Ice Cream") == []


def test_market_data_formats_age():
    label, text = _age_text(datetime.now(timezone.utc) - timedelta(minutes=20))
    assert label == "fresh"
    assert "мин назад" in text
