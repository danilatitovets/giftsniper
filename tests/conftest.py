"""Shared pytest hooks (optional autouse stubs)."""

from __future__ import annotations

import os

# Developer `.env` may set PRODUCTION_MODE for the real bot; pytest must not inherit strict production mock locks.
os.environ["PRODUCTION_MODE"] = "false"
os.environ.setdefault("PUBLIC_BOT_ACCESS", "false")

from unittest.mock import AsyncMock

import pytest

try:
    from app.config import get_settings

    get_settings.cache_clear()
except Exception:
    pass


@pytest.fixture(autouse=True)
def _nft_daily_limits_stub(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Избегаем реального SELECT user_nft_check_day в тестах без миграции 0031."""
    if any(
        x in request.node.nodeid
        for x in (
            "test_limits_show_upgrade",
            "test_plan_mvp_limits",
            "test_referrals_mvp",
            "test_daily_nft_check_limit_still_blocks_free_user",
        )
    ):
        return
    from app.services import nft_check_limits

    monkeypatch.setattr(nft_check_limits, "assert_nft_daily_check_allowed", AsyncMock(return_value=True))
    monkeypatch.setattr(nft_check_limits, "record_successful_nft_check", AsyncMock(return_value=None))
