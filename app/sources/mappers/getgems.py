from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.gift import GiftAttributeSchema
from app.schemas.market import ListingSchema, MarketFloor, SaleSchema


def _as_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_ton_price(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        val = float(value)
        if isinstance(value, int) and val >= 1_000_000_000:
            return val / 1_000_000_000
        return val
    if isinstance(value, str):
        try:
            val = float(value)
        except ValueError:
            return None
        if value.isdigit() and val >= 1_000_000_000:
            return val / 1_000_000_000
        return val
    if isinstance(value, dict):
        amount = value.get("amount") or value.get("value") or value.get("price")
        currency = str(value.get("currency") or value.get("symbol") or "").upper()
        parsed = parse_ton_price(amount)
        if parsed is None:
            return None
        if currency in ("NANOTON", "NANO_TON", "NANO"):
            return parsed / 1_000_000_000 if parsed > 1_000_000 else parsed
        return parsed
    return None


def _price_with_uncertainty(value) -> tuple[float | None, bool]:
    if value is None:
        return None, False
    if isinstance(value, dict):
        currency = str(value.get("currency") or value.get("symbol") or "").upper()
        if not currency:
            parsed = parse_ton_price(value)
            return parsed, True if parsed is not None else False
    if isinstance(value, str) and value.isdigit() and len(value) >= 11:
        parsed = parse_ton_price(value)
        return parsed, True if parsed is not None else False
    return parse_ton_price(value), False


def _extract_items(payload: dict | list | None) -> list[dict]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "items", "nfts", "results", "history"):
        candidate = payload.get(key)
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
        if isinstance(candidate, dict):
            for nested in ("items", "nfts", "results", "history"):
                nested_candidate = candidate.get(nested)
                if isinstance(nested_candidate, list):
                    return [item for item in nested_candidate if isinstance(item, dict)]
    return []


def parse_getgems_floor(payload: dict | list | None, collection: str = "") -> MarketFloor | None:
    if isinstance(payload, dict):
        val = _as_float(payload.get("floorPrice"))
        if val is None and isinstance(payload.get("data"), dict):
            val = _as_float(payload["data"].get("floorPrice"))
        if val is not None:
            return MarketFloor(collection=collection or "Unknown", source="Getgems", floor_ton=val)
    listings = parse_getgems_listings(payload, collection=collection)
    if not listings:
        return None
    return MarketFloor(collection=collection or listings[0].collection, source="Getgems", floor_ton=listings[0].price_ton)


def parse_getgems_attributes(payload: dict | None) -> list[GiftAttributeSchema]:
    if not isinstance(payload, dict):
        return []
    raw = (
        payload.get("attributes")
        or payload.get("traits")
        or (payload.get("metadata") or {}).get("attributes")
        or ((payload.get("content") or {}).get("metadata") or {}).get("attributes")
        or []
    )
    if not isinstance(raw, list):
        return []
    out: list[GiftAttributeSchema] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        trait_type = str(item.get("trait_type") or item.get("traitType") or item.get("name") or "").strip()
        trait_value = str(item.get("value") or item.get("trait_value") or "").strip()
        if not trait_type or not trait_value:
            continue
        out.append(GiftAttributeSchema(trait_type=trait_type, trait_value=trait_value, rarity_percent=_as_float(item.get("rarity"))))
    return out


def parse_getgems_listings(payload: dict | list | None, collection: str = "") -> list[ListingSchema]:
    items = _extract_items(payload)
    out: list[ListingSchema] = []
    for idx, item in enumerate(items, 1):
        raw_price = (
            (item.get("sale") or {}).get("price")
            or (item.get("sale") or {}).get("fullPrice")
            or item.get("price")
            or item.get("priceTon")
            or item.get("salePrice")
        )
        price, uncertain = _price_with_uncertainty(raw_price)
        if price is None:
            continue
        number = item.get("index") or item.get("number") or idx
        try:
            number = int(number)
        except (TypeError, ValueError):
            number = idx
        url = str(item.get("url") or item.get("link") or "")
        external_id = str(
            item.get("id")
            or item.get("address")
            or (item.get("item") or {}).get("address")
            or item.get("nftAddress")
            or f"getgems_listing_{idx}"
        )
        attrs = parse_getgems_attributes(item)
        attrs_json = {"attributes": [a.model_dump() for a in attrs]} if attrs else {}
        if uncertain:
            attrs_json["_price_units_uncertain"] = True
        out.append(
            ListingSchema(
                external_id=external_id,
                source="Getgems",
                collection=collection or str(item.get("collection") or "Unknown"),
                number=number,
                price_ton=price,
                url=url,
                image_url=item.get("image") or item.get("imageUrl"),
                attributes_json=attrs_json,
            )
        )
    out.sort(key=lambda x: x.price_ton)
    return out


def parse_getgems_sales(payload: dict | list | None, collection: str = "") -> list[SaleSchema]:
    items = _extract_items(payload)
    if isinstance(payload, dict):
        for key in ("events",):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                items = [x for x in candidate if isinstance(x, dict)]
                break
    out: list[SaleSchema] = []
    for idx, item in enumerate(items, 1):
        evt = str(item.get("type") or item.get("eventType") or "").lower()
        if not evt:
            continue
        if "sale" not in evt and "sold" not in evt:
            continue
        raw_price = (
            item.get("price")
            or item.get("priceTon")
            or item.get("salePrice")
            or (item.get("sale") or {}).get("price")
        )
        price = parse_ton_price(raw_price)
        if price is None:
            continue
        number = item.get("index") or item.get("number") or idx
        try:
            number = int(number)
        except (TypeError, ValueError):
            number = idx
        sold_raw = item.get("soldAt") or item.get("timestamp")
        sold_at = datetime.now(timezone.utc)
        if isinstance(sold_raw, str):
            try:
                sold_at = datetime.fromisoformat(sold_raw.replace("Z", "+00:00"))
            except ValueError:
                pass
        out.append(
            SaleSchema(
                external_id=str(item.get("id") or item.get("eventId") or f"getgems_sale_{idx}"),
                source="Getgems",
                collection=collection or str(item.get("collection") or "Unknown"),
                number=number,
                price_ton=price,
                sold_at=sold_at,
                attributes_json={},
            )
        )
    out.sort(key=lambda x: x.sold_at, reverse=True)
    return out
