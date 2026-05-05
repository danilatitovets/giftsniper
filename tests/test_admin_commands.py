from app.bot.handlers.admin import _flag_set, _is_admin, _parse_pipe, disclaimer_text, privacy_text


def test_admin_set_plan_parser():
    parts = _parse_pipe("/admin_set_plan 123456 | pro | 30", "/admin_set_plan")
    assert parts == ["123456", "pro", "30"]


def test_non_secret_env_flag():
    assert _flag_set("secret-value") == "set"
    assert _flag_set("") == "missing"


def test_privacy_text_no_sensitive_storage():
    text = privacy_text().lower()
    assert "seed phrase" in text
    assert "private keys" in text


def test_disclaimer_present():
    text = disclaimer_text().lower()
    assert "не является финансовым советником" in text


def test_non_admin_check(monkeypatch):
    settings = type("S", (), {"admin_telegram_ids": ""})()
    monkeypatch.setattr("app.bot.handlers.admin.get_settings", lambda: settings)
    user = type("U", (), {"role": "user"})()
    assert _is_admin(user, 100500) is False
