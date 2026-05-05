"""Compare precision plans and explain price moves."""

from __future__ import annotations

from app.schemas.market_brain import PrecisionPricePlan


def compare_price_plans(old: PrecisionPricePlan, new: PrecisionPricePlan) -> list[str]:
    diffs: list[str] = []
    if abs(old.safe_buy_price_ton - new.safe_buy_price_ton) > 0.5:
        diffs.append(f"safe_buy {old.safe_buy_price_ton:.2f} → {new.safe_buy_price_ton:.2f}")
    if abs(old.max_buy_price_ton - new.max_buy_price_ton) > 0.5:
        diffs.append(f"max_buy {old.max_buy_price_ton:.2f} → {new.max_buy_price_ton:.2f}")
    if abs(old.normal_list_price_ton - new.normal_list_price_ton) > 0.5:
        diffs.append(f"normal_list {old.normal_list_price_ton:.2f} → {new.normal_list_price_ton:.2f}")
    if abs(old.confidence_score - new.confidence_score) >= 5:
        diffs.append(f"confidence {old.confidence_score:.0f} → {new.confidence_score:.0f}")
    if abs(old.liquidity_score - new.liquidity_score) >= 5:
        diffs.append(f"liquidity {old.liquidity_score:.0f} → {new.liquidity_score:.0f}")
    return diffs


def explain_price_change(diffs: list[str], *, old_fresh: str | None, new_fresh: str | None) -> list[str]:
    reasons = list(diffs)
    if old_fresh and new_fresh and old_fresh != new_fresh:
        reasons.append(f"freshness {old_fresh} → {new_fresh}")
    return reasons


def format_price_change_explanation(reasons: list[str]) -> str:
    if not reasons:
        return "Значимых изменений уровней цен не обнаружено."
    return "Изменения модели:\n" + "\n".join(f"- {r}" for r in reasons[:12])
