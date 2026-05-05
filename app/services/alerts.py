from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.db.models import AlertRule
from app.schemas.analysis import PriceEstimate
from app.schemas.market import ListingSchema
from app.sources.base import MarketSource


@dataclass(slots=True)
class ParsedAlertCommand:
    collection: str
    trait_type: str | None
    trait_value: str | None
    max_price_ton: float | None
    min_price_ton: float | None


@dataclass(slots=True)
class AlertEvaluation:
    rule_id: int
    collection: str
    trait_type: str | None
    trait_value: str | None
    current_value_ton: float | None
    condition_text: str
    triggered: bool
    source: str
    reason: str


def parse_alert_command(text: str) -> ParsedAlertCommand:
    payload = text.removeprefix("/alert_add").strip()
    if not payload:
        raise ValueError("Пустая команда. Добавьте параметры после /alert_add.")
    parts = [part.strip() for part in payload.split("|")]
    if len(parts) not in (3, 5):
        raise ValueError("Неверный формат. Используйте 3 или 5 частей через '|'.")

    if len(parts) == 3:
        collection, direction, price_raw = parts
        trait_type = None
        trait_value = None
    else:
        collection, trait_type, trait_value, direction, price_raw = parts
        if not trait_type or not trait_value:
            raise ValueError("Для trait-правила нужны trait_type и trait_value.")

    if not collection:
        raise ValueError("Коллекция обязательна.")
    direction = direction.lower()
    if direction not in ("below", "above"):
        raise ValueError("Допустимые операторы: below или above.")
    try:
        price = float(price_raw.replace(",", "."))
    except ValueError as exc:
        raise ValueError("Цена должна быть числом.") from exc
    if price <= 0:
        raise ValueError("Цена должна быть положительным числом.")

    max_price_ton = price if direction == "below" else None
    min_price_ton = price if direction == "above" else None
    return ParsedAlertCommand(
        collection=collection,
        trait_type=trait_type,
        trait_value=trait_value,
        max_price_ton=max_price_ton,
        min_price_ton=min_price_ton,
    )


def should_trigger_alert(rule: AlertRule, market_data: dict) -> bool:
    price = market_data.get("trait_floor_ton") if rule.trait_type and rule.trait_value else market_data.get("collection_floor_ton")
    if price is None:
        return False
    if rule.max_price_ton is not None and price <= rule.max_price_ton:
        return True
    if rule.min_price_ton is not None and price >= rule.min_price_ton:
        return True
    return False


def _build_condition_text(rule: AlertRule) -> str:
    metric = "trait floor" if rule.trait_type and rule.trait_value else "floor"
    if rule.max_price_ton is not None:
        return f"{metric} <= {rule.max_price_ton:.2f} TON"
    return f"{metric} >= {rule.min_price_ton:.2f} TON"


async def evaluate_alert_rule(rule: AlertRule, market_source: MarketSource) -> AlertEvaluation:
    trait_mode = bool(rule.trait_type and rule.trait_value)
    floor = await market_source.get_collection_floor(rule.collection)
    value = floor.floor_ton if floor else None
    if trait_mode:
        trait_floor = await market_source.get_trait_floor(rule.collection, rule.trait_type or "", rule.trait_value or "")
        value = trait_floor.floor_ton if trait_floor else None
    quality = getattr(market_source, "last_quality", None)
    source_name = market_source.name
    if quality and quality.sources_used:
        source_name = ", ".join(quality.sources_used)

    triggered = False
    reason = "Нет рыночных данных по правилу."
    if value is not None:
        if rule.max_price_ton is not None:
            triggered = value <= rule.max_price_ton
            reason = "Текущая цена ниже или равна целевому порогу." if triggered else "Цена пока выше заданного порога."
        elif rule.min_price_ton is not None:
            triggered = value >= rule.min_price_ton
            reason = "Текущая цена выше или равна целевому порогу." if triggered else "Цена пока ниже заданного порога."

    return AlertEvaluation(
        rule_id=rule.id,
        collection=rule.collection,
        trait_type=rule.trait_type,
        trait_value=rule.trait_value,
        current_value_ton=value,
        condition_text=_build_condition_text(rule),
        triggered=triggered,
        source=source_name,
        reason=reason,
    )


def should_send_alert_notification(
    rule: AlertRule, evaluation: AlertEvaluation, now: datetime, cooldown_minutes: int = 60
) -> bool:
    if not evaluation.triggered:
        return False
    if not rule.last_is_triggered:
        return True
    if rule.last_triggered_at is None:
        return True
    if rule.last_triggered_at.tzinfo is None:
        last_triggered = rule.last_triggered_at.replace(tzinfo=timezone.utc)
    else:
        last_triggered = rule.last_triggered_at
    return now - last_triggered >= timedelta(minutes=cooldown_minutes)


def format_alert_rule(rule: AlertRule) -> str:
    state = "✅" if rule.is_active else "⏸"
    condition = _build_condition_text(rule)
    trait_line = f"\nTrait: {rule.trait_type} = {rule.trait_value}" if rule.trait_type and rule.trait_value else ""
    return f"#{rule.id} {state} {rule.collection}{trait_line}\nУсловие: {condition}"


def format_alert_test_result(rule: AlertRule, market_data: dict, triggered: bool) -> str:
    price = market_data.get("trait_floor_ton") if rule.trait_type and rule.trait_value else market_data.get("collection_floor_ton")
    source = market_data.get("source", "unknown")
    condition = _build_condition_text(rule)
    trait_line = f"\nTrait: {rule.trait_type} = {rule.trait_value}" if rule.trait_type and rule.trait_value else ""
    status = "сработает" if triggered else "пока не сработает"
    price_text = f"{price:.2f} TON" if price is not None else "нет данных"
    return (
        f"🧪 Проверка уведомления #{rule.id}\n\n"
        f"Коллекция: {rule.collection}{trait_line}\n"
        f"Текущая цена: {price_text}\n"
        f"Условие: {condition}\n"
        f"Источник: {source}\n\n"
        f"Статус: {status}"
    )


def format_alert_notification(rule: AlertRule, evaluation: AlertEvaluation) -> str:
    trait_line = (
        f"\nTrait: {rule.trait_type} = {rule.trait_value}"
        if rule.trait_type and rule.trait_value
        else ""
    )
    value_text = f"{evaluation.current_value_ton:.2f} TON" if evaluation.current_value_ton is not None else "нет данных"
    source_text = evaluation.source.title()
    if "mock" in evaluation.source.lower():
        source_text = "Mock / тестовые данные"
    return (
        "🚨 Сработало уведомление\n\n"
        f"Коллекция: {rule.collection}{trait_line}\n"
        f"Текущая цена: {value_text}\n"
        f"Условие: {evaluation.condition_text}\n"
        f"Источник: {source_text}\n\n"
        "Что это значит:\n"
        "Цена достигла заданного уровня. Проверь лот/рынок вручную перед сделкой.\n\n"
        "Важно:\n"
        "Это не финансовый совет. Бот не совершает сделки автоматически."
    )


def format_flip_alert(listing: ListingSchema, estimate: PriceEstimate) -> str:
    potential = ((estimate.fair_price_ton - listing.price_ton) / listing.price_ton) * 100 if listing.price_ton else 0
    return (
        "🚨 Найден возможный флип\n\n"
        f"Коллекция: {listing.collection}\n"
        f"Цена: {listing.price_ton:.2f} TON\n"
        f"Оценка fair: {estimate.fair_price_ton:.2f} TON\n"
        f"Потенциал: +{potential:.1f}%\n"
        f"Источник: {listing.source.title()}\n"
        "Риск: medium"
    )
