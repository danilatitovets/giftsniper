import pytest

from app.services.billing_providers.manual import ManualBillingProvider


@pytest.mark.asyncio
async def test_manual_provider_checkout_instructions():
    provider = ManualBillingProvider()
    user = type("U", (), {"telegram_id": 555})()
    text = await provider.create_checkout(user, "starter")
    assert "Manual upgrade request" in text


@pytest.mark.asyncio
async def test_manual_provider_webhook_disabled():
    provider = ManualBillingProvider()
    assert await provider.verify_webhook({}, {}) is False
    mapped = await provider.map_event_to_entitlement({})
    assert mapped["action"] == "ignored"
