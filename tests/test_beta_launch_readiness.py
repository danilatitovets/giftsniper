import pytest

from app.services.beta_launch_readiness import build_beta_launch_readiness_report, format_beta_launch_readiness_report


class _S:
    pass


def _settings(**kwargs):
    s = _S()
    defaults = dict(
        bot_token="x",
        database_url="postgresql://x",
        production_mode=False,
        admin_telegram_ids="1,2",
        beta_require_invite=False,
        beta_mode=True,
        manual_payment_enabled=False,
        owner_crypto_wallet_ton="UQtest",
        tonapi_api_key="k",
        getgems_api_key="k",
        enable_mock_source=False,
        manual_payment_starter_ton=10.0,
        manual_payment_pro_ton=20.0,
        manual_payment_trader_ton=30.0,
        collection_registry_path="data/collections.json",
        getgems_base_url="",
        tonnel_base_url="",
        tonapi_base_url="https://tonapi.io",
        fragment_base_url="",
        getgems_enabled=True,
        tonnel_enabled=False,
        tonapi_enabled=True,
        fragment_enabled=False,
    )
    for k, v in {**defaults, **kwargs}.items():
        setattr(s, k, v)
    return s


class _Session:
    def __init__(self):
        self._scalar_i = 0

    async def execute(self, *_a, **_k):
        class _R:
            def first(self):
                return ("rev1",)

        return _R()

    async def scalar(self, *_a, **_k):
        self._scalar_i += 1
        return 0


@pytest.mark.asyncio
async def test_missing_bot_token_is_no_go(monkeypatch):
    async def _owner_snap(*_a, **_k):
        return {"owner_found": True, "role": "owner", "warnings": []}

    async def _pay(*_a, **_k):
        return type(
            "P",
            (),
            {
                "manual_enabled": False,
                "wallet_configured": True,
                "prices_configured": True,
                "submitted_total": 0,
                "stale_submitted_count": 0,
            },
        )()

    async def _inv(*_a, **_k):
        return type(
            "I",
            (),
            {
                "valid_active_invites": 1,
                "remaining_redemptions_capacity": 1,
                "expired_still_flagged_active": 0,
                "require_invite_gate": False,
                "blocking_no_valid_invite": False,
            },
        )()

    class _UR:
        def __init__(self, _s):
            pass

        async def count_all(self):
            return 3

    monkeypatch.setattr("app.bot.handlers.admin._owner_setup_snapshot", _owner_snap)
    monkeypatch.setattr("app.services.beta_launch_readiness.build_payment_readiness", _pay)
    monkeypatch.setattr("app.services.beta_launch_readiness.build_beta_invite_readiness", _inv)
    monkeypatch.setattr("app.services.beta_launch_readiness.UserRepository", _UR)
    monkeypatch.setattr(
        "app.services.beta_launch_readiness._migration_heads",
        lambda _s: ("rev1", "rev1", True),
    )
    monkeypatch.setattr(
        "app.services.beta_launch_readiness.build_source_readiness_summary",
        lambda _s: type("X", (), {"warnings": []})(),
    )

    report = await build_beta_launch_readiness_report(_Session(), _settings(bot_token=""))
    assert report.overall_status == "NO_GO"
    assert any(c.key == "bot_token" and c.status == "fail" for c in report.checks)
    assert "Recommended" in format_beta_launch_readiness_report(report)


@pytest.mark.asyncio
async def test_missing_database_url_is_no_go(monkeypatch):
    async def _owner_snap(*_a, **_k):
        return {"owner_found": True, "role": "owner", "warnings": []}

    async def _pay(*_a, **_k):
        return type(
            "P",
            (),
            {
                "manual_enabled": False,
                "wallet_configured": True,
                "prices_configured": True,
                "submitted_total": 0,
                "stale_submitted_count": 0,
            },
        )()

    async def _inv(*_a, **_k):
        return type(
            "I",
            (),
            {
                "valid_active_invites": 1,
                "remaining_redemptions_capacity": 1,
                "expired_still_flagged_active": 0,
                "require_invite_gate": False,
                "blocking_no_valid_invite": False,
            },
        )()

    class _UR:
        def __init__(self, _s):
            pass

        async def count_all(self):
            return 1

    monkeypatch.setattr("app.bot.handlers.admin._owner_setup_snapshot", _owner_snap)
    monkeypatch.setattr("app.services.beta_launch_readiness.build_payment_readiness", _pay)
    monkeypatch.setattr("app.services.beta_launch_readiness.build_beta_invite_readiness", _inv)
    monkeypatch.setattr("app.services.beta_launch_readiness.UserRepository", _UR)
    monkeypatch.setattr(
        "app.services.beta_launch_readiness._migration_heads",
        lambda _s: ("rev1", "rev1", True),
    )
    monkeypatch.setattr(
        "app.services.beta_launch_readiness.build_source_readiness_summary",
        lambda _s: type("X", (), {"warnings": []})(),
    )

    report = await build_beta_launch_readiness_report(_Session(), _settings(database_url=""))
    assert report.overall_status == "NO_GO"


@pytest.mark.asyncio
async def test_beta_require_invite_no_valid_invite_fails(monkeypatch):
    async def _owner_snap(*_a, **_k):
        return {"owner_found": True, "role": "owner", "warnings": []}

    async def _pay(*_a, **_k):
        return type(
            "P",
            (),
            {
                "manual_enabled": False,
                "wallet_configured": True,
                "prices_configured": True,
                "submitted_total": 0,
                "stale_submitted_count": 0,
            },
        )()

    async def _inv(*_a, **_k):
        return type(
            "I",
            (),
            {
                "valid_active_invites": 0,
                "remaining_redemptions_capacity": 0,
                "expired_still_flagged_active": 0,
                "require_invite_gate": True,
                "blocking_no_valid_invite": True,
            },
        )()

    class _UR:
        def __init__(self, _s):
            pass

        async def count_all(self):
            return 1

    monkeypatch.setattr("app.bot.handlers.admin._owner_setup_snapshot", _owner_snap)
    monkeypatch.setattr("app.services.beta_launch_readiness.build_payment_readiness", _pay)
    monkeypatch.setattr("app.services.beta_launch_readiness.build_beta_invite_readiness", _inv)
    monkeypatch.setattr("app.services.beta_launch_readiness.UserRepository", _UR)
    monkeypatch.setattr(
        "app.services.beta_launch_readiness._migration_heads",
        lambda _s: ("rev1", "rev1", True),
    )
    monkeypatch.setattr(
        "app.services.beta_launch_readiness.build_source_readiness_summary",
        lambda _s: type("X", (), {"warnings": []})(),
    )

    report = await build_beta_launch_readiness_report(_Session(), _settings(beta_require_invite=True))
    assert any(c.key == "beta_invites" and c.status == "fail" for c in report.checks)


@pytest.mark.asyncio
async def test_manual_payment_without_wallet_fails(monkeypatch):
    async def _owner_snap(*_a, **_k):
        return {"owner_found": True, "role": "owner", "warnings": []}

    async def _pay(*_a, **_k):
        return type(
            "P",
            (),
            {
                "manual_enabled": True,
                "wallet_configured": False,
                "prices_configured": True,
                "submitted_total": 0,
                "stale_submitted_count": 0,
            },
        )()

    async def _inv(*_a, **_k):
        return type(
            "I",
            (),
            {
                "valid_active_invites": 1,
                "remaining_redemptions_capacity": 1,
                "expired_still_flagged_active": 0,
                "require_invite_gate": False,
                "blocking_no_valid_invite": False,
            },
        )()

    class _UR:
        def __init__(self, _s):
            pass

        async def count_all(self):
            return 1

    monkeypatch.setattr("app.bot.handlers.admin._owner_setup_snapshot", _owner_snap)
    monkeypatch.setattr("app.services.beta_launch_readiness.build_payment_readiness", _pay)
    monkeypatch.setattr("app.services.beta_launch_readiness.build_beta_invite_readiness", _inv)
    monkeypatch.setattr("app.services.beta_launch_readiness.UserRepository", _UR)
    monkeypatch.setattr(
        "app.services.beta_launch_readiness._migration_heads",
        lambda _s: ("rev1", "rev1", True),
    )
    monkeypatch.setattr(
        "app.services.beta_launch_readiness.build_source_readiness_summary",
        lambda _s: type("X", (), {"warnings": []})(),
    )

    report = await build_beta_launch_readiness_report(_Session(), _settings(manual_payment_enabled=True, owner_crypto_wallet_ton=""))
    assert any(c.key == "manual_wallet" and c.status == "fail" for c in report.checks)
