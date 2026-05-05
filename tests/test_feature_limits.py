import pytest

from app.config import Settings
from app.services.feature_limits import assert_feature_allowed, can_use_feature, check_usage_limit, get_plan_limits


def _settings(**kw: object) -> Settings:
    base: dict[str, object] = {
        "BOT_TOKEN": "t",
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "plan_free_daily_nft_checks": 3,
        "plan_free_watchlist_limit": 3,
        "plan_pro_daily_nft_checks": 100,
        "plan_pro_watchlist_limit": 50,
        "plan_sniper_daily_nft_checks": 1000,
        "plan_sniper_watchlist_limit": 300,
    }
    base.update(kw)
    return Settings(**base)


def _user(plan: str):
    return type("U", (), {"plan": plan})()


def test_free_max_gifts_enforced():
    s = _settings()
    user = _user("free")
    ok, limit = check_usage_limit(user, "max_gifts", current_count=3, settings=s)
    assert ok is False
    assert limit == 3


def test_free_cannot_use_smart_alerts():
    user = _user("free")
    assert can_use_feature(user, "smart_alerts") is False
    with pytest.raises(PermissionError):
        assert_feature_allowed(user, "smart_alerts")


def test_sniper_can_use_smart_alerts():
    user = _user("sniper")
    assert can_use_feature(user, "smart_alerts") is True


def test_trader_higher_limits():
    s = _settings()
    assert get_plan_limits("trader", settings=s)["max_gifts"] > get_plan_limits("pro", settings=s)["max_gifts"]


def test_plan_limits_free_pro_sniper_match_production_contract():
    s = _settings()
    free = get_plan_limits("free", settings=s)
    pro = get_plan_limits("pro", settings=s)
    sniper = get_plan_limits("sniper", settings=s)
    assert free["checks_per_day"] == 3
    assert free["max_gifts"] == 3
    assert pro["checks_per_day"] == 100
    assert pro["max_gifts"] == 50
    assert sniper["checks_per_day"] == 1000
    assert sniper["max_gifts"] == 300
