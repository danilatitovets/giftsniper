from app.services.nft_tonapi_image import extract_nft_image_url, extract_nft_media_urls


def test_extract_nft_media_urls_top_level_image():
    nft = {"image": "https://tonapi.example/nft.png"}
    primary, secondary = extract_nft_media_urls(nft)
    assert primary == "https://tonapi.example/nft.png"
    assert secondary is None


def test_extract_nft_image_url_prefers_1500_preview():
    nft = {
        "previews": [
            {"resolution": "100x100", "url": "https://cdn.example/p100.png"},
            {"resolution": "500x500", "url": "https://cdn.example/p500.png"},
            {"resolution": "1500x1500", "url": "https://cdn.example/p1500.png"},
        ]
    }
    assert extract_nft_image_url(nft) == "https://cdn.example/p1500.png"


def test_extract_nft_image_url_fallback_to_500():
    nft = {
        "previews": [
            {"resolution": "100x100", "url": "https://cdn.example/p100.png"},
            {"resolution": "500x500", "url": "https://cdn.example/p500.png"},
        ]
    }
    assert extract_nft_image_url(nft) == "https://cdn.example/p500.png"


def test_extract_nft_image_url_metadata_image():
    nft = {"metadata": {"image": "https://meta.example/nft.png"}}
    assert extract_nft_image_url(nft) == "https://meta.example/nft.png"


def test_extract_nft_image_url_ipfs():
    nft = {"metadata": {"image": "ipfs://bafyCID/path/file.png"}}
    out = extract_nft_image_url(nft, ipfs_gateway_url="https://ipfs.io/ipfs/")
    assert out == "https://ipfs.io/ipfs/bafyCID/path/file.png"
