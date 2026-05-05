"""python -m app.tools.sample_all_collection_aliases"""

from __future__ import annotations

import argparse
import asyncio
import json

from app.config import get_settings
from app.services.global_nft_indexer import sample_all_collection_aliases


def main() -> None:
    settings = get_settings()
    p = argparse.ArgumentParser(description="Sample item names → nft_collection_aliases for indexed collections.")
    p.add_argument("--sample-items", type=int, default=None)
    p.add_argument("--max-collections", type=int, default=None)
    p.add_argument("--only-new", action="store_true", default=True)
    p.add_argument("--all-statuses", action="store_true", help="Do not filter by index_status")
    p.add_argument("--sleep-ms", type=int, default=settings.nft_global_index_request_sleep_ms)
    args = p.parse_args()
    out = asyncio.run(
        sample_all_collection_aliases(
            settings,
            sample_items=args.sample_items,
            max_collections=args.max_collections,
            only_new=not args.all_statuses,
            sleep_ms=args.sleep_ms,
        )
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
