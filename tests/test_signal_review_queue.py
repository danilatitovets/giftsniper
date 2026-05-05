from app.services.signal_review import calculate_signal_review_priority


def test_review_priority_prefers_bad_and_high_confidence():
    low = calculate_signal_review_priority(bad_count=0, good_count=2, unclear_count=0, confidence=40, freshness="fresh")
    high = calculate_signal_review_priority(bad_count=2, good_count=0, unclear_count=0, confidence=90, freshness="old")
    assert high > low
