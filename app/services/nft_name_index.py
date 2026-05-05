"""Нормализация и разбор имён NFT / «коллекция #номер» для глобального индекса."""

from __future__ import annotations

import re
import unicodedata

_NUM_TAIL_RE = re.compile(
    r"(?i)([#№])\s*([\d\s,\u00A0\u202F\.]+)\s*$",
)


def normalize_nft_text(value: str) -> str:
    """NFKC, lower, trim, схлопывание пробелов, _ и - как пробелы, без управляющих символов."""
    if not isinstance(value, str):
        return ""
    s = unicodedata.normalize("NFKC", value).strip().lower()
    s = s.replace("_", " ").replace("-", " ")
    s = " ".join(s.split())
    out: list[str] = []
    for ch in s:
        if ch.isalnum() or ch.isspace():
            out.append(ch)
        elif ord(ch) > 127 and not ch.isspace():
            out.append(ch)
    return " ".join("".join(out).split())


def extract_item_number_from_name(name: str) -> int | None:
    """
    Извлекает номер из хвоста имени: #974, №217467, #57 234 -> 57234, #57,234.
    """
    if not isinstance(name, str) or not name.strip():
        return None
    m = _NUM_TAIL_RE.search(name.strip())
    if not m:
        return None
    raw = m.group(2)
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    try:
        v = int(digits)
    except ValueError:
        return None
    return v if v >= 0 else None


def extract_base_name_from_nft_name(name: str) -> str | None:
    """«Bunny Muffin #974» -> «Bunny Muffin»."""
    if not isinstance(name, str) or not name.strip():
        return None
    m = _NUM_TAIL_RE.search(name.strip())
    if not m:
        return None
    base = name[: m.start()].strip()
    return base or None


def parse_collection_number_payload(payload: str) -> tuple[str, int] | None:
    """«Bunny Muffin #974» -> («Bunny Muffin», 974)."""
    if not isinstance(payload, str):
        return None
    s = payload.strip()
    if not s:
        return None
    m = _NUM_TAIL_RE.search(s)
    if not m:
        return None
    raw = m.group(2)
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    try:
        num = int(digits)
    except ValueError:
        return None
    base = s[: m.start()].strip()
    if not base:
        return None
    return base, num
