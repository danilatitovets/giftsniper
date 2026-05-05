"""Signal snapshot packing and formatting (Stage 33)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import SignalSnapshot
from app.db.repositories.signal_snapshots import SignalSnapshotRepository
from app.schemas.analysis import OpportunityScore
from app.schemas.gift import GiftCard
from app.schemas.market_brain import TraitOpportunity
from app.services.important_traits import detect_important_traits


def _freshness_label(stats: dict) -> str:
    if "old" in [stats.get("floor_freshness"), stats.get("sales_freshness")]:
        return "old"
    if "stale" in [
        stats.get("floor_freshness"),
        stats.get("sales_freshness"),
        stats.get("listings_freshness"),
    ]:
        return "stale"
    return "fresh"


def _warning_flags(quality: Any, estimate: Any) -> list[str]:
    out: list[str] = []
    if quality is not None:
        for w in getattr(quality, "warnings", None) or []:
            if w:
                out.append(str(w))
    reasons = getattr(estimate, "reasons", None) or []
    for r in reasons[:12]:
        if r:
            out.append(str(r))
    return out[:24]


def _analysis_dump(estimate: Any) -> dict | list | None:
    if estimate is None:
        return None
    if hasattr(estimate, "model_dump"):
        return estimate.model_dump(mode="json")
    return None


def build_snapshot_seed_from_flip_analysis(
    *,
    source_command: str,
    gift: GiftCard,
    estimate: Any,
    stats: dict,
    quality: Any,
    score: OpportunityScore | None = None,
    input_text: str | None = None,
    nft_address: str | None = None,
    source_url: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    st = settings or get_settings()
    fresh = _freshness_label(stats)
    mts = getattr(estimate, "max_trait_recent_sales", None)
    has_trait = bool(mts is not None and int(mts) > 0)
    rs = int(stats.get("real_sales_count") or 0)
    has_recent = bool(rs > 0 or (stats.get("sales_age_minutes") is not None and int(stats.get("sales_age_minutes") or 999999) <= 7 * 24 * 60))
    imp = bool(detect_important_traits(list(gift.attributes or []), st))
    srcq = None
    if quality is not None and getattr(quality, "sources_used", None):
        srcq = ",".join(str(x) for x in quality.sources_used[:4])
    tier = score.final_rank_label if score else None
    score_val = score.total_score if score else None
    flags = _warning_flags(quality, estimate)
    return {
        "source_command": source_command,
        "collection": gift.collection,
        "number": gift.number,
        "nft_address": nft_address,
        "source_url": source_url,
        "input_text": input_text,
        "decision_type": getattr(estimate, "decision_type", None),
        "recommendation": getattr(estimate, "recommendation", None),
        "tier": tier,
        "score": score_val,
        "safe_buy_price_ton": getattr(estimate, "safe_buy_price_ton", None),
        "max_buy_price_ton": getattr(estimate, "buy_zone_max_ton", None),
        "list_price_ton": getattr(estimate, "list_price_ton", None),
        "quick_sell_price_ton": getattr(estimate, "quick_sell_price_ton", None),
        "stop_loss_price_ton": getattr(estimate, "stop_price_ton", None),
        "expected_profit_ton": getattr(estimate, "expected_profit_ton", None),
        "expected_roi_percent": getattr(estimate, "expected_roi_percent", None),
        "confidence_score": getattr(estimate, "confidence_score", None),
        "risk_score": getattr(estimate, "risk_score", None),
        "liquidity_score": getattr(estimate, "liquidity_score", None),
        "market_regime": stats.get("market_regime"),
        "source_quality": srcq,
        "freshness_label": fresh,
        "has_recent_sales": has_recent,
        "has_trait_sales": has_trait,
        "important_trait_detected": imp,
        "warning_flags_json": flags,
        "analysis_json": _analysis_dump(estimate),
    }


def build_snapshot_seed_from_trait_opportunity(
    o: TraitOpportunity,
    *,
    source_command: str = "rare_deals",
    settings: Settings | None = None,
) -> dict[str, Any]:
    st = settings or get_settings()
    gift = GiftCard(collection=o.collection, number=o.number or 0, attributes=[])
    has_trait_sales = o.trait_recent_sale_median_ton is not None and float(o.trait_recent_sale_median_ton) > 0
    imp = bool(detect_important_traits(list(gift.attributes or []), st))
    return {
        "source_command": source_command,
        "collection": o.collection,
        "number": o.number,
        "nft_address": o.nft_address,
        "source_url": o.source_url,
        "input_text": f"{o.collection} #{o.number or '?'} {o.trait_type}={o.trait_value}",
        "decision_type": None,
        "recommendation": o.recommendation or None,
        "tier": None,
        "score": int(o.opportunity_score) if o.opportunity_score is not None else None,
        "safe_buy_price_ton": None,
        "max_buy_price_ton": None,
        "list_price_ton": None,
        "quick_sell_price_ton": None,
        "stop_loss_price_ton": None,
        "expected_profit_ton": None,
        "expected_roi_percent": None,
        "confidence_score": int(o.confidence_score) if o.confidence_score is not None else None,
        "risk_score": int(o.risk_score) if o.risk_score is not None else None,
        "liquidity_score": int(o.liquidity_score) if o.liquidity_score is not None else None,
        "market_regime": None,
        "source_quality": None,
        "freshness_label": None,
        "has_recent_sales": None,
        "has_trait_sales": has_trait_sales,
        "important_trait_detected": imp,
        "warning_flags_json": list(o.reasons[:20]) if o.reasons else [],
        "analysis_json": o.model_dump(mode="json"),
    }


async def create_signal_snapshot_from_analysis(
    session: AsyncSession,
    *,
    user_id: int,
    seed: dict[str, Any],
) -> SignalSnapshot:
    return await SignalSnapshotRepository(session).create(user_id=user_id, **seed)


async def create_signal_snapshot_from_deal(
    session: AsyncSession,
    *,
    user_id: int,
    seed: dict[str, Any],
) -> SignalSnapshot:
    return await SignalSnapshotRepository(session).create(user_id=user_id, **seed)


async def create_signal_snapshot_from_scan_item(
    session: AsyncSession,
    *,
    user_id: int,
    seed: dict[str, Any],
) -> SignalSnapshot:
    return await SignalSnapshotRepository(session).create(user_id=user_id, **seed)


def format_signal_snapshot_short(snap: SignalSnapshot) -> str:
    return (
        f"#{snap.id} {snap.source_command} · {snap.collection} #{snap.number or '?'} "
        f"· {snap.decision_type or snap.recommendation or 'n/a'}"
    )


def format_signal_snapshot_detail(snap: SignalSnapshot) -> str:
    lines = [
        f"Signal #{snap.id} ({snap.source_command})",
        f"{snap.collection} #{snap.number or '?'}",
        f"decision: {snap.decision_type} · rec: {snap.recommendation}",
        f"safe/max/list: {snap.safe_buy_price_ton} / {snap.max_buy_price_ton} / {snap.list_price_ton}",
        f"confidence/risk/liq: {snap.confidence_score} / {snap.risk_score} / {snap.liquidity_score}",
        f"freshness: {snap.freshness_label} · trait_sales: {snap.has_trait_sales}",
    ]
    if snap.warning_flags_json:
        lines.append("flags: " + "; ".join(str(x) for x in snap.warning_flags_json[:6]))
    return "\n".join(lines)


async def list_recent_signal_snapshots(session: AsyncSession, user_id: int, *, limit: int = 10) -> list[SignalSnapshot]:
    return await SignalSnapshotRepository(session).list_recent_for_user(user_id, limit=limit)


async def find_signal_snapshot_for_feedback(
    session: AsyncSession,
    *,
    user_id: int,
    signal_id: int,
) -> SignalSnapshot | None:
    return await SignalSnapshotRepository(session).get_for_user(signal_id, user_id)


def prediction_dict_from_signal_snapshot(snap: SignalSnapshot) -> dict[str, Any]:
    if snap.analysis_json and isinstance(snap.analysis_json, dict):
        d = snap.analysis_json
        return {
            "decision_type": d.get("decision_type") or snap.decision_type,
            "safe_buy_price_ton": d.get("safe_buy_price_ton") or snap.safe_buy_price_ton,
            "max_buy_price_ton": d.get("buy_zone_max_ton") or snap.max_buy_price_ton,
            "normal_list_price_ton": d.get("normal_list_price_ton") or d.get("list_price_ton") or snap.list_price_ton,
            "expected_roi_percent": d.get("expected_roi_percent") or snap.expected_roi_percent,
            "confidence_score": d.get("confidence_score") or snap.confidence_score,
            "precision_plan_json": d.get("precision_plan_json"),
        }
    return {
        "decision_type": snap.decision_type,
        "safe_buy_price_ton": snap.safe_buy_price_ton,
        "max_buy_price_ton": snap.max_buy_price_ton,
        "normal_list_price_ton": snap.list_price_ton,
        "expected_roi_percent": snap.expected_roi_percent,
        "confidence_score": snap.confidence_score,
    }


def signal_feedback_footer(snapshot_id: int) -> str:
    return (
        f"\n\n🧾 ID сигнала: #{snapshot_id}\n"
        f"Оценка сигнала:\n"
        f"· /signal_good {snapshot_id} — согласен\n"
        f"· /signal_bad {snapshot_id} — не согласен\n"
        f"· /signal_unclear {snapshot_id} — неясно"
    )


def parse_signal_command_body(text: str, command_prefix: str) -> tuple[int | None, str | None, str | None]:
    """Returns (snapshot_id, note, legacy_message). If snapshot_id is None and legacy_message set, free-text legacy."""
    raw = (text or "").strip()
    if not raw.startswith(command_prefix):
        return None, None, raw
    rest = raw.removeprefix(command_prefix).strip()
    if not rest:
        return None, None, None
    note: str | None = None
    main = rest
    if "|" in rest:
        main, note_part = rest.split("|", 1)
        main = main.strip()
        note = note_part.strip() or None
    first = main.split()[0] if main else ""
    if first.isdigit():
        return int(first), note, None
    return None, note, main or rest

