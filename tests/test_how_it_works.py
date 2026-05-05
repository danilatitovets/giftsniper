from app.bot.messages import HOW_IT_WORKS_TEXT


def test_how_it_works_plain_language():
    assert "рыночн" in HOW_IT_WORKS_TEXT.lower()
    assert "калибровк" in HOW_IT_WORKS_TEXT.lower()
    assert "гарант" not in HOW_IT_WORKS_TEXT.lower() or "нет" in HOW_IT_WORKS_TEXT.lower()
