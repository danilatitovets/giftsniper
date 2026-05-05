from app.config import get_settings
from app.sources.collections import get_source_identifier, load_collection_registry, resolve_collection
from app.sources.http import MarketHTTPClient
from app.sources.tonapi import TonApiSource


async def check_nft_metadata(collection: str | None = None, number: int | None = None, address: str | None = None) -> dict:
    settings = get_settings()
    source = TonApiSource(
        settings,
        http_client=MarketHTTPClient(
            timeout_seconds=settings.market_http_timeout_seconds,
            retries=settings.market_http_retries,
            user_agent=settings.market_http_user_agent,
        ),
    )
    if address:
        nft = await source.get_nft_by_address(address)
        if not nft:
            return {"status": "не найден", "source": source.name, "need_address": False}
        owner = (nft.get("owner") or {}).get("address") if isinstance(nft, dict) else None
        attrs = (nft.get("metadata") or {}).get("attributes") if isinstance(nft, dict) else None
        history = await source.get_nft_history(address, limit=20)
        return {
            "status": "найден",
            "source": source.name,
            "collection": (nft.get("collection") or {}).get("name") if isinstance(nft, dict) else None,
            "nft_address": address,
            "owner": owner,
            "attributes": attrs if isinstance(attrs, list) else [],
            "history_available": bool(history),
            "need_address": False,
        }
    if collection and number is not None:
        registry = load_collection_registry(settings.collection_registry_path)
        canonical, payload = resolve_collection(collection, registry)
        collection_address = get_source_identifier(canonical or collection, "getgems", "collection_address", registry=registry)
        if not payload or not collection_address:
            return {"status": "нужен address", "source": source.name, "need_address": True}
        # TonAPI collection+index mapping is not always deterministic without address.
        return {"status": "нужен address", "source": source.name, "need_address": True}
    return {"status": "нужен address", "source": source.name, "need_address": True}


def format_nft_check_result(result: dict) -> str:
    status = result.get("status", "неизвестно")
    if status == "нужен address":
        return (
            "🔎 NFT Check\n\n"
            f"Источник: {result.get('source', 'TonAPI')}\n"
            "Статус: нужен address\n\n"
            "Для точной проверки нужен NFT address.\n"
            "Проверка collection+number сейчас best-effort и может быть неточной."
        )
    if status != "найден":
        return (
            "🔎 NFT Check\n\n"
            f"Источник: {result.get('source', 'TonAPI')}\n"
            "Статус: не найден"
        )
    attrs = result.get("attributes") or []
    attrs_text = "\n".join(f"- {a.get('trait_type') or a.get('traitType')}: {a.get('value')}" for a in attrs[:8]) if attrs else "- нет"
    return (
        "🔎 NFT Check\n\n"
        f"Источник: {result.get('source', 'TonAPI')}\n"
        f"Статус: {result.get('status')}\n\n"
        f"Коллекция: {result.get('collection') or 'unknown'}\n"
        f"Адрес NFT: {result.get('nft_address') or 'unknown'}\n"
        f"Владелец: {result.get('owner') or 'unknown'}\n"
        f"Атрибуты:\n{attrs_text}\n"
        f"История: {'доступна' if result.get('history_available') else 'недоступна'}\n\n"
        "Важно: это on-chain/metadata проверка, не live marketplace floor/listing price."
    )
