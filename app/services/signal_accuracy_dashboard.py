"""Owner-facing signal accuracy aggregates (Stage 33)."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FeedbackItem, SignalSnapshot
from app.services.signal_review import ISSUE_TAXONOMY, build_signal_review_queue, classify_signal_issue


def _confidence_bucket(c: int | None) -> str:
    if c is None:
        return "unknown"
    if c < 50:
        return "0-49"
    if c < 70:
        return "50-69"
    if c < 85:
        return "70-84"
    return "85-100"


async def build_admin_signal_accuracy_report(session: AsyncSession, *, days: int = 7) -> str:
    since = datetime.utcnow() - timedelta(days=days)
    since30 = datetime.utcnow() - timedelta(days=30)

    n7 = int(
        await session.scalar(select(func.count(SignalSnapshot.id)).where(SignalSnapshot.created_at >= since)) or 0
    )
    n30 = int(
        await session.scalar(select(func.count(SignalSnapshot.id)).where(SignalSnapshot.created_at >= since30)) or 0
    )

    fb_stmt = select(FeedbackItem).where(
        FeedbackItem.signal_snapshot_id.is_not(None),
        FeedbackItem.created_at >= since,
    )
    fb_rows = list((await session.scalars(fb_stmt)).all())
    good = sum(1 for x in fb_rows if x.signal_rating == "good" or (x.type == "signal_good" and not x.signal_rating))
    bad = sum(1 for x in fb_rows if x.signal_rating == "bad" or (x.type == "signal_bad" and not x.signal_rating))
    unclear = sum(1 for x in fb_rows if x.signal_rating == "unclear" or x.type == "signal_unclear")
    denom = max(good + bad + unclear, 1)
    lines = [
        "📊 Signal accuracy dashboard\n",
        f"Signals created: 7d={n7}, 30d={n30}",
        f"Linked feedback 7d: good={good}, bad={bad}, unclear={unclear}",
        f"Rough ratios: good {good/denom:.0%}, bad {bad/denom:.0%}, unclear {unclear/denom:.0%}",
        "",
    ]

    snap_ids = [x.signal_snapshot_id for x in fb_rows if x.signal_snapshot_id and (x.signal_rating == "bad" or x.type == "signal_bad")]
    snap_ids = list({i for i in snap_ids if i})
    snaps: list[SignalSnapshot] = []
    if snap_ids:
        snaps = list(
            (await session.scalars(select(SignalSnapshot).where(SignalSnapshot.id.in_(snap_ids)))).all()
        )
        by_cmd: dict[str, list[SignalSnapshot]] = defaultdict(list)
        by_dec: dict[str | None, list[SignalSnapshot]] = defaultdict(list)
        by_coll: dict[str, list[SignalSnapshot]] = defaultdict(list)
        by_conf: dict[str, list[SignalSnapshot]] = defaultdict(list)
        for s in snaps:
            by_cmd[s.source_command].append(s)
            by_dec[s.decision_type].append(s)
            by_coll[s.collection].append(s)
            by_conf[_confidence_bucket(s.confidence_score)].append(s)
        lines.append("Bad-linked signals by command:")
        for k, v in sorted(by_cmd.items(), key=lambda kv: len(kv[1]), reverse=True):
            lines.append(f"  - {k}: {len(v)}")
        lines.append("\nBad-linked by decision_type:")
        for k, v in sorted(by_dec.items(), key=lambda kv: len(kv[1]), reverse=True)[:8]:
            lines.append(f"  - {k}: {len(v)}")
        lines.append("\nBad-linked by confidence bucket:")
        for k, v in sorted(by_conf.items(), key=lambda kv: len(kv[1]), reverse=True):
            lines.append(f"  - {k}: {len(v)}")
        lines.append("\nBad-linked top collections:")
        for k, v in sorted(by_coll.items(), key=lambda kv: len(kv[1]), reverse=True)[:6]:
            lines.append(f"  - {k}: {len(v)}")

    tax_counter: Counter[str] = Counter()
    for s in snaps:
        tax_counter[classify_signal_issue(s, feedback_notes=[])] += 1
    if tax_counter:
        lines.append("\nIssue taxonomy (from bad-linked snapshots, heuristic):")
        for issue, c in tax_counter.most_common(8):
            lines.append(f"  - {issue}: {c}")

    q = await build_signal_review_queue(session, limit=12)
    lines.append("\nRisky patterns (queue preview):")
    for item in q[:5]:
        if item.risk_flags:
            lines.append(f"  - #{item.signal_snapshot.id}: {', '.join(item.risk_flags)}")

    lines.append("\nRecommendations:")
    lines.append("- Собирайте больше /signal_good и /signal_bad с Signal ID для калибровки.")
    lines.append("- Связывайте сделки: /trade_add <signal_id> | цена — для проверки прогноза.")
    lines.append("- Меняйте PRICING_* только после /admin_pricing_change_policy (не автоматически).")
    return "\n".join(lines)


def taxonomy_classes() -> tuple[str, ...]:
    return ISSUE_TAXONOMY
