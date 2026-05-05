import pytest
from datetime import datetime, timedelta, timezone

from app.db.models import AlertRule
from app.schemas.market import MarketFloor
from app.services.alerts import (
    evaluate_alert_rule,
    format_alert_notification,
    parse_alert_command,
    should_send_alert_notification,
    should_trigger_alert,
)
from app.sources.base import MarketSource


class DummySource(MarketSource):
    name = "mock"

    def __init__(self, collection_floor: float | None = None, trait_floor: float | None = None) -> None:
        self.collection_floor = collection_floor
        self.trait_floor = trait_floor

    async def get_collection_floor(self, collection: str):
        if self.collection_floor is None:
            return None
        return MarketFloor(collection=collection, source=self.name, floor_ton=self.collection_floor)

    async def get_trait_floor(self, collection: str, trait_type: str, trait_value: str):
        if self.trait_floor is None:
            return None
        return MarketFloor(collection=collection, source=self.name, floor_ton=self.trait_floor)

    async def get_recent_sales(self, collection: str, limit: int = 20):
        return []

    async def get_similar_listings(self, collection: str, attributes, limit: int = 20):
        return []

    async def search_underpriced(self, collection: str, filters: dict):
        return []


def test_parse_collection_below():
    parsed = parse_alert_command("/alert_add Ice Cream | below | 180")
    assert parsed.collection == "Ice Cream"
    assert parsed.max_price_ton == 180
    assert parsed.min_price_ton is None
    assert parsed.trait_type is None


def test_parse_collection_above():
    parsed = parse_alert_command("/alert_add Ice Cream | above | 250")
    assert parsed.collection == "Ice Cream"
    assert parsed.min_price_ton == 250
    assert parsed.max_price_ton is None


def test_parse_trait_below():
    parsed = parse_alert_command("/alert_add Ice Cream | Symbol | Moon | below | 190")
    assert parsed.collection == "Ice Cream"
    assert parsed.trait_type == "Symbol"
    assert parsed.trait_value == "Moon"
    assert parsed.max_price_ton == 190


def test_parse_trait_above():
    parsed = parse_alert_command("/alert_add Ice Cream | Symbol | Moon | above | 260")
    assert parsed.trait_type == "Symbol"
    assert parsed.trait_value == "Moon"
    assert parsed.min_price_ton == 260


def test_parse_invalid_format():
    with pytest.raises(ValueError):
        parse_alert_command("/alert_add Ice Cream below 180")


def test_parse_negative_price():
    with pytest.raises(ValueError):
        parse_alert_command("/alert_add Ice Cream | below | -10")


def test_should_trigger_below():
    rule = AlertRule(collection="Ice Cream", max_price_ton=180, is_active=True, user_id=1)
    assert should_trigger_alert(rule, {"collection_floor_ton": 175}) is True
    assert should_trigger_alert(rule, {"collection_floor_ton": 181}) is False


def test_should_trigger_above():
    rule = AlertRule(collection="Ice Cream", min_price_ton=250, is_active=True, user_id=1)
    assert should_trigger_alert(rule, {"collection_floor_ton": 260}) is True
    assert should_trigger_alert(rule, {"collection_floor_ton": 249}) is False


def test_should_send_alert_notification_first_trigger_sends():
    rule = AlertRule(collection="Ice Cream", user_id=1, last_is_triggered=False)
    eval_result = type("Eval", (), {"triggered": True})
    assert should_send_alert_notification(rule, eval_result, now=datetime.now(timezone.utc), cooldown_minutes=60) is True


def test_should_send_alert_notification_recent_trigger_does_not_send():
    rule = AlertRule(
        collection="Ice Cream",
        user_id=1,
        last_is_triggered=True,
        last_triggered_at=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    eval_result = type("Eval", (), {"triggered": True})
    assert should_send_alert_notification(rule, eval_result, now=datetime.now(timezone.utc), cooldown_minutes=60) is False


def test_should_send_alert_notification_cooldown_passed_sends_again():
    rule = AlertRule(
        collection="Ice Cream",
        user_id=1,
        last_is_triggered=True,
        last_triggered_at=datetime.now(timezone.utc) - timedelta(minutes=90),
    )
    eval_result = type("Eval", (), {"triggered": True})
    assert should_send_alert_notification(rule, eval_result, now=datetime.now(timezone.utc), cooldown_minutes=60) is True


def test_should_send_alert_notification_not_triggered_does_not_send():
    rule = AlertRule(collection="Ice Cream", user_id=1, last_is_triggered=False)
    eval_result = type("Eval", (), {"triggered": False})
    assert should_send_alert_notification(rule, eval_result, now=datetime.now(timezone.utc), cooldown_minutes=60) is False


@pytest.mark.asyncio
async def test_evaluate_collection_below():
    rule = AlertRule(id=1, collection="Ice Cream", user_id=1, max_price_ton=190)
    evaluation = await evaluate_alert_rule(rule, DummySource(collection_floor=186))
    assert evaluation.triggered is True


@pytest.mark.asyncio
async def test_evaluate_trait_below():
    rule = AlertRule(id=1, collection="Ice Cream", user_id=1, trait_type="Symbol", trait_value="Moon", max_price_ton=250)
    evaluation = await evaluate_alert_rule(rule, DummySource(collection_floor=186, trait_floor=240))
    assert evaluation.triggered is True


@pytest.mark.asyncio
async def test_evaluate_collection_above():
    rule = AlertRule(id=1, collection="Ice Cream", user_id=1, min_price_ton=180)
    evaluation = await evaluate_alert_rule(rule, DummySource(collection_floor=186))
    assert evaluation.triggered is True


@pytest.mark.asyncio
async def test_evaluate_trait_above():
    rule = AlertRule(id=1, collection="Ice Cream", user_id=1, trait_type="Symbol", trait_value="Moon", min_price_ton=230)
    evaluation = await evaluate_alert_rule(rule, DummySource(collection_floor=186, trait_floor=240))
    assert evaluation.triggered is True


@pytest.mark.asyncio
async def test_format_alert_notification_contains_explanation():
    rule = AlertRule(id=1, collection="Ice Cream", user_id=1, max_price_ton=190)
    evaluation = await evaluate_alert_rule(rule, DummySource(collection_floor=186))
    text = format_alert_notification(rule, evaluation)
    assert "Это не финансовый совет" in text
