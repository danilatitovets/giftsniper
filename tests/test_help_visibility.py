from app.bot.messages import build_commands_text


def test_commands_text_hides_admin_for_regular_user():
    text = build_commands_text(is_admin=False)
    assert "/admin_stats" not in text
    assert "/help" in text


def test_commands_text_shows_admin_for_admin():
    text = build_commands_text(is_admin=True)
    assert "/admin_stats" in text
