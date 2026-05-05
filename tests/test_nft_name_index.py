from app.services.nft_name_index import (
    extract_base_name_from_nft_name,
    extract_item_number_from_name,
    normalize_nft_text,
    parse_collection_number_payload,
)


def test_parse_bunny_muffin():
    p = parse_collection_number_payload("Bunny Muffin #974")
    assert p == ("Bunny Muffin", 974)


def test_parse_spaced_number():
    assert parse_collection_number_payload("Whip Cupcake #57 234") == ("Whip Cupcake", 57234)
    assert parse_collection_number_payload("Whip Cupcake #57,234") == ("Whip Cupcake", 57234)


def test_parse_unicode_safe():
    assert normalize_nft_text("  Café_Gift  ") == "café gift"
    assert extract_item_number_from_name("Ice Cream №217467") == 217467
    assert extract_base_name_from_nft_name("Trapped Heart #22976") == "Trapped Heart"


def test_extract_item_number_from_name():
    assert extract_item_number_from_name("Heroic Helmet #2760") == 2760
