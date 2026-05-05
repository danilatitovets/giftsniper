import pytest

from app.services.gift_intake import is_probable_ton_address


def test_raw_workchain_ok():
    ok, w = is_probable_ton_address("0:" + "a" * 64)
    assert ok and not w


def test_suspicious_friendly_warns():
    ok, w = is_probable_ton_address("EQ" + "x" * 69)
    assert ok
    assert w
