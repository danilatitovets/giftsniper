"""Weekly owner accuracy digest content (Stage 33)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.repositories.signal_snapshots import SignalSnapshotRepository
from app.db.repositories.trade_journal import TradeJournalRepository
from app.services.beta_dataset_workflow import build_beta_dataset_summary
from app.services.pricing_tuner import analyze_pricing_accuracy
from app.services.signal_accuracy_dashboard import build_admin_signal_accuracy_report
from app.services.signal_review import build_signal_review_queue


async def build_owner_accuracy_digest_text(session: AsyncSession, settings: Settings) -> str:
    snap_repo = SignalSnapshotRepository(session)
    trade_repo = TradeJournalRepository(session)
    good, bad, unclear = await snap_repo.count_linked_bad_good_signals(7)
    denom = max(good + bad + unclear, 1)
    closed_rows = await trade_repo.list_closed_all_users(limit=3000)
    tuning = analyze_pricing_accuracy(closed_rows, settings=settings)
    q = await build_signal_review_queue(session, limit=15)
    ds = await build_beta_dataset_summary(session)
    acc_snip = await build_admin_signal_accuracy_report(session, days=7)

    lines = [
        "📈 Owner accuracy digest (7d)",
        f"Signal feedback (linked): good={good}, bad={bad}, unclear={unclear} (bad share ~{bad/denom:.0%})",
        f"Closed trades (sample for tuning): {tuning.total_closed_trades}",
        f"Tuning findings: {len(tuning.findings)} (heuristic, not financial advice)",
        f"Unresolved queue (priority items): {len(q)}",
        f"Dataset: snapshots={ds.get('signal_snapshots_total',0)}, reviewed={ds.get('snapshots_with_review_rating',0)}",
        "",
        "Top bad patterns (queue):",
    ]
    for item in q[:4]:
        if item.bad_count or item.risk_flags:
            lines.append(f"  - #{item.signal_snapshot.id}: {', '.join(item.risk_flags) or item.issue_class}")
    lines.append("")
    lines.append("Snapshot report (trimmed):\n" + acc_snip[:2800])
    lines.append("")
    lines.append("Recommended next actions:")
    lines.append("- Просмотреть /admin_signal_queue и связать сделки с сигналами.")
    lines.append("- Экспорт датасета: /admin_export_reviewed_signals")
    lines.append("- Перед правками PRICING_*: /admin_pricing_change_policy")
    lines.append("")
    lines.append("Напоминание: отчёты не гарантируют прибыль; бот не меняет .env автоматически.")
    return "\n".join(lines)
