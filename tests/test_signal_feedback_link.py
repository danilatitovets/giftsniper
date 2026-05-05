from app.services.signal_snapshots import parse_signal_command_body


def test_parse_signal_id_with_note():
    sid, note, legacy = parse_signal_command_body("/signal_good 42 | great", "/signal_good")
    assert sid == 42
    assert note == "great"
    assert legacy is None


def test_parse_legacy_text():
    sid, note, legacy = parse_signal_command_body("/signal_good was helpful", "/signal_good")
    assert sid is None
    assert legacy == "was helpful"


def test_parse_signal_bad_id_only():
    sid, note, legacy = parse_signal_command_body("/signal_bad 7", "/signal_bad")
    assert sid == 7
    assert note is None
