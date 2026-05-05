from __future__ import annotations

import base64
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from enum import Enum
from urllib.parse import parse_qs, unquote, urlparse

from app.sources.normalization import normalize_collection_name

# User-friendly TON: EQ/UQ with url-safe alphabet.
_NFT_USER_ADDR_RE = re.compile(r"^(EQ|UQ)[A-Za-z0-9_-]{40,90}$")
_RAW_WORKCHAIN_ADDR_RE = re.compile(r"^-?\d+:[0-9a-fA-F]{64}$")
_RAW_HEX_ADDR_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_COLLECTION_NUM_TAIL_RE = re.compile(
    r"^(.+?)\s*(?:[/|]|№|#)\s*(\d+)\s*$",
    re.IGNORECASE,
)
_COLLECTION_NUM_SPACE_RE = re.compile(r"^(.+?)\s+(\d+)\s*$", re.IGNORECASE)
_BUY_PRICE_INLINE_RE = re.compile(
    r"(?i)(?:^|\s)(?:at|for|price)\s*:?\s*(\d+(?:[.,]\d+)?)\s*(?:ton)?(?:\s|$)",
)
_BUY_PRICE_SUFFIX_RE = re.compile(r"(?i)\b(?:at|for)\s+(\d+(?:[.,]\d+)?)\s*(?:ton)?\b")


class GiftInputType(str, Enum):
    collection_number = "collection_number"
    nft_address = "nft_address"
    marketplace_url = "marketplace_url"
    telegram_gift_url = "telegram_gift_url"
    getgems_startapp = "getgems_startapp"
    unknown = "unknown"


@dataclass
class GiftInput:
    raw_text: str
    input_type: GiftInputType
    collection: str | None = None
    number: int | None = None
    nft_address: str | None = None
    collection_address: str | None = None
    marketplace: str | None = None
    source_url: str | None = None
    listing_price_ton: float | None = None
    source_hint: str | None = None
    startapp_decoded_path: str | None = None
    parse_warnings: list[str] = field(default_factory=list)


@dataclass
class GiftIdentity:
    collection: str
    number: int | None
    nft_address: str | None
    collection_address: str | None
    normalized_collection: str
    canonical_key: str
    source_url: str | None = None
    marketplace: str | None = None
    confidence: int = 70
    warnings: list[str] = field(default_factory=list)
    metadata_extra: dict[str, Any] | None = None


def normalize_gift_collection(name: str) -> str:
    return normalize_collection_name(name)


def is_probable_ton_address(value: str) -> tuple[bool, list[str]]:
    """Heuristic only — not full chain validation."""
    warnings: list[str] = []
    v = (value or "").strip()
    if not v:
        return False, []
    if _RAW_WORKCHAIN_ADDR_RE.match(v):
        return True, warnings
    if _NFT_USER_ADDR_RE.match(v):
        if len(v) > 70:
            warnings.append("Адрес необычно длинный — перепроверь копирование.")
        return True, warnings
    if re.match(r"^(EQ|UQ)", v) and 40 <= len(v) <= 90:
        warnings.append("Адрес похож на TON friendly, но формат нестандартный — перепроверь.")
        return True, warnings
    return False, warnings


def parse_nft_address(text: str) -> str | None:
    candidate = text.strip()
    normalized = normalize_ton_nft_address(candidate)
    if normalized:
        return normalized
    ok, _ = is_probable_ton_address(candidate)
    return candidate if ok else None


def normalize_ton_nft_address(value: str) -> str | None:
    """Normalize TON NFT address variants into the forms accepted by TonAPI."""
    v = (value or "").strip()
    if not v:
        return None
    if _NFT_USER_ADDR_RE.match(v):
        return v
    if _RAW_WORKCHAIN_ADDR_RE.match(v):
        wc, raw = v.split(":", 1)
        return f"{wc}:{raw.lower()}"
    if _RAW_HEX_ADDR_RE.match(v):
        return "0:" + v.lower()
    return None


def _host_matches(host: str, *needles: str) -> bool:
    h = host.lower()
    return any(n in h for n in needles)


def _normalize_source_url(url: str) -> str:
    u = url.strip()
    try:
        p = urlparse(u)
        return p._replace(fragment="").geturl() if p.fragment else u
    except Exception:
        return u


def _find_address_in_text(s: str) -> str | None:
    for token in re.split(r"[^\w:/-]", s):
        t = token.strip()
        if parse_nft_address(t):
            return t
    m = re.search(r"(EQ|UQ)[A-Za-z0-9_-]{40,}", s)
    if m and parse_nft_address(m.group(0)):
        return m.group(0)
    m2 = re.search(r"(-?\d+:[0-9a-fA-F]{64})", s)
    if m2 and parse_nft_address(m2.group(1)):
        return m2.group(1)
    return None


def _parse_float_price(raw: str) -> float | None:
    try:
        v = float(raw.replace(",", "."))
        return v if v > 0 else None
    except ValueError:
        return None


def _parse_price_query(url: str) -> float | None:
    try:
        qs = parse_qs(urlparse(url).query)
        for key in ("price", "ton", "amount", "value", "listing_price"):
            if key in qs and qs[key]:
                v = _parse_float_price(qs[key][0])
                if v is not None:
                    return v
    except Exception:
        return None
    return None


def extract_buy_price_from_text(text: str) -> float | None:
    """Extract a TON buy price from free-form text (deal command body, paste lines)."""
    if not text:
        return None
    q = _parse_price_query(text)
    if q is not None:
        return q
    m = _BUY_PRICE_INLINE_RE.search(text)
    if m:
        v = _parse_float_price(m.group(1))
        if v is not None:
            return v
    m2 = _BUY_PRICE_SUFFIX_RE.search(text)
    if m2:
        v = _parse_float_price(m2.group(1))
        if v is not None:
            return v
    m3 = re.search(r"(?i)\bprice\s+(\d+(?:[.,]\d+)?)\b", text)
    if m3:
        v = _parse_float_price(m3.group(1))
        if v is not None:
            return v
    return None


def normalize_deal_subject(ref: str) -> str:
    """Strip leading 'buy' and trailing 'at/for <price> TON' from a deal subject string."""
    r = ref.strip()
    r = re.sub(r"(?i)^buy\s+", "", r)
    r = re.sub(r"(?i)\s+(?:at|for)\s+\d+(?:[.,]\d+)?\s*(?:ton)?\s*$", "", r)
    return r.strip()


def scrub_import_line(line: str) -> str:
    """Strip list prefixes and noise; return best gift-like substring (one line)."""
    s = unicodedata.normalize("NFKC", line.strip())
    if not s:
        return ""
    s = re.sub(r"^\s*[\[\(]?\d+[\]\).]\s*", "", s)
    s = re.sub(r"(?i)^buy\s*:\s*", "", s)
    url_m = re.search(r"https?://[^\s<>]+", s)
    if url_m:
        return url_m.group(0).rstrip(").,;]")
    addr_m = re.search(r"(EQ|UQ)[A-Za-z0-9_-]{40,}", s)
    if addr_m:
        return addr_m.group(0)
    raw_m = re.search(r"-?\d+:[0-9a-fA-F]{64}", s)
    if raw_m:
        return raw_m.group(0)
    s = re.sub(r"(?i)\s+at\s+(\d+(?:[.,]\d+)?)\s*(?:ton)?\s*$", "", s)
    s = re.sub(r"(?i)\s+price\s+(\d+(?:[.,]\d+)?)\s*$", "", s)
    return s.strip()


def parse_explorer_url(url: str) -> GiftInput:
    warnings: list[str] = []
    parsed = urlparse(url.strip())
    host = (parsed.netloc or "").lower()
    path = unquote(parsed.path or "")
    if parsed.scheme not in ("http", "https") or not host:
        return GiftInput(
            raw_text=url,
            input_type=GiftInputType.unknown,
            parse_warnings=["Некорректная ссылка explorer."],
        )

    if not (
        _host_matches(host, "tonviewer", "tonscan", "toncoin.org")
        or (_host_matches(host, "tonapi.io") and ("/nfts/" in path or "/accounts/" in path))
    ):
        return GiftInput(
            raw_text=url,
            input_type=GiftInputType.unknown,
            marketplace="explorer",
            source_url=_normalize_source_url(url),
            parse_warnings=["Домен не похож на известный TON explorer."],
        )

    listing_price = _parse_price_query(url)
    nft_addr = _find_address_in_text(f"{path}?{parsed.query}")
    segments = [x for x in path.split("/") if x]

    if not nft_addr and "nft" in segments:
        idx = segments.index("nft")
        if idx + 1 < len(segments):
            nft_addr = _find_address_in_text(segments[idx + 1]) or parse_nft_address(segments[idx + 1])

    if _host_matches(host, "tonscan") and "address" in segments:
        idx = segments.index("address")
        if idx + 1 < len(segments):
            nft_addr = nft_addr or _find_address_in_text(segments[idx + 1])

    if not nft_addr:
        warnings.append("Explorer: в URL не найден EQ/UQ/0:… адрес — пришли NFT address отдельно.")

    if listing_price is not None:
        warnings.append("Цена из explorer URL — только listing_hint, не рыночный floor/sales.")

    inferred = GiftInputType.marketplace_url
    if nft_addr:
        inferred = GiftInputType.nft_address

    return GiftInput(
        raw_text=url,
        input_type=inferred,
        nft_address=nft_addr,
        marketplace="explorer",
        source_url=_normalize_source_url(url),
        listing_price_ton=listing_price,
        parse_warnings=warnings,
    )


def parse_marketplace_url(url: str) -> GiftInput:
    warnings: list[str] = []
    parsed = urlparse(url.strip())
    host = (parsed.netloc or "").lower()
    path = unquote(parsed.path or "")
    if parsed.scheme not in ("http", "https") or not host:
        return GiftInput(
            raw_text=url,
            input_type=GiftInputType.unknown,
            parse_warnings=["Некорректная ссылка."],
        )

    listing_price: float | None = _parse_price_query(url)
    marketplace: str | None = None

    if _host_matches(host, "getgems"):
        marketplace = "getgems"
    elif _host_matches(host, "fragment"):
        marketplace = "fragment"
    elif _host_matches(host, "tonnel"):
        marketplace = "tonnel"
    else:
        marketplace = "external"

    nft_addr = _find_address_in_text(f"{path}?{parsed.query}")
    collection_address: str | None = None
    number: int | None = None
    collection_guess: str | None = None

    segments = [s for s in path.split("/") if s]
    if marketplace == "getgems":
        if "collection" in segments:
            idx = segments.index("collection")
            if idx + 1 < len(segments):
                collection_address = segments[idx + 1]
            if idx + 2 < len(segments) and segments[idx + 2].isdigit():
                number = int(segments[idx + 2])
        elif "nft" in segments:
            idx = segments.index("nft")
            if idx + 1 < len(segments):
                seg = segments[idx + 1]
                nft_addr = nft_addr or _find_address_in_text(seg) or parse_nft_address(seg)
        if not collection_address and not nft_addr and not number:
            warnings.append("Getgems: не удалось извлечь collection address, NFT address или index из пути.")
    elif marketplace == "fragment":
        if "gift" in segments:
            idx = segments.index("gift")
            slug = segments[idx + 1] if idx + 1 < len(segments) else ""
            if slug:
                collection_guess = normalize_gift_collection(slug.replace("-", " ").replace("_", " "))
                warnings.append("Fragment: slug распознан; номер элемента в URL часто отсутствует — уточни # или NFT address.")
            else:
                warnings.append("Fragment: путь /gift без slug.")
        else:
            warnings.append("Fragment: ожидался путь с /gift/ — данных может не хватать.")
    elif marketplace == "tonnel":
        warnings.append("Tonnel: ссылка распознана; без запросов к сайту извлекаю только видимые в URL данные.")
        nft_addr = nft_addr or _find_address_in_text(path)
        if not nft_addr and not any(x.isdigit() for x in segments[-2:]):
            warnings.append("Tonnel: не найден address или числовой индекс в URL.")

    inferred_type = GiftInputType.marketplace_url
    if marketplace == "external":
        warnings.append("Неизвестный домен — извлекаю только адрес/цену из текста URL (без HTTP к сайту).")
        if not nft_addr and not collection_address and number is None and not collection_guess:
            inferred_type = GiftInputType.unknown
            warnings.append(
                "Я вижу ссылку, но не могу надёжно понять Gift. Пришли: Ice Cream #217467 или NFT address."
            )
    elif marketplace in {"getgems", "fragment", "tonnel"}:
        if not nft_addr and not collection_address and number is None and not collection_guess:
            warnings.append(
                f"{marketplace.title()}: в ссылке не хватает номера, NFT или collection address — дополни вручную."
            )

    if inferred_type == GiftInputType.unknown and marketplace != "external":
        inferred_type = GiftInputType.marketplace_url

    if listing_price is not None:
        warnings.append("Цена из URL — только listing_hint для входа (/deal), не floor и не история продаж.")

    return GiftInput(
        raw_text=url,
        input_type=inferred_type,
        collection=collection_guess,
        number=number,
        nft_address=nft_addr,
        collection_address=collection_address,
        marketplace=marketplace,
        source_url=_normalize_source_url(url),
        listing_price_ton=listing_price,
        parse_warnings=warnings,
    )


def parse_telegram_gift_url(url: str, _depth: int = 0) -> GiftInput:
    parsed = urlparse(url.strip())
    host = (parsed.netloc or "").lower()
    path = unquote(parsed.path or "")
    qs = parse_qs(parsed.query)
    if parsed.scheme not in ("http", "https") or not host:
        return GiftInput(
            raw_text=url,
            input_type=GiftInputType.unknown,
            parse_warnings=["Некорректная ссылка Telegram."],
        )
    if not _host_matches(host, "t.me", "telegram.me"):
        return GiftInput(
            raw_text=url,
            input_type=GiftInputType.unknown,
            marketplace="telegram",
            source_url=_normalize_source_url(url),
            parse_warnings=["Это не похоже на ссылку t.me / telegram.me."],
        )

    if path.startswith("/share/url") and qs.get("url"):
        inner = unquote(qs["url"][0])
        if inner.lower().startswith(("http://", "https://")):
            inner_gi = parse_gift_input(inner, _depth=_depth + 1)
            w = ["Расшаренная ссылка t.me — разобран вложенный URL."] + list(inner_gi.parse_warnings)
            return GiftInput(
                raw_text=url,
                input_type=GiftInputType.telegram_gift_url,
                collection=inner_gi.collection,
                number=inner_gi.number,
                nft_address=inner_gi.nft_address,
                collection_address=inner_gi.collection_address,
                marketplace="telegram",
                source_url=_normalize_source_url(url),
                listing_price_ton=inner_gi.listing_price_ton,
                parse_warnings=w,
            )

    def _decode_startapp_path(raw_value: str) -> str | None:
        s = (raw_value or "").strip()
        if not s:
            return None
        try:
            pad = "=" * ((4 - len(s) % 4) % 4)
            decoded = base64.urlsafe_b64decode((s + pad).encode("ascii")).decode("utf-8", errors="ignore")
        except Exception:
            return None
        return decoded.strip() or None

    if qs.get("startapp"):
        decoded = _decode_startapp_path(qs["startapp"][0])
        if decoded:
            d_parsed = urlparse(decoded)
            d_path = unquote(d_parsed.path or decoded)
            d_segments = [s for s in d_path.split("/") if s]
            # t.me links use netloc "t.me" and username in path: /GetgemsNftBot/gems?startapp=…
            path_norm = (path or "").lower().replace("-", "")
            gg_host = "getgemsnftbot" in host or "getgemsnftbot" in path_norm
            if len(d_segments) >= 2 and d_segments[0].lower() == "collection":
                coll = parse_nft_address(d_segments[1])
                nft = parse_nft_address(d_segments[2]) if len(d_segments) >= 3 else None
                if coll and nft and coll == nft:
                    return GiftInput(
                        raw_text=url,
                        input_type=GiftInputType.getgems_startapp if gg_host else GiftInputType.telegram_gift_url,
                        nft_address=None,
                        collection_address=coll,
                        marketplace="telegram",
                        source_url=_normalize_source_url(url),
                        source_hint="getgems_startapp_invalid",
                        startapp_decoded_path=d_path,
                        parse_warnings=[
                            "Не удалось разобрать Getgems startapp: второй адрес совпадает с коллекцией. "
                            "Пришли корректную ссылку на NFT."
                        ],
                    )
                if coll and nft:
                    return GiftInput(
                        raw_text=url,
                        input_type=GiftInputType.getgems_startapp if gg_host else GiftInputType.telegram_gift_url,
                        nft_address=nft,
                        collection_address=coll,
                        marketplace="telegram",
                        source_url=_normalize_source_url(url),
                        source_hint="getgems_startapp_collection_nft",
                        startapp_decoded_path=d_path,
                    )
                if coll and not nft:
                    return GiftInput(
                        raw_text=url,
                        input_type=GiftInputType.getgems_startapp if gg_host else GiftInputType.telegram_gift_url,
                        collection_address=coll,
                        marketplace="telegram",
                        source_url=_normalize_source_url(url),
                        source_hint="getgems_startapp_collection_only",
                        startapp_decoded_path=d_path,
                        parse_warnings=[
                            "Это ссылка на коллекцию, а не на конкретный NFT. Пришли ссылку на сам NFT."
                        ],
                    )

    segments = [s for s in path.split("/") if s]
    collection_guess: str | None = None
    number: int | None = None
    nft_addr: str | None = None
    warnings: list[str] = []

    if segments and segments[0] == "nft" and len(segments) >= 2:
        nft_addr = _find_address_in_text(segments[1]) or parse_nft_address(segments[1])
        if not nft_addr:
            warnings.append("t.me/nft: не удалось вытащить address из сегмента.")
    elif segments and segments[0] == "gifts" and len(segments) >= 2:
        slug = segments[1]
        collection_guess = normalize_gift_collection(slug.replace("-", " ").replace("_", " "))
        if len(segments) >= 3 and segments[2].isdigit():
            number = int(segments[2])
        else:
            warnings.append("Telegram gifts: номер в URL отсутствует — уточни # вручную.")
    elif "gift" in segments:
        idx = segments.index("gift")
        slug = segments[idx + 1] if idx + 1 < len(segments) else ""
        if slug:
            collection_guess = normalize_gift_collection(slug.replace("-", " "))
        warnings.append("t.me gift path: identity может быть не полностью в URL.")
    else:
        warnings.append("Telegram link recognized, but Gift identity is not fully encoded in URL.")

    source_hint = "telegram_gift_url" if (not nft_addr and number is None and not collection_guess) else None

    if not collection_guess and not nft_addr and number is None:
        warnings.append("Telegram: пришли коллекцию и # или NFT address для точного действия.")

    return GiftInput(
        raw_text=url,
        input_type=GiftInputType.telegram_gift_url,
        collection=collection_guess,
        number=number,
        nft_address=nft_addr,
        marketplace="telegram",
        source_url=_normalize_source_url(url),
        listing_price_ton=_parse_price_query(url),
        source_hint=source_hint,
        parse_warnings=warnings,
    )


def parse_collection_number(text: str) -> tuple[str, int] | None:
    raw = " ".join(text.strip().split())
    if not raw:
        return None
    m = _COLLECTION_NUM_TAIL_RE.match(raw)
    if m:
        return normalize_gift_collection(m.group(1)), int(m.group(2))
    m2 = _COLLECTION_NUM_SPACE_RE.match(raw)
    if m2:
        return normalize_gift_collection(m2.group(1)), int(m2.group(2))
    return None


def parse_gift_input(text: str, _depth: int = 0) -> GiftInput:
    if _depth > 2:
        return GiftInput(
            raw_text=text or "",
            input_type=GiftInputType.unknown,
            parse_warnings=["Слишком глубокая вложенность ссылок."],
        )
    raw = (text or "").strip()
    if not raw:
        return GiftInput(raw_text=text or "", input_type=GiftInputType.unknown, parse_warnings=["Пустой ввод."])

    if raw.lower().startswith(("http://", "https://")):
        p = urlparse(raw)
        h = (p.netloc or "").lower()
        if _host_matches(h, "t.me", "telegram.me"):
            return parse_telegram_gift_url(raw, _depth=_depth)
        if _host_matches(h, "tonviewer", "tonscan") or (
            _host_matches(h, "tonapi.io") and ("/nfts/" in unquote(p.path or "") or "/accounts/" in unquote(p.path or ""))
        ):
            return parse_explorer_url(raw)
        return parse_marketplace_url(raw)

    ok_addr, addr_warn = is_probable_ton_address(raw)
    if ok_addr:
        gi = GiftInput(
            raw_text=raw,
            input_type=GiftInputType.nft_address,
            nft_address=raw.strip(),
            parse_warnings=list(addr_warn),
        )
        return gi

    parsed_cn = parse_collection_number(raw)
    if parsed_cn:
        col, num = parsed_cn
        return GiftInput(
            raw_text=raw,
            input_type=GiftInputType.collection_number,
            collection=col,
            number=num,
        )

    return GiftInput(
        raw_text=raw,
        input_type=GiftInputType.unknown,
        parse_warnings=[
            "Не удалось распознать подарок. Примеры: Ice Cream #217467, NFT address (EQ...), или ссылка маркетплейса."
        ],
    )


def build_canonical_gift_key(
    *,
    collection: str | None,
    number: int | None,
    nft_address: str | None,
    normalized_collection: str | None = None,
) -> str:
    norm = normalized_collection or (normalize_gift_collection(collection) if collection else "")
    if nft_address and not norm:
        return f"addr:{nft_address}"
    if norm and number is not None:
        key_col = norm.replace(" ", "_").lower()
        return f"{key_col}#{number}"
    if nft_address:
        return f"addr:{nft_address}"
    return f"unknown:{hash((norm, number, nft_address)) & 0xFFFFFFFF:x}"


def smells_like_gift_link(text: str) -> bool:
    low = text.lower().strip()
    return any(
        x in low
        for x in (
            "getgems",
            "getgemsnftbot",
            "fragment.com",
            "tonviewer",
            "tonscan",
            "tonapi.io",
            "t.me/nft",
            "t.me/gifts",
            "/nft/",
            "tonnel",
        )
    )


def format_parse_result(gi: GiftInput) -> str:
    lines = [f"Тип ввода: {gi.input_type.value}"]
    if gi.collection:
        lines.append(f"Коллекция: {gi.collection}")
    if gi.number is not None:
        lines.append(f"Номер: #{gi.number}")
    if gi.nft_address:
        lines.append(f"NFT: {gi.nft_address}")
    if gi.marketplace:
        lines.append(f"Площадка: {gi.marketplace}")
    if gi.listing_price_ton is not None:
        lines.append(f"Цена в ссылке (если есть): {gi.listing_price_ton} TON")
    if gi.parse_warnings:
        lines.append("Заметки:\n- " + "\n- ".join(gi.parse_warnings))
    return "\n".join(lines)
