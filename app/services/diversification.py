from __future__ import annotations

from collections import Counter, defaultdict


def calculate_collection_exposure(portfolio: list[dict]) -> dict[str, float]:
    exposure: defaultdict[str, float] = defaultdict(float)
    total = 0.0
    for row in portfolio:
        value = float(row.get("value_ton", 0.0))
        total += value
        exposure[row.get("collection", "unknown")] += value
    if total <= 0:
        return {}
    return {k: round(v / total * 100.0, 2) for k, v in exposure.items()}


def calculate_trait_exposure(portfolio: list[dict]) -> dict[str, float]:
    counter: Counter[str] = Counter()
    total = 0
    for row in portfolio:
        traits = row.get("traits", [])
        for trait in traits:
            key = f"{trait.get('trait_type')}={trait.get('trait_value')}"
            counter[key] += 1
            total += 1
    if total == 0:
        return {}
    return {k: round(v / total * 100.0, 2) for k, v in counter.items()}


def calculate_diversification_score(portfolio: list[dict]) -> int:
    if not portfolio:
        return 60
    collection_exp = calculate_collection_exposure(portfolio)
    if not collection_exp:
        return 60
    max_collection = max(collection_exp.values())
    score = 100 - int(max_collection * 0.8)
    if len(collection_exp) == 1:
        score -= 10
    return max(20, min(95, score))


def get_concentration_warnings(portfolio: list[dict], user_settings) -> list[str]:
    warnings: list[str] = []
    collection_exp = calculate_collection_exposure(portfolio)
    trait_exp = calculate_trait_exposure(portfolio)
    collection_limit = float(user_settings.max_collection_percent or 40)
    for name, pct in collection_exp.items():
        if pct > collection_limit:
            warnings.append(f"{pct:.0f}% портфеля в {name} — выше лимита {collection_limit:.0f}%")
    for trait, pct in trait_exp.items():
        if pct > 60:
            warnings.append(f"Сильная trait-концентрация: {trait} ({pct:.0f}%)")
    return warnings
