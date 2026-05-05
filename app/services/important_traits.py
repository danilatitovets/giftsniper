from __future__ import annotations

from app.config import Settings
from app.schemas.gift import GiftAttributeSchema


def _keywords(settings: Settings) -> list[str]:
    raw = (settings.important_trait_keywords or "").strip()
    if not raw:
        return []
    return [k.strip().lower() for k in raw.split(",") if k.strip()]


def score_important_trait_keyword(trait_type: str, trait_value: str, settings: Settings) -> float:
    """Attention bonus 0..25; does not imply buy."""
    text = f"{trait_type} {trait_value}".lower()
    score = 0.0
    for kw in _keywords(settings):
        if kw and kw in text:
            score += 8.0
    return min(25.0, score)


def detect_important_traits(attributes: list[GiftAttributeSchema], settings: Settings) -> list[tuple[GiftAttributeSchema, float]]:
    out: list[tuple[GiftAttributeSchema, float]] = []
    for a in attributes:
        s = score_important_trait_keyword(a.trait_type, a.trait_value, settings)
        if s > 0:
            out.append((a, s))
    return sorted(out, key=lambda x: x[1], reverse=True)


def format_important_trait_notes(
    attributes: list[GiftAttributeSchema],
    settings: Settings,
    *,
    trait_sales_count: int,
    trait_floor_ton: float | None,
) -> list[str]:
    notes: list[str] = []
    hits = detect_important_traits(attributes, settings)
    if not hits:
        return notes
    for attr, bonus in hits[:3]:
        base = f"{attr.trait_type}: {attr.trait_value} — важный trait (внимание +{bonus:.0f})"
        if trait_sales_count < 2:
            notes.append(
                base + ". Продаж по trait мало — премиум спекулятивный; безопасный вход обычно ниже trait floor."
            )
        elif trait_floor_ton:
            notes.append(base + f". Проверьте trait floor ~{trait_floor_ton:.1f} TON и ликвидность.")
        else:
            notes.append(base + ". Нужны floor/продажи по trait для подтверждения.")
    return notes
