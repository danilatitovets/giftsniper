"""Confidence explanation and caps from data coverage (Stage 31)."""

from __future__ import annotations



def calculate_data_coverage_score(
    *,
    real_sales_count: int,
    listing_count: int,
    max_trait_sales: int | None,
    has_floor: bool,
    source_mock: bool,
    source_manual: bool,
    freshness_label: str,
) -> float:
    score = 30.0
    if has_floor:
        score += 15
    score += min(35.0, real_sales_count * 5.0)
    score += min(15.0, listing_count * 0.5)
    if max_trait_sales is not None and max_trait_sales > 0:
        score += min(15.0, max_trait_sales * 5.0)
    if source_mock:
        score -= 25
    if source_manual and not real_sales_count:
        score -= 10
    if freshness_label == "stale":
        score -= 8
    elif freshness_label == "old":
        score -= 18
    return max(0.0, min(100.0, score))


def calculate_prediction_confidence(
    base_confidence: float,
    coverage: float,
    *,
    journal_accuracy_hint: float | None = None,
) -> float:
    """Blend model confidence with coverage; optional journal win-rate hint 0..100."""
    out = base_confidence * 0.65 + coverage * 0.35
    if journal_accuracy_hint is not None:
        out = out * 0.85 + journal_accuracy_hint * 0.15
    return max(5.0, min(100.0, out))


def explain_confidence_cap(cap_reason: str, base_conf: float, after_cap: float) -> str:
    if not cap_reason:
        return f"Confidence {after_cap:.0f}/100 без жёсткого cap."
    return f"Confidence снижен с ~{base_conf:.0f} до {after_cap:.0f}: {cap_reason}"


def format_confidence_explanation(
    *,
    sources_used: list[str],
    sales_count: int,
    trait_sales_max: int | None,
    spread_percent: float | None,
    freshness_label: str,
    capped_reason: str | None,
) -> str:
    lines = [
        "📊 Confidence (покрытие данных):",
        f"- Источники: {', '.join(sources_used) or 'unknown'}",
        f"- Sales (sample): {sales_count}",
        f"- Trait sales (max по атрибутам): {trait_sales_max if trait_sales_max is not None else 'n/a'}",
        f"- Spread listings: {spread_percent or 0:.1f}%",
        f"- Freshness: {freshness_label}",
    ]
    if not sales_count:
        lines.append("- Нет недавних продаж — верх confidence ограничен (нет якоря сделок).")
    if trait_sales_max == 0:
        lines.append("- Редкий trait без продаж — премиум спекулятивный, cap на агрессивные buy.")
    if capped_reason:
        lines.append(f"- Cap: {capped_reason}")
    lines.append("- Это не гарантия прибыли, только качество входных данных.")
    return "\n".join(lines)
