"""python -m app.tools.index_collection_items --collection <address>"""

from __future__ import annotations

import argparse
import asyncio
import json

from app.config import get_settings
from app.services.global_nft_indexer import index_collection_items


def main() -> None:
    settings = get_settings()
    p = argparse.ArgumentParser(description="Index NFT items for one collection (heavy; gated by env).")
    p.add_argument("--collection", required=True, help="Collection TON address")
    p.add_argument("--limit-per-page", type=int, default=None)
    p.add_argument("--max-items", type=int, default=None)
    p.add_argument("--no-resume", action="store_true")
    p.add_argument("--sleep-ms", type=int, default=settings.nft_global_index_request_sleep_ms)
    args = p.parse_args()
    out = asyncio.run(
        index_collection_items(
            settings,
            args.collection.strip(),
            limit_per_page=args.limit_per_page,
            max_items=args.max_items,
            resume=not args.no_resume,
            sleep_ms=args.sleep_ms,
        )
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
