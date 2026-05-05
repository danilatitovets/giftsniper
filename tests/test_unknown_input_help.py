from app.services.gift_cards import format_unknown_gift_input_help


def test_unknown_help_has_examples():
    t = format_unknown_gift_input_help("foo", ["warn"], context="check")
    assert "/check" in t
    assert "/feedback" in t
    assert "Ice Cream" in t
