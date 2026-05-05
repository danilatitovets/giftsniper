from app.bot.messages import build_commands_text


def test_commands_categories_for_user():
    text = build_commands_text(is_admin=False)
    assert "/check" in text
    assert "/lite_plan" in text
    assert "/flip_plan" in text
    assert "/admin_beta_checklist" not in text


def test_commands_includes_admin_for_admin():
    text = build_commands_text(is_admin=True)
    assert "/admin_beta_checklist" in text
