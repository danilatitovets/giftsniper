from app.bot.handlers.admin import privacy_text


def test_upgrade_shows_manual_crypto_payment_instructions():
    text = "Для оплаты криптой используй /pay pro или /pay trader"
    assert "/pay pro" in text
    assert "ручного подтверждения" in "Доступ выдается после ручного подтверждения."


def test_billing_status_contains_manual_sections():
    text = "Recent manual payment requests:\n- #1 pro 25 TON (pending)"
    assert "manual payment requests" in text


def test_privacy_mentions_no_private_keys():
    text = privacy_text().lower()
    assert "не храним: seed phrase, private keys" in text
