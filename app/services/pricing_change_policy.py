"""Rules for when PRICING_* tweaks are responsible to consider (Stage 33)."""

from __future__ import annotations

from collections import Counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.repositories.signal_snapshots import SignalSnapshotRepository
from app.db.repositories.trade_journal import TradeJournalRepository
from app.services.pricing_tuner import analyze_pricing_accuracy
from app.services.signal_review import build_signal_review_queue


async def evaluate_pricing_change_readiness(session: AsyncSession, settings: Settings) -> dict:
    trade_repo = TradeJournalRepository(session)
    snap_repo = SignalSnapshotRepository(session)
    closed_n = await snap_repo.count_closed_trades()
    closed_recent = await snap_repo.count_closed_trades_since(30)
    good, bad, unclear = await snap_repo.count_linked_bad_good_signals(30)
    reviewed = good + bad + unclear
    linked_trades = await snap_repo.count_trades_linked_to_signals()
    rows = await trade_repo.list_closed_all_users(limit=5000)

    report = analyze_pricing_accuracy(rows, settings=settings)
    queue = await build_signal_review_queue(session, limit=40)
    tax = Counter(item.issue_class for item in queue)
    top_issue, top_n = (tax.most_common(1)[0] if tax else ("none", 0))
    stable_issue = top_n >= 3 and top_issue not in {"good_signal", "none"}

    signals_30d = await snap_repo.count_since(user_id=None, days=30)

    blockers: list[str] = []
    if closed_n < 20:
        blockers.append(f"closed trades {closed_n} < 20")
    if (good + bad) < 10:
        blockers.append(f"good+bad reviewed signals {good + bad} < 10")
    if bad >= 5 and linked_trades < 5:
        blockers.append("bad signals not sufficiently linked to trade outcomes (need more /trade_add <signal_id>)")
    if len(queue) >= 8 and not stable_issue:
        blockers.append("issue taxonomy not stable (no dominant repeated issue)")

    tuning_stable = len(report.findings) > 0 or report.total_closed_trades >= 15
    safe_small = (
        signals_30d >= 50
        and closed_n >= 20
        and stable_issue
        and closed_recent >= 5
        and tuning_stable
    )

    ready = safe_small and len(blockers) == 0

    return {
        "ready": ready,
        "not_ready_reasons": blockers if not ready else [],
        "evidence": {
            "closed_trades": closed_n,
            "closed_trades_30d": closed_recent,
            "reviewed_signal_feedback_30d": reviewed,
            "good_30d": good,
            "bad_30d": bad,
            "trades_linked_to_signals": linked_trades,
            "signals_30d": signals_30d,
            "tuning_findings": len(report.findings),
            "dominant_issue": top_issue,
            "dominant_issue_count": top_n,
        },
        "suggested_safe_changes": report.suggested_env_changes if safe_small else {},
        "risks": [
            "Изменения PRICING_* влияют на все пользователи — менять осторожно малыми шагами.",
            "Не интерпретировать отчёты как гарантию прибыли.",
        ],
    }


def format_pricing_change_policy_report(data: dict) -> str:
    status = "ready (осторожные малые шаги)" if data["ready"] else "not ready"
    lines = [
        "⚖️ Pricing change policy",
        f"Status: {status}",
        f"Evidence: {data['evidence']}",
    ]
    if data["not_ready_reasons"]:
        lines.append("Blockers:\n- " + "\n- ".join(data["not_ready_reasons"]))
    if data.get("suggested_safe_changes"):
        lines.append("Suggested env keys (manual .env only):\n" + "\n".join(f"  - {k}={v}" for k, v in data["suggested_safe_changes"].items()))
    lines.append("Risks:\n- " + "\n- ".join(data["risks"]))
    return "\n".join(lines)
