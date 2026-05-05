import time

import pytest

from app.services import runtime_state


def test_pending_put_get():
    runtime_state.pending_gift_inputs.clear()
    sid = runtime_state.pending_gift_put(42, "https://getgems.io/x", ttl_seconds=60)
    assert runtime_state.pending_gift_get(42, sid) == "https://getgems.io/x"


def test_pending_expires():
    runtime_state.pending_gift_inputs.clear()
    sid = runtime_state.pending_gift_put(7, "raw", ttl_seconds=0.01)
    time.sleep(0.05)
    assert runtime_state.pending_gift_get(7, sid) is None


def test_pending_cancel():
    runtime_state.pending_gift_inputs.clear()
    sid = runtime_state.pending_gift_put(3, "a", ttl_seconds=60)
    runtime_state.pending_gift_cancel(3, sid)
    assert runtime_state.pending_gift_get(3, sid) is None
