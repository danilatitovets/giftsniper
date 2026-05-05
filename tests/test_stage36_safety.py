from app.bot.messages import BETA_SMOKE_PLAN_TEXT, BETA_USER_SCRIPT_TEXT


def test_stage36_copy_no_seed_wallet_autobuy():
    blob = (BETA_SMOKE_PLAN_TEXT + BETA_USER_SCRIPT_TEXT).lower()
    assert "wallet connect" not in blob
    assert "автопокуп" not in blob and "autobuy" not in blob
    assert "не просит" in blob or "не подключает" in blob
    assert "не гарантирует прибыль" in blob or "не финансовый совет" in blob
