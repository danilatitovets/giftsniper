"""Безопасное извлечение комментария и суммы из объекта транзакции TonAPI."""

from __future__ import annotations

from typing import Any


def _as_int(v: Any) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str) and v.isdigit():
        return int(v)
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def extract_ton_transfer_comment(tx: dict[str, Any]) -> str | None:
    """Достаёт текст комментария входящего перевода, если он есть. Не бросает исключений."""
    if not isinstance(tx, dict):
        return None

    def from_obj(obj: Any, depth: int = 0) -> str | None:
        if depth > 12 or obj is None:
            return None
        if isinstance(obj, str):
            s = obj.strip()
            return s or None
        if isinstance(obj, dict):
            for key in ("text", "comment", "payload", "message"):
                if key in obj:
                    r = from_obj(obj[key], depth + 1)
                    if r:
                        return r
            if "decoded_body" in obj:
                r = from_obj(obj["decoded_body"], depth + 1)
                if r:
                    return r
            if "value" in obj and len(obj) <= 6:
                for v in obj.values():
                    r = from_obj(v, depth + 1)
                    if r:
                        return r
            for v in obj.values():
                r = from_obj(v, depth + 1)
                if r:
                    return r
        if isinstance(obj, list):
            for item in obj:
                r = from_obj(item, depth + 1)
                if r:
                    return r
        return None

    in_msg = tx.get("in_msg") or tx.get("inMessage") or tx.get("in_msg_body")
    if isinstance(in_msg, dict):
        r = from_obj(in_msg)
        if r:
            return r
    evs = tx.get("events") or tx.get("actions")
    if isinstance(evs, list):
        for ev in evs:
            r = from_obj(ev)
            if r:
                return r
    return from_obj(tx)


def extract_incoming_value_nano(tx: dict[str, Any]) -> int | None:
    """Сумма входящего сообщения в нанотонах, если удаётся распознать."""
    if not isinstance(tx, dict):
        return None
    in_msg = tx.get("in_msg") or tx.get("inMessage")
    if not isinstance(in_msg, dict):
        return None
    for key in ("value", "amount", "value_raw"):
        v = _as_int(in_msg.get(key))
        if v is not None and v >= 0:
            return v
    return None
