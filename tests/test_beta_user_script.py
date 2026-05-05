from app.bot.messages import BETA_USER_SCRIPT_TEXT


def test_beta_user_script_covers_flow():
    assert "/check" in BETA_USER_SCRIPT_TEXT
    assert "/lite_plan" in BETA_USER_SCRIPT_TEXT or "lite_plan" in BETA_USER_SCRIPT_TEXT
    assert "/signal_good" in BETA_USER_SCRIPT_TEXT
    assert "финансовый" in BETA_USER_SCRIPT_TEXT.lower()
