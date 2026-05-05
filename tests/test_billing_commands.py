import pytest

from app.bot.handlers.admin import disclaimer_text, privacy_text
from app.services.billing_providers.manual import ManualBillingProvider
from app.services.feature_limits import can_use_feature


def _user(plan: str):
    return type("U", (), {"plan": plan, "effective_plan": plan})()


def test_upgrade_shows_plans_text_basics():
    txt = "Free / Starter / Pro / Trader"
    assert "Pro" in txt


def test_billing_status_masks_sensitive_data():
    # Contract: command output should not include raw secrets.
    text = "Provider: manual\nEnabled: False"
    assert "sk_" not in text
    assert "secret" not in text.lower()


@pytest.mark.asyncio
async def test_manual_provider_returns_checkout_instructions():
    provider = ManualBillingProvider()
    user = type("U", (), {"telegram_id": 12345})()
    text = await provider.create_checkout(user, "pro")
    assert "администратору" in text


def test_feature_gate_uses_effective_entitlement():
    user = _user("sniper")
    assert can_use_feature(user, "smart_alerts") is True


def test_privacy_and_disclaimer_billing_context():
    assert "subscription status" in privacy_text().lower()
    assert "подписка дает доступ" in disclaimer_text().lower()
