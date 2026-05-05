import pytest

import app.services.pricing_change_policy as pcp
from app.config import get_settings
from app.db.session import SessionLocal
from app.services.pricing_change_policy import format_pricing_change_policy_report


@pytest.mark.asyncio
async def test_pricing_policy_not_ready_with_low_sample(monkeypatch):
    settings = get_settings()

    async def _closed(_self):
        return 3

    async def _linked(_self, _days):
        return (1, 1, 0)

    async def _tr_linked(_self):
        return 0

    async def _since(_self, **_kw):
        return 10

    async def _closed_recent(_self, _days):
        return 1

    async def _no_trades(_self, limit=5000):
        return []

    async def _empty_queue(_session, **_kw):
        return []

    monkeypatch.setattr(pcp.SignalSnapshotRepository, "count_closed_trades", _closed)
    monkeypatch.setattr(pcp.SignalSnapshotRepository, "count_linked_bad_good_signals", _linked)
    monkeypatch.setattr(pcp.SignalSnapshotRepository, "count_trades_linked_to_signals", _tr_linked)
    monkeypatch.setattr(pcp.SignalSnapshotRepository, "count_since", _since)
    monkeypatch.setattr(pcp.SignalSnapshotRepository, "count_closed_trades_since", _closed_recent)
    monkeypatch.setattr(pcp.TradeJournalRepository, "list_closed_all_users", _no_trades)
    monkeypatch.setattr(pcp, "build_signal_review_queue", _empty_queue)

    async with SessionLocal() as session:
        data = await pcp.evaluate_pricing_change_readiness(session, settings)
    assert data["ready"] is False
    assert data["not_ready_reasons"]
    txt = format_pricing_change_policy_report(data)
    assert "not ready" in txt.lower()


def test_pricing_policy_format_when_marked_ready():
    data = {
        "ready": True,
        "not_ready_reasons": [],
        "evidence": {"closed_trades": 50},
        "suggested_safe_changes": {"PRICING_TARGET_ROI_NORMAL": "19"},
        "risks": ["Изменения влияют на всех пользователей"],
    }
    txt = format_pricing_change_policy_report(data)
    assert "ready" in txt.lower()
    assert "PRICING_TARGET_ROI_NORMAL" in txt
