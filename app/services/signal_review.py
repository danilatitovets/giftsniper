"""Signal review queue and issue taxonomy (Stage 33)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FeedbackItem, SignalSnapshot
from app.db.repositories.feedback import FeedbackRepository


ISSUE_TAXONOMY = (
    "price_too_high",
    "max_buy_too_high",
    "list_price_unrealistic",
    "confidence_too_high",
    "stale_data_issue",
    "no_sales_trait_issue",
    "liquidity_overestimated",
    "rare_trait_overestimated",
    "parser_wrong_collection",
    "parser_wrong_number",
    "source_data_bad",
    "user_misunderstood",
    "good_signal",
)


@dataclass
class SignalReviewItem:
    signal_snapshot: SignalSnapshot
    feedback_count: int
    bad_count: int
    good_count: int
    unclear_count: int
    risk_flags: list[str]
    priority_score: float
    suggested_action: str
    issue_class: str


def classify_signal_issue(
    snapshot: SignalSnapshot,
    *,
    feedback_notes: list[str] | None = None,
    trade_outcome: str | None = None,
) -> str:
    blob = " ".join(feedback_notes or []).lower()
    if any(k in blob for k in ("wrong collection", "wrong coll", "not ice cream", "parser")):
        if "number" in blob or "#" in blob:
            return "parser_wrong_number"
        return "parser_wrong_collection"
    if any(k in blob for k in ("misunderstood", "did not buy", "not a signal")):
        return "user_misunderstood"
    if any(k in blob for k in ("too expensive", "overpriced", "price too high")):
        return "price_too_high"
    if "max buy" in blob or "ceiling" in blob:
        return "max_buy_too_high"
    if "list price" in blob or "unrealistic list" in blob:
        return "list_price_unrealistic"
    if "confidence" in blob and ("too high" in blob or "inflated" in blob):
        return "confidence_too_high"
    if any(k in blob for k in ("stale", "old data", "outdated")):
        return "stale_data_issue"
    if any(k in blob for k in ("no sales", "no trait sales", "zero sales", "illiquid")):
        return "no_sales_trait_issue"
    if "liquidity" in blob:
        return "liquidity_overestimated"
    if "rare" in blob and "trait" in blob:
        return "rare_trait_overestimated"
    if any(k in blob for k in ("bad source", "market data", "api wrong")):
        return "source_data_bad"

    if trade_outcome in {"no_liquidity", "bad_price"}:
        return "liquidity_overestimated" if trade_outcome == "no_liquidity" else "price_too_high"

    flags = snapshot.warning_flags_json or []
    flag_txt = " ".join(str(x).lower() for x in flags) if isinstance(flags, list) else ""
    if snapshot.freshness_label in {"stale", "old"} and snapshot.recommendation in {"BUY_FOR_FLIP", "LIST_HIGHER"}:
        return "stale_data_issue"
    if snapshot.confidence_score and snapshot.confidence_score >= 75 and snapshot.has_trait_sales is False:
        return "no_sales_trait_issue"
    if snapshot.decision_type == "STRONG_BUY" and snapshot.liquidity_score is not None and snapshot.liquidity_score < 40:
        return "liquidity_overestimated"
    if snapshot.important_trait_detected and snapshot.has_trait_sales is False:
        return "rare_trait_overestimated"
    if "no sales" in flag_txt or ("trait" in flag_txt and "sale" in flag_txt):
        return "no_sales_trait_issue"

    return "good_signal"


def _risk_flags_for_snapshot(snap: SignalSnapshot) -> list[str]:
    out: list[str] = []
    if snap.confidence_score and snap.confidence_score >= 80 and not snap.has_trait_sales:
        out.append("high_confidence_no_trait_sales")
    if snap.decision_type == "STRONG_BUY" and snap.liquidity_score is not None and snap.liquidity_score < 45:
        out.append("strong_buy_low_liquidity")
    if snap.important_trait_detected and not snap.has_trait_sales:
        out.append("rare_trait_no_sales")
    if snap.freshness_label in {"stale", "old"} and snap.recommendation in {"BUY_FOR_FLIP", "BUY_ONLY_CHEAP"}:
        out.append("stale_data_buy")
    return out


def calculate_signal_review_priority(
    *,
    bad_count: int,
    good_count: int,
    unclear_count: int,
    confidence: int | None,
    freshness: str | None,
) -> float:
    pri = bad_count * 12.0 + unclear_count * 4.0 - good_count * 2.0
    if confidence:
        pri += min(25.0, confidence / 4.0)
    if freshness in {"old", "stale"}:
        pri += 6.0
    return pri


def _suggested_action(issue: str) -> str:
    return {
        "stale_data_issue": "Review freshness caps / PRICING_STALE_DATA_DISCOUNT",
        "no_sales_trait_issue": "Tighten rare-trait and no-sales gates in analyzer",
        "liquidity_overestimated": "Check liquidity scoring weights",
        "confidence_too_high": "Review confidence calibration dataset",
        "price_too_high": "Compare realized sales vs list/safe buy heuristics",
        "good_signal": "No action — positive pattern",
    }.get(issue, "Manual review snapshot + user thread")


async def build_signal_review_queue(session: AsyncSession, *, limit: int = 25) -> list[SignalReviewItem]:
    r = await session.execute(select(SignalSnapshot).order_by(SignalSnapshot.id.desc()).limit(120))
    snaps = list(r.scalars().all())
    if not snaps:
        return []
    ids = [s.id for s in snaps]
    fb_rows = await FeedbackRepository(session).list_linked_feedback_for_snapshots(ids)
    by_snap: dict[int, list[FeedbackItem]] = defaultdict(list)
    for row in fb_rows:
        if row.signal_snapshot_id:
            by_snap[row.signal_snapshot_id].append(row)

    items: list[SignalReviewItem] = []
    for snap in snaps:
        rows = by_snap.get(snap.id, [])
        bad = sum(1 for x in rows if x.signal_rating == "bad" or (x.type == "signal_bad" and not x.signal_rating))
        good = sum(1 for x in rows if x.signal_rating == "good" or (x.type == "signal_good" and not x.signal_rating))
        unclear = sum(1 for x in rows if x.signal_rating == "unclear" or x.type == "signal_unclear")
        if not rows and snap.confidence_score and snap.confidence_score < 60:
            continue
        notes = [x.message for x in rows if x.message]
        issue = classify_signal_issue(snap, feedback_notes=notes)
        pri = calculate_signal_review_priority(
            bad_count=bad,
            good_count=good,
            unclear_count=unclear,
            confidence=snap.confidence_score,
            freshness=snap.freshness_label,
        )
        if bad == 0 and unclear == 0 and pri < 8:
            continue
        flags = _risk_flags_for_snapshot(snap)
        items.append(
            SignalReviewItem(
                signal_snapshot=snap,
                feedback_count=len(rows),
                bad_count=bad,
                good_count=good,
                unclear_count=unclear,
                risk_flags=flags,
                priority_score=pri,
                suggested_action=_suggested_action(issue),
                issue_class=issue,
            )
        )
    items.sort(key=lambda x: x.priority_score, reverse=True)
    return items[:limit]


def format_signal_review_item(item: SignalReviewItem) -> str:
    s = item.signal_snapshot
    return (
        f"#{s.id} {s.source_command} · {s.collection} #{s.number or '?'} "
        f"· bad/good/unclear {item.bad_count}/{item.good_count}/{item.unclear_count} "
        f"· pri {item.priority_score:.1f}\n"
        f"issue: {item.issue_class} · {item.suggested_action}\n"
        f"flags: {', '.join(item.risk_flags) if item.risk_flags else '—'}"
    )


def format_signal_review_queue(items: list[SignalReviewItem]) -> str:
    if not items:
        return "Signal review queue: пусто."
    lines = ["📋 Signal review queue (top by priority):\n"]
    lines.extend(format_signal_review_item(x) for x in items[:20])
    return "\n\n".join(lines)
