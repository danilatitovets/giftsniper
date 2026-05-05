"""Scenario-based QA for pricing / decisions (Stage 31)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.config import Settings, get_settings
from app.schemas.gift import GiftAttributeSchema, GiftCard
from app.schemas.market_brain import CollectionMarketProfile, PrecisionPricePlan
from app.services.decision_engine import make_buy_decision
from app.services.pricing import calculate_precision_price_plan, estimate_gift_price


@dataclass
class CalibrationScenario:
    name: str
    collection: str
    number: int | None
    attributes: list[dict]
    listing_price_ton: float
    collection_floor_ton: float
    trait_floor_ton: float | None
    recent_sales: list[float]
    trait_recent_sales: list[float]
    similar_listings: list[float] | None = None
    expected_decision: str | None = None
    expected_safe_buy_range: tuple[float, float] | None = None
    expected_max_buy_range: tuple[float, float] | None = None
    expected_list_range: tuple[float, float] | None = None
    expected_risk_range: tuple[int, int] | None = None
    expected_confidence_range: tuple[int, int] | None = None
    notes: str = ""


@dataclass
class CalibrationResult:
    scenario_name: str
    passed: bool
    actual_decision: str
    actual_safe_buy: float
    actual_max_buy: float
    actual_list_price: float
    actual_confidence: int
    actual_risk: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _scenario_from_dict(d: dict) -> CalibrationScenario:
    return CalibrationScenario(
        name=d["name"],
        collection=d["collection"],
        number=d.get("number"),
        attributes=list(d.get("attributes") or []),
        listing_price_ton=float(d["listing_price_ton"]),
        collection_floor_ton=float(d["collection_floor_ton"]),
        trait_floor_ton=float(d["trait_floor_ton"]) if d.get("trait_floor_ton") is not None else None,
        recent_sales=[float(x) for x in d.get("recent_sales") or []],
        trait_recent_sales=[float(x) for x in d.get("trait_recent_sales") or []],
        similar_listings=[float(x) for x in d["similar_listings"]] if d.get("similar_listings") else None,
        expected_decision=d.get("expected_decision"),
        expected_safe_buy_range=tuple(d["expected_safe_buy_range"]) if d.get("expected_safe_buy_range") else None,
        expected_max_buy_range=tuple(d["expected_max_buy_range"]) if d.get("expected_max_buy_range") else None,
        expected_list_range=tuple(d["expected_list_range"]) if d.get("expected_list_range") else None,
        expected_risk_range=tuple(d["expected_risk_range"]) if d.get("expected_risk_range") else None,
        expected_confidence_range=tuple(d["expected_confidence_range"]) if d.get("expected_confidence_range") else None,
        notes=d.get("notes") or "",
    )


def load_calibration_scenarios(base: Path | None = None) -> list[CalibrationScenario]:
    root = base or Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "calibration" / "scenarios"
    if not root.exists():
        return []
    out: list[CalibrationScenario] = []
    for p in sorted(root.glob("*.json")):
        out.append(_scenario_from_dict(json.loads(p.read_text(encoding="utf-8"))))
    return out


def run_calibration_scenario(scenario: CalibrationScenario, settings: Settings | None = None) -> CalibrationResult:
    settings = settings or get_settings()
    attrs = [GiftAttributeSchema(trait_type=a["trait_type"], trait_value=a["trait_value"]) for a in scenario.attributes]
    gift = GiftCard(collection=scenario.collection, number=scenario.number or 1, attributes=attrs)
    trait_floors = [scenario.trait_floor_ton] if scenario.trait_floor_ton else []
    if scenario.similar_listings:
        sim = scenario.similar_listings
    elif scenario.recent_sales:
        med = sorted(scenario.recent_sales)[len(scenario.recent_sales) // 2]
        sim = [med * 0.96, med * 1.04, scenario.listing_price_ton * 0.98, scenario.listing_price_ton * 1.02]
    else:
        sim = [scenario.listing_price_ton * 0.95, scenario.listing_price_ton * 1.05]
    market_data = {
        "collection_floor": scenario.collection_floor_ton,
        "listed_count": 20,
        "trait_floors": [t for t in trait_floors if t],
        "recent_sales": scenario.recent_sales,
        "similar_listings": sim,
    }
    base = estimate_gift_price(
        gift,
        market_data,
        risk_mode="normal",
        buy_price_ton=scenario.listing_price_ton,
        marketplace_fee_percent=settings.default_marketplace_fee_percent,
        estimated_extra_costs_ton=settings.estimated_extra_costs_ton,
        min_profit_ton=settings.min_profit_ton,
        settings=settings,
    )
    coll = CollectionMarketProfile(
        collection=scenario.collection,
        collection_floor_ton=scenario.collection_floor_ton,
        recent_sales_count=len(scenario.recent_sales),
        median_sale_price_ton=sorted(scenario.recent_sales)[len(scenario.recent_sales) // 2] if scenario.recent_sales else None,
        liquidity_score=68.0,
        spread_percent=10.0,
    )
    plan = calculate_precision_price_plan(
        base,
        coll,
        risk_mode="normal",
        marketplace_fee_percent=settings.default_marketplace_fee_percent,
        estimated_extra_costs_ton=settings.estimated_extra_costs_ton,
        min_profit_ton=settings.min_profit_ton,
        floor=scenario.collection_floor_ton,
        median_sale=coll.median_sale_price_ton,
        sales_count=len(scenario.recent_sales),
        listing_low=min(market_data["similar_listings"]),
        combined_liquidity_adj_rarity=40.0,
        is_mock_or_stale=False,
        settings=settings,
    )
    max_trait_sales = 1 if scenario.trait_recent_sales else 0
    strong_ok = max_trait_sales >= 1 or not attrs
    trait_opp_for_decision = 50.0 if (max_trait_sales or not attrs) else 20.0
    dec = make_buy_decision(
        buy_price=scenario.listing_price_ton,
        plan=plan,
        base=base,
        trait_opp_score=trait_opp_for_decision,
        combined_rarity_adj=50.0 if attrs else 20.0,
        sales_count=len(scenario.recent_sales),
        market_regime=None,
        settings=settings,
        strong_buy_trait_ok=strong_ok,
        spread_percent=coll.spread_percent,
    )
    errors: list[str] = []
    if scenario.expected_decision and dec.decision != scenario.expected_decision:
        errors.append(f"decision want {scenario.expected_decision} got {dec.decision}")
    lo, hi = scenario.expected_safe_buy_range or (0, 1e9)
    if scenario.expected_safe_buy_range and not (lo <= plan.safe_buy_price_ton <= hi):
        errors.append(f"safe_buy {plan.safe_buy_price_ton} not in [{lo},{hi}]")
    lo, hi = scenario.expected_confidence_range or (0, 100)
    if scenario.expected_confidence_range and not (lo <= base.confidence_score <= hi):
        errors.append(f"confidence {base.confidence_score} not in [{lo},{hi}]")
    lo, hi = scenario.expected_max_buy_range or (0, 1e9)
    if scenario.expected_max_buy_range and not (lo <= plan.max_buy_price_ton <= hi):
        errors.append(f"max_buy {plan.max_buy_price_ton} not in [{lo},{hi}]")
    lo, hi = scenario.expected_list_range or (0, 1e9)
    if scenario.expected_list_range and not (lo <= plan.normal_list_price_ton <= hi):
        errors.append(f"list {plan.normal_list_price_ton} not in [{lo},{hi}]")
    lo, hi = scenario.expected_risk_range or (0, 100)
    if scenario.expected_risk_range and not (lo <= base.risk_score <= hi):
        errors.append(f"risk {base.risk_score} not in [{lo},{hi}]")
    return CalibrationResult(
        scenario_name=scenario.name,
        passed=not errors,
        actual_decision=dec.decision,
        actual_safe_buy=plan.safe_buy_price_ton,
        actual_max_buy=plan.max_buy_price_ton,
        actual_list_price=plan.normal_list_price_ton,
        actual_confidence=int(base.confidence_score),
        actual_risk=int(base.risk_score),
        errors=errors,
        warnings=[],
    )


def run_all_calibration_scenarios(
    scenarios: list[CalibrationScenario] | None = None,
    *,
    settings: Settings | None = None,
) -> list[CalibrationResult]:
    sc = scenarios or load_calibration_scenarios()
    return [run_calibration_scenario(s, settings=settings) for s in sc]


def format_calibration_report(results: list[CalibrationResult]) -> str:
    ok = sum(1 for r in results if r.passed)
    lines = [f"Calibration: {ok}/{len(results)} passed"]
    for r in results:
        st = "OK" if r.passed else "FAIL"
        lines.append(f"[{st}] {r.scenario_name}: {r.actual_decision} safe={r.actual_safe_buy:.2f} max={r.actual_max_buy:.2f}")
        for e in r.errors:
            lines.append(f"  ! {e}")
    return "\n".join(lines)
