from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.repositories.feedback import FeedbackRepository


def _since(period_days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=period_days)


async def summarize_signal_feedback(session, period_days: int = 7) -> dict:
    since = _since(period_days)
    rows = await FeedbackRepository(session).list_signal_feedback(limit=200)
    rows = [r for r in rows if (r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=timezone.utc)) >= since]
    good = [r for r in rows if r.type == "signal_good"]
    bad = [r for r in rows if r.type == "signal_bad"]
    latest_bad_reasons = [x.message[:120] for x in bad[:5]]
    latest_good_examples = [x.message[:120] for x in good[:5]]
    return {
        "period_days": period_days,
        "signal_good_count": len(good),
        "signal_bad_count": len(bad),
        "latest_bad_reasons": latest_bad_reasons,
        "latest_good_examples": latest_good_examples,
    }


async def calculate_signal_good_bad_ratio(session, period_days: int = 7) -> float:
    summary = await summarize_signal_feedback(session, period_days=period_days)
    bad = int(summary["signal_bad_count"])
    good = int(summary["signal_good_count"])
    return float(good / bad) if bad else float(good)


def format_signal_quality_report(summary: dict, ratio: float) -> str:
    good = int(summary["signal_good_count"])
    bad = int(summary["signal_bad_count"])
    if bad > good:
        recommendation = "Recommendation: review scan thresholds."
    elif good + bad < 5:
        recommendation = "Recommendation: ask beta users for /signal_good or /signal_bad."
    else:
        recommendation = "Recommendation: keep monitoring and review top bad cases."
    bad_text = "\n".join(f"- {x}" for x in summary.get("latest_bad_reasons", [])) or "- n/a"
    good_text = "\n".join(f"- {x}" for x in summary.get("latest_good_examples", [])) or "- n/a"
    return (
        f"📡 Signal Quality — {summary.get('period_days', 7)}d\n"
        f"signal_good: {good}\n"
        f"signal_bad: {bad}\n"
        f"good/bad ratio: {ratio:.2f}\n\n"
        f"Latest bad reasons:\n{bad_text}\n\n"
        f"Latest good examples:\n{good_text}\n\n"
        f"{recommendation}"
    )
