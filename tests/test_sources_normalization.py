from app.sources.normalization import (
    build_search_variants,
    normalize_collection_name,
    normalize_trait_type,
    normalize_trait_value,
)


def test_normalize_collection_name():
    assert normalize_collection_name("ice cream") == "Ice Cream"
    assert normalize_collection_name("IceCream") == "Ice Cream"


def test_normalize_trait_names():
    assert normalize_trait_type("symbol") == "Symbol"
    assert normalize_trait_type("BACKDROP") == "Backdrop"
    assert normalize_trait_value("ivory   white") == "Ivory White"


def test_build_search_variants():
    variants = build_search_variants("Ice Cream")
    assert "ice cream" in variants
    assert "IceCream" in variants or "icecream" in variants
