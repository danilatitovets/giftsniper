from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone


SMART_ALERT_TYPES = {
    "regime_change",
    "strength_drop",
    "liquidity_crash",
    "data_stale",
    "concentration_risk",
    "rebalance_needed",
    "stay_in_cash",
}


def payload_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def should_send_smart_alert(last_sent_at: datetime | None, cooldown_minutes: int, new_hash: str, old_hash: str | None) -> bool:
    if old_hash == new_hash:
        return False
    if last_sent_at is None:
        return True
    now = datetime.now(timezone.utc)
    ts = last_sent_at if last_sent_at.tzinfo else last_sent_at.replace(tzinfo=timezone.utc)
    return now - ts >= timedelta(minutes=cooldown_minutes)


def evaluate_regime_change(user, current_regime: str, previous_state) -> tuple[bool, str]:
    prev = getattr(previous_state, "last_regime", None)
    if prev is None or prev == current_regime:
        return False, ""
    text = f"🌡 Market Regime Changed\n\nБыло: {prev}\nСтало: {current_regime}"
    return True, text


def evaluate_strength_drop(collection_report, previous_state, threshold: float) -> tuple[bool, str]:
    prev = getattr(previous_state, "last_strength_score", None)
    curr = float(collection_report.relative_strength_score)
    if prev is None or (prev - curr) < threshold:
        return False, ""
    text = (
        f"📉 Strength Drop\n\nКоллекция: {collection_report.collection}\n"
        f"Было: {prev:.1f}\nСтало: {curr:.1f}\nПадение: {prev-curr:.1f}"
    )
    return True, text


def evaluate_liquidity_crash(collection_report, threshold: float) -> tuple[bool, str]:
    curr = float(collection_report.liquidity_score)
    if curr > threshold:
        return False, ""
    return True, f"💧 Liquidity Crash\n\n{collection_report.collection}: liquidity {curr:.0f}/100 (порог {threshold:.0f})"


def evaluate_data_stale(collection_report, threshold_minutes: int) -> tuple[bool, str]:
    stale_like = collection_report.freshness_label in {"stale", "old", "unknown"}
    if not stale_like:
        return False, ""
    return True, f"⏱ Data Stale\n\n{collection_report.collection}: freshness {collection_report.freshness_label} (threshold {threshold_minutes}m)"


def evaluate_concentration_risk(portfolio: list[dict], user_settings) -> tuple[bool, str]:
    total = sum(float(x.get("value_ton", 0.0)) for x in portfolio)
    if total <= 0:
        return False, ""
    limit = float(user_settings.max_collection_percent or 40)
    by_collection: dict[str, float] = {}
    for row in portfolio:
        by_collection[row["collection"]] = by_collection.get(row["collection"], 0.0) + float(row.get("value_ton", 0.0))
    top_name, top_value = max(by_collection.items(), key=lambda x: x[1])
    pct = top_value / total * 100.0
    if pct <= limit:
        return False, ""
    text = (
        "⚠️ Concentration Risk\n\n"
        f"{pct:.0f}% портфеля в {top_name}.\nЛимит: {limit:.0f}%\n\n"
        "Рекомендация:\n- не докупать перегруженную коллекцию\n- искать альтернативы в universe"
    )
    return True, text


def evaluate_rebalance_needed(portfolio: list[dict], universe_report) -> tuple[bool, str]:
    if not portfolio:
        return False, ""
    weak = [x for x in universe_report if x.recommendation in {"REDUCE_EXPOSURE", "AVOID_FOR_NOW"}]
    if not weak:
        return False, ""
    names = ", ".join(x.collection for x in weak[:3])
    return True, f"⚖️ Rebalance Needed\n\nПроблемные коллекции: {names}\nРассмотрите снижение экспозиции."


def evaluate_stay_in_cash(market_regime, opportunities: list[dict]) -> tuple[bool, str]:
    best_tier = opportunities[0]["score"].final_rank_label if opportunities else "AVOID"
    if market_regime.regime in {"data_poor", "illiquid"} or best_tier in {"C_TIER", "AVOID"}:
        text = (
            "🧊 Stay in Cash Signal\n\n"
            "Сейчас лучше не входить.\n"
            f"Причина:\n- market regime: {market_regime.regime}\n- лучший tier: {best_tier}\n"
            "Действие:\n- обновить данные\n- ждать более сильных сигналов"
        )
        return True, text
    return False, ""


def format_smart_alert(title: str, body: str) -> str:
    return f"{title}\n\n{body}\n\nЭто не финансовый совет."
