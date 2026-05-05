import pytest

from app.bot.handlers.admin import admin_beta_checklist_handler


class _Msg:
    text = "/admin_beta_checklist"
    from_user = type("U", (), {"id": 1, "username": "admin"})()

    def __init__(self):
        self.out: list[str] = []

    async def answer(self, text, **kwargs):
        self.out.append(text)


class _Sess:
    async def scalar(self, *_a, **_k):
        return 5


class _Ctx:
    async def __aenter__(self):
        return _Sess()

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_admin_beta_checklist_requires_admin(monkeypatch):
    async def _deny(_):
        return None

    monkeypatch.setattr("app.bot.handlers.admin._require_admin", _deny)
    msg = _Msg()
    await admin_beta_checklist_handler(msg)
    assert msg.out == []


@pytest.mark.asyncio
async def test_admin_beta_checklist_body(monkeypatch):
    async def _ok(_):
        return type("U", (), {"id": 1, "role": "admin"})()

    async def _owner_snap(*_a, **_k):
        return {
            "expected_owner_tg": 999,
            "owner_found": True,
            "role": "owner",
            "warnings": [],
        }

    async def _activation(*_a, **_k):
        return {"active_users": 3}

    async def _payops(*_a, **_k):
        return {"stale_submitted_48h": 1}

    class _Users:
        def __init__(self, _s):
            pass

        async def count_all(self):
            return 10

    class _Feedback:
        def __init__(self, _s):
            pass

        async def calculate_sla_metrics(self):
            return {"new_feedback_count": 2}

    class _Beta:
        def __init__(self, _s):
            pass

        async def count_active(self):
            return 1

    class _Sig:
        def __init__(self, _s):
            pass

        async def count_linked_bad_good_signals(self, _d):
            return 4, 1, 0

    async def _inv(*_a, **_k):
        return type(
            "I",
            (),
            {
                "valid_active_invites": 2,
                "remaining_redemptions_capacity": 5,
                "expired_still_flagged_active": 0,
                "require_invite_gate": True,
                "blocking_no_valid_invite": False,
            },
        )()

    async def _payrd(*_a, **_k):
        return type(
            "P",
            (),
            {
                "manual_enabled": True,
                "wallet_configured": True,
                "prices_configured": True,
                "admin_ids_configured": True,
                "submitted_total": 1,
                "stale_submitted_count": 0,
            },
        )()

    monkeypatch.setattr("app.bot.handlers.admin.build_beta_invite_readiness", _inv)
    monkeypatch.setattr("app.bot.handlers.admin.build_payment_readiness", _payrd)
    monkeypatch.setattr("app.bot.handlers.admin._require_admin", _ok)
    monkeypatch.setattr("app.bot.handlers.admin.SessionLocal", lambda: _Ctx())
    monkeypatch.setattr("app.bot.handlers.admin._owner_setup_snapshot", _owner_snap)
    monkeypatch.setattr("app.bot.handlers.admin.calculate_activation_metrics", _activation)
    monkeypatch.setattr("app.bot.handlers.admin.calculate_payment_ops_metrics", _payops)
    monkeypatch.setattr("app.bot.handlers.admin.UserRepository", _Users)
    monkeypatch.setattr("app.bot.handlers.admin.FeedbackRepository", _Feedback)
    monkeypatch.setattr("app.bot.handlers.admin.BetaInviteRepository", _Beta)
    monkeypatch.setattr("app.bot.handlers.admin.SignalSnapshotRepository", _Sig)

    msg = _Msg()
    await admin_beta_checklist_handler(msg)
    assert msg.out
    assert "Admin beta checklist" in msg.out[0]
    assert "Users total: 10" in msg.out[0]
    assert "Open incidents: 5" in msg.out[0]
    assert "admin_payments_stale" in msg.out[0]
