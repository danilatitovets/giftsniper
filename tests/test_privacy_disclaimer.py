from app.bot.handlers.admin import _flag_set, disclaimer_text, privacy_text


def test_privacy_text_contains_no_wallet_connect_or_keys():
    text = privacy_text().lower()
    assert "не подключает wallet" in text
    assert "не храним: seed phrase, private keys" in text


def test_prod_health_masks_env_secrets():
    assert _flag_set("abc123") == "set"
    assert _flag_set("") == "missing"


def test_disclaimer_text_mentions_risk():
    text = disclaimer_text().lower()
    assert "высокорисковые" in text
