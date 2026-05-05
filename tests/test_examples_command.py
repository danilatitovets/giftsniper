from app.bot.messages import EXAMPLES_TEXT


def test_examples_includes_check_deal_flip_lite():
    assert "/check Ice Cream #217467" in EXAMPLES_TEXT
    assert "/deal Ice Cream #217467 | 180" in EXAMPLES_TEXT
    assert "/flip_plan 300" in EXAMPLES_TEXT
    assert "/lite_plan 300" in EXAMPLES_TEXT or "/lite_plan" in EXAMPLES_TEXT
