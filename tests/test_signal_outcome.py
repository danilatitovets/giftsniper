from app.bot.handlers.admin import _parse_pipe


def test_signal_outcome_parse():
    parts = _parse_pipe("/signal_outcome 5 | bought | note here", "/signal_outcome")
    assert parts[0] == "5"
    assert parts[1] == "bought"
    assert parts[2] == "note here"
