import pytest

from app.services.gift_intake import (
    GiftInputType,
    parse_collection_number,
    parse_gift_input,
    parse_marketplace_url,
    parse_nft_address,
    parse_telegram_gift_url,
)


def test_parse_ice_cream_space_number():
    gi = parse_gift_input("Ice Cream 217467")
    assert gi.input_type == GiftInputType.collection_number
    assert gi.collection == "Ice Cream"
    assert gi.number == 217467


def test_parse_hash_and_mixed_case():
    gi = parse_gift_input("ice cream #217467")
    assert gi.collection == "Ice Cream"
    assert gi.number == 217467


def test_parse_slash_and_no():
    gi = parse_gift_input("Ice Cream / 217467")
    assert gi.number == 217467
    gi2 = parse_gift_input("Ice Cream №217467")
    assert gi2.number == 217467


def test_parse_nft_addresses():
    eq = "EQD__________________________________________0vo"
    assert parse_nft_address(eq) == eq
    raw = "0:" + "a" * 64
    assert parse_nft_address(raw) == raw


def test_parse_unknown_url_safe():
    gi = parse_marketplace_url("https://unknown-market.example/foo/bar")
    assert gi.input_type == GiftInputType.unknown


def test_parse_getgems_does_not_crash():
    gi = parse_marketplace_url("https://getgems.io/collection/EQColAddr/217467")
    assert gi.input_type == GiftInputType.marketplace_url
    assert gi.number == 217467


def test_parse_telegram_nft_path():
    gi = parse_telegram_gift_url("https://t.me/nft/EQTest__________________________________________0ab")
    assert gi.input_type == GiftInputType.telegram_gift_url


def test_parse_getgems_telegram_startapp_extracts_collection_and_nft():
    url = (
        "https://t.me/GetgemsNftBot/gems?startapp="
        "L2NvbGxlY3Rpb24vRVFBMEV6UllYNXdtX3E0Nl9OWDhiN0VZaHRPa1hmWGdzcjA2RVRib3YxYTdTdFpsL0VRZl90"
        "Z19naWZ0X19fX19fX19fX19fX19fX19fX184cXRGNGZBQUJ3d0wtZQ"
    )
    gi = parse_gift_input(url)
    assert gi.input_type == GiftInputType.getgems_startapp
    assert gi.collection_address == "EQA0EzRYX5wm_q46_NX8b7EYhtOkXfXgsr06ETbov1a7StZl"
    assert gi.nft_address == "EQf_tg_gift____________________8qtF4fAABwwL-e"
    assert gi.source_hint == "getgems_startapp_collection_nft"
    assert gi.startapp_decoded_path
    assert gi.startapp_decoded_path.startswith("/collection/")


def test_collection_only_startapp_friendly_error():
    url = (
        "https://t.me/GetgemsNftBot/gems?startapp="
        "L2NvbGxlY3Rpb24vRVFBMEV6UllYNXdtX3E0Nl9OWDhiN0VZaHRPa1hmWGdzcjA2RVRib3YxYTdTdFps"
    )
    gi = parse_gift_input(url)
    assert gi.input_type == GiftInputType.getgems_startapp
    assert gi.collection_address == "EQA0EzRYX5wm_q46_NX8b7EYhtOkXfXgsr06ETbov1a7StZl"
    assert gi.nft_address is None
    assert gi.source_hint == "getgems_startapp_collection_only"


def test_gift_friendly_address_with_underscores_is_valid():
    addr = "EQf_tg_gift____________________8qtF4fAABwwL-e"
    assert parse_nft_address(addr) == addr


def test_parse_collection_number_helper():
    assert parse_collection_number("X #1") == ("X", 1)


def test_unknown_plain_text():
    gi = parse_gift_input("hello world")
    assert gi.input_type == GiftInputType.unknown
