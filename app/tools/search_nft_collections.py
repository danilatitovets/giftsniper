"""CLI: python -m app.tools.search_nft_collections "Pretty Posy" --source toncenter --max-pages 30"""

from __future__ import annotations

import argparse
import asyncio
import json

from app.config import get_settings
from app.services.tonapi_collection_client import TonAPICollectionClient
from app.services.universal_nft_resolver import search_nft_collections


async def _run(query: str, *, source: str, max_pages: int) -> dict:
    settings = get_settings()
    client = TonAPICollectionClient(settings)
    return await search_nft_collections(query, settings, client, source=source, max_pages=max_pages)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("query")
    p.add_argument("--source", choices=("toncenter", "tonapi"), default="toncenter")
    p.add_argument("--max-pages", type=int, default=30)
    args = p.parse_args()
    out = asyncio.run(_run(args.query, source=args.source, max_pages=args.max_pages))
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
