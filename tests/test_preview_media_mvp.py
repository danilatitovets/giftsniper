from __future__ import annotations

import pytest

from app.bot.handlers import passive_gift
from app.i18n import t
from app.services.nft_tonapi_image import extract_nft_preview_media
from app.services.real_market_collection_scan import target_from_nft_payload


def test_extract_media_prefers_animation_url_over_image():
    m = extract_nft_preview_media({"animation_url": "https://x/a.gif", "image": "https://x/i.png"})
    assert m.kind == "animation"
    assert m.url == "https://x/a.gif"


def test_extract_media_prefers_video_over_image():
    m = extract_nft_preview_media({"video": "https://x/a.mp4", "image": "https://x/i.png"})
    assert m.kind == "video"
    assert m.url.endswith(".mp4")


def test_extract_media_detects_gif_as_animation():
    m = extract_nft_preview_media({"metadata": {"animation": "https://x/a.gif"}})
    assert m.kind == "animation"


def test_extract_media_falls_back_to_image():
    m = extract_nft_preview_media({"image": "https://x/i.png"})
    assert m.kind == "photo"


def test_extract_media_reads_content_image():
    m = extract_nft_preview_media({"content": {"image": "https://x/c.png"}})
    assert m.kind == "photo"
    assert m.source_field == "content.image"


def test_extract_media_reads_metadata_image():
    m = extract_nft_preview_media({"metadata": {"image": "https://x/m.png"}})
    assert m.kind == "photo"


def test_extract_media_reads_previews_list_video():
    nft = {
        "previews": [
            {"resolution": "500x500", "url": "https://x/thumb.jpg"},
            {"url": "https://x/clips/prev.mp4", "mime_type": "video/mp4"},
        ]
    }
    m = extract_nft_preview_media(nft)
    assert m.kind == "video"
    assert "previews" in (m.source_field or "")


def test_extract_media_reads_previews_dict_image():
    nft = {"previews": {"main": {"url": "https://x/big.webp", "mime_type": "image/webp"}}}
    m = extract_nft_preview_media(nft)
    assert m.kind == "photo"


def test_extract_media_prefers_metadata_over_small_tonapi_imgproxy_preview():
    """500×500 imgproxy — размыто в шапке; канонический metadata.image лучше."""
    nft = {
        "previews": [{"url": "https://cache.tonapi.io/imgproxy/abc/rs:fill:500:500/plain.webp"}],
        "metadata": {"image": "https://nft.fragment.com/gift/fallback.webp"},
    }
    m = extract_nft_preview_media(nft)
    assert m.kind == "photo"
    assert m.url == "https://nft.fragment.com/gift/fallback.webp"
    assert m.source_field == "metadata.image"


def test_extract_media_prefers_largest_preview_in_list():
    nft = {
        "previews": [
            {"resolution": "100x100", "url": "https://cdn.example/small.png"},
            {"resolution": "1500x1500", "url": "https://cdn.example/large.png"},
        ],
    }
    m = extract_nft_preview_media(nft)
    assert m.url == "https://cdn.example/large.png"


def test_extract_media_prefers_1500_preview_over_metadata_when_both_present():
    nft = {
        "previews": [{"resolution": "1500x1500", "url": "https://cdn.example/huge.png"}],
        "metadata": {"image": "https://nft.fragment.com/gift/m.webp"},
    }
    m = extract_nft_preview_media(nft)
    assert m.url == "https://cdn.example/huge.png"


def test_extract_media_prefers_fragment_metadata_over_tonapi_imgproxy_fill():
    """rs:fill в кэше TonAPI портит пропорции; прямой webp с Fragment лучше."""
    nft = {
        "previews": [
            {
                "resolution": "1500x1500",
                "url": "https://cache.tonapi.io/imgproxy/sig/rs:fill:1500:1500:1/g:no/aHR0cHM6Ly9uZnQuZnJhZ21lbnQuY29tL2dpZnQveC53ZWJw.webp",
            }
        ],
        "metadata": {"image": "https://nft.fragment.com/gift/poolfloat-201154.webp"},
    }
    m = extract_nft_preview_media(nft)
    assert m.url == "https://nft.fragment.com/gift/poolfloat-201154.webp"
    assert m.source_field == "metadata.image"


def test_extract_media_ipfs_url_normalized():
    m = extract_nft_preview_media(
        {"image": "ipfs://bafytest/path/file.png"},
        ipfs_gateway_url="https://ipfs.io/ipfs/",
    )
    assert m.url == "https://ipfs.io/ipfs/bafytest/path/file.png"


def test_extract_media_blocks_localhost():
    m = extract_nft_preview_media({"image": "http://127.0.0.1/evil.png"})
    assert m.kind == "none"
    assert m.url is None


def test_extract_media_none_when_no_media():
    m = extract_nft_preview_media({})
    assert m.kind == "none"
    assert m.url is None


def test_extract_media_video_url_field():
    m = extract_nft_preview_media({"video_url": "https://x/v.webm"})
    assert m.kind == "video"


def test_extract_media_content_metadata_animation_priority():
    m = extract_nft_preview_media(
        {"image": "https://x/i.png", "metadata": {"animation_url": "https://x/a.webm"}}
    )
    assert m.kind == "video"


def test_extract_media_relative_with_base_uri():
    m = extract_nft_preview_media(
        {
            "metadata": {"base_uri": "https://cdn.example/collection/", "image": "image.png"},
        }
    )
    assert m.url == "https://cdn.example/collection/image.png"
    assert m.kind == "photo"


def test_start_text_says_preview_not_photo():
    txt = t("start.main", "ru").lower()
    assert "превью" in txt
    assert "покажу фото nft" not in txt


def test_help_text_says_preview_not_photo():
    txt = t("help.main", "ru").lower()
    assert "превью" in txt
    assert "покажу фото nft" not in txt


@pytest.mark.asyncio
async def test_find_nft_link_help_callback():
    class _M:
        def __init__(self):
            self.out: list[str] = []

        async def answer(self, text: str, **_kwargs):
            self.out.append(text)

    class _Q:
        data = "help:find_nft_link"
        message = _M()

        async def answer(self, *_a, **_k):
            return None

    q = _Q()
    await passive_gift.help_find_nft_link_callback(q)  # type: ignore[arg-type]
    assert q.message.out
    assert "Как найти ссылку на NFT" in q.message.out[0]


def test_tonapi_nft_response_with_content_image_extracts_photo():
    nft = {
        "address": "EQtest",
        "content": {
            "image": "https://nft.cache.ton/content-image.png",
        },
    }
    m = extract_nft_preview_media(nft)
    assert m.kind == "photo"
    assert m.source_field == "content.image"


def test_tonapi_nft_response_with_metadata_animation_extracts_animation():
    nft = {
        "metadata": {
            "name": "Gift #1",
            "animation_url": "https://cdn.example/nft/card.gif",
        },
    }
    m = extract_nft_preview_media(nft)
    assert m.kind == "animation"


def test_target_from_nft_payload_sets_rich_preview_for_video():
    nft = {
        "address": "EQnftaddr_________________________________________0001",
        "collection": {"address": "EQcoll____________________________________________0002"},
        "metadata": {"name": "Chill Flame #1"},
        "video": "https://cdn.example/nft-preview.mp4",
        "image": "https://cdn.example/thumb.png",
    }
    t = target_from_nft_payload(nft, ipfs_gateway_url="https://ipfs.io/ipfs/")
    assert t is not None
    assert t.rich_preview_kind == "video"
    assert t.rich_preview_url and t.rich_preview_url.endswith(".mp4")
    assert t.image_url and "thumb" in t.image_url


def test_getgems_style_metadata_image_extracts_photo():
    nft = {
        "metadata": {
            "name": "Collection #42",
            "image": "ipfs://bafyBEIG/image.png",
        },
    }
    m = extract_nft_preview_media(nft, ipfs_gateway_url="https://ipfs.io/ipfs/")
    assert m.kind == "photo"
    assert m.url and m.url.startswith("https://")
