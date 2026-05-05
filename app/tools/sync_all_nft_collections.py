"""python -m app.tools.sync_all_nft_collections"""

from __future__ import annotations

import argparse
import asyncio
import json

from app.config import get_settings
from app.services.global_nft_indexer import sync_all_nft_collections


def main() -> None:
    settings = get_settings()
    p = argparse.ArgumentParser(description="Sync TonAPI NFT collections into nft_collections_index.")
    p.add_argument("--limit-per-page", type=int, default=None)
    p.add_argument("--max-collections", type=int, default=None)
    p.add_argument("--sleep-ms", type=int, default=settings.nft_global_index_request_sleep_ms)
    args = p.parse_args()
    out = asyncio.run(
        sync_all_nft_collections(
            settings,
            limit_per_page=args.limit_per_page,
            max_collections=args.max_collections,
            sleep_ms=args.sleep_ms,
        )
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
