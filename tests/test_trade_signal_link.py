"""Trade journal links to signal_snapshot_id via handler logic (model support)."""

from app.db.models import TradeJournal


def test_trade_journal_has_signal_snapshot_fk_column():
    t = TradeJournal(user_id=1, collection="X", number=1, signal_snapshot_id=99)
    assert t.signal_snapshot_id == 99
