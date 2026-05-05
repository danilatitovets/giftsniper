"""CLI: безопасно показать, какое медиа выберет extract_nft_preview_media для NFT address (TonAPI)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.config import get_settings
from app.services.nft_tonapi_image import extract_nft_preview_media, safe_media_url_for_log
from app.services.tonapi_collection_client import TonAPICollectionClient


async def _run(address: str) -> dict:
    settings = get_settings()
    client = TonAPICollectionClient(settings)
    if not client.configured:
        return {"ok": False, "error": "TonAPI client not configured (TONAPI_ENABLED / TONAPI_API_KEY)."}
    raw = await client.get_nft(address.strip())
    if not raw or not isinstance(raw, dict):
        return {"ok": False, "error": "NFT not found or empty response."}
    meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    name = (meta.get("name") or raw.get("name") or "")[:500] or None
    media = extract_nft_preview_media(raw, ipfs_gateway_url=settings.ipfs_gateway_url)
    meta_log = safe_media_url_for_log(media.url)
    return {
        "ok": True,
        "nft_name": name,
        "media": {
            "kind": media.kind,
            "source_field": media.source_field,
            "url_host": meta_log.get("url_host"),
            "url_ext": meta_log.get("url_ext"),
        },
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Inspect NFT preview media selection (TonAPI).")
    p.add_argument("nft_address", help="NFT address (EQ... / raw)")
    args = p.parse_args()
    out = asyncio.run(_run(args.nft_address))
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
