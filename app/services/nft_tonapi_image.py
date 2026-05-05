"""Извлечение URL медиа NFT из ответа TonAPI (без загрузки файлов, без mock URL)."""

from __future__ import annotations

import ipaddress
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

_RES_SEP_RE = re.compile(r"[x×]", re.IGNORECASE)
# TonAPI / imgproxy: …/rs:fill:500:500/… или dpr:fit:…
_IMGPROXY_DIM_RE = re.compile(
    r"(?:^|/)(?:rs|dpr):(?:fill|fit|auto|force-fit):(\d+):(\d+)",
    re.IGNORECASE,
)
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif")
_VIDEO_SUFFIXES = (".mp4", ".webm", ".mov")
_GIF_SUFFIXES = (".gif",)


@dataclass
class PreviewMedia:
    url: str | None
    kind: str  # "animation" | "video" | "photo" | "none"
    mime_type: str | None
    source_field: str | None


def _normalize_ipfs_gateway(base: str) -> str:
    b = (base or "").strip()
    if not b:
        return "https://ipfs.io/ipfs/"
    return b if b.endswith("/") else b + "/"


def normalize_ipfs_http_url(url: str, *, ipfs_gateway_url: str) -> str | None:
    """Преобразует ipfs://… в HTTPS через шлюз. Остальные http(s) URL возвращает как есть."""
    if not isinstance(url, str):
        return None
    raw = url.strip()
    if not raw:
        return None
    low = raw.lower()
    if low.startswith("ipfs://"):
        rest = raw[7:].lstrip("/")
        return f"{_normalize_ipfs_gateway(ipfs_gateway_url)}{rest}"
    if low.startswith("http://") or low.startswith("https://"):
        return raw
    return None


def safe_media_url_for_log(url: str | None) -> dict[str, str | None]:
    """Хост, путь без query, расширение — без секретов в query."""
    if not url or not isinstance(url, str):
        return {"url_host": None, "url_ext": None, "path_prefix": None}
    try:
        p = urlparse(url.strip())
    except ValueError:
        return {"url_host": None, "url_ext": None, "path_prefix": None}
    host = (p.netloc or "").split("@")[-1].lower() or None
    path = p.path or ""
    ext = ""
    for suf in _VIDEO_SUFFIXES + _GIF_SUFFIXES + _IMAGE_SUFFIXES:
        if path.lower().endswith(suf):
            ext = suf
            break
    prefix = path[:120] if path else None
    return {"url_host": host, "url_ext": ext or None, "path_prefix": prefix}


def _is_blocked_scheme_or_host(url: str) -> bool:
    low = url.strip().lower()
    if low.startswith("file:") or low.startswith("javascript:") or low.startswith("data:"):
        return True
    try:
        p = urlparse(url)
    except ValueError:
        return True
    scheme = (p.scheme or "").lower()
    if scheme and scheme not in ("http", "https"):
        return True
    if not scheme:
        return False
    host = (p.hostname or "").lower()
    if not host:
        return True
    if host == "localhost" or host.endswith(".localhost"):
        return True
    if host in ("0.0.0.0", "[::1]", "::1"):
        return True
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return True
        if getattr(ip, "is_reserved", False):
            return True
    except ValueError:
        pass
    return False


def _resolve_base_uri(nft: dict[str, Any]) -> str | None:
    meta = nft.get("metadata") if isinstance(nft.get("metadata"), dict) else {}
    content = nft.get("content") if isinstance(nft.get("content"), dict) else {}
    for key in ("base_uri", "baseUri", "baseURL"):
        v = meta.get(key) or content.get(key)
        if isinstance(v, str) and v.strip():
            b = v.strip()
            if b.startswith("http://") or b.startswith("https://") or b.startswith("ipfs://"):
                return b
    uri = content.get("uri")
    if isinstance(uri, str) and uri.strip():
        u = uri.strip()
        if u.startswith("http://") or u.startswith("https://"):
            if u.endswith("/"):
                return u
            try:
                parsed = urlparse(u)
                if parsed.path and "." not in (parsed.path.rsplit("/", 1)[-1] or ""):
                    return u if u.endswith("/") else u + "/"
            except ValueError:
                pass
            return u.rsplit("/", 1)[0] + "/" if "/" in u else u
    return None


def _normalize_media_url(
    raw: object,
    *,
    ipfs_gateway_url: str,
    base_uri: str | None,
) -> str | None:
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    if s.startswith("ipfs://"):
        return normalize_ipfs_http_url(s, ipfs_gateway_url=ipfs_gateway_url)
    if s.startswith("http://") or s.startswith("https://"):
        out = normalize_ipfs_http_url(s, ipfs_gateway_url=ipfs_gateway_url)
        if out and _is_blocked_scheme_or_host(out):
            return None
        return out
    if base_uri:
        joined: str
        if base_uri.startswith("ipfs://"):
            base_h = normalize_ipfs_http_url(base_uri, ipfs_gateway_url=ipfs_gateway_url)
            if not base_h:
                return None
            joined = urljoin(base_h if base_h.endswith("/") else base_h + "/", s.lstrip("/"))
        else:
            joined = urljoin(base_uri if base_uri.endswith("/") else base_uri + "/", s.lstrip("/"))
        if joined.startswith("ipfs://"):
            joined = normalize_ipfs_http_url(joined, ipfs_gateway_url=ipfs_gateway_url) or joined
        if joined and _is_blocked_scheme_or_host(joined):
            return None
        return joined if joined.startswith("http") else None
    return None


def _mime_from_preview_dict(d: dict[str, Any]) -> str | None:
    for k in ("mime_type", "mimetype", "content_type", "type"):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    return None


def _url_candidates_from_preview_dict(d: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for k in ("url", "src", "preview_url", "medium", "big", "large", "original"):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    return out


def _photo_url_keys_preference() -> tuple[str, ...]:
    """Для одного dict превью: сначала самые крупные ассеты, не `url` по умолчанию."""
    return ("original", "large", "big", "medium", "preview_url", "url", "src")


def _is_imgproxy_rs_fill(url: str) -> bool:
    """TonAPI cache: rs:fill принудительно вписывает в прямоугольник — портит пропорции NFT."""
    if not isinstance(url, str):
        return False
    return "/rs:fill:" in url.lower()


def _infer_dimensions_from_url(url: str) -> tuple[int, int] | None:
    """Размер из URL (imgproxy TonAPI и похожие)."""
    if not isinstance(url, str):
        return None
    m = _IMGPROXY_DIM_RE.search(url)
    if not m:
        return None
    try:
        w = int(m.group(1))
        h = int(m.group(2))
        if w > 0 and h > 0:
            return w, h
    except ValueError:
        return None
    return None


def _score_static_photo_preview_entry(
    d: dict[str, Any],
    url: str,
    field_path: str,
    *,
    mime_hint: str | None,
) -> int:
    """Чем выше — тем лучше для показа. -1 если это не статичное фото."""
    kind, _ = _classify_url(field_path, url, mime_hint)
    if kind != "photo":
        return -1
    res = d.get("resolution") or d.get("size") or ""
    res_s = str(res).strip() if res is not None else ""
    norm = res_s.replace(" ", "").lower()
    if norm == "1500x1500":
        out = 15_000_000
    elif norm == "500x500":
        out = 5_000_000
    else:
        inferred = _infer_dimensions_from_url(url)
        if inferred:
            w, h = inferred
            a = w * h
            mx = max(w, h)
            if mx <= 400:
                out = 350_000 + min(a // 100, 150_000)
            else:
                out = 1_000_000 + min(a, 2_500_000)
        else:
            area = _parse_resolution_area(res_s) or 0
            if area > 0:
                out = 1_000_000 + min(area, 2_500_000)
            else:
                out = 800_000
    if _is_imgproxy_rs_fill(url):
        out = min(out, 4_500_000)
    return out


def _score_static_photo_canonical_field(field: str, url: str) -> int:
    """Приоритет канонических image из metadata/content выше маленького TonAPI preview."""
    if field == "content.preview":
        inf = _infer_dimensions_from_url(url)
        if inf:
            out = 450_000 + min(inf[0] * inf[1] // 100, 400_000)
        else:
            out = 450_000
        return min(out, 4_500_000) if _is_imgproxy_rs_fill(url) else out
    score = 6_000_000
    low = url.lower()
    if "fragment.com" in low or "getgems.io" in low or "nft.fragment" in low:
        score += 150_000
    if _is_imgproxy_rs_fill(url):
        score = min(score, 4_500_000)
    return score


def _best_preview_media_from_preview_tree(
    previews: Any,
    source_root: str,
    *,
    ipfs_gateway_url: str,
    base_uri: str | None,
) -> tuple[PreviewMedia | None, int]:
    """Лучшее статичное фото в дереве previews и его score (для сравнения с metadata/content image)."""
    best_score = -1
    best: PreviewMedia | None = None
    for label, d in _iter_preview_dicts(previews):
        if not isinstance(d, dict):
            continue
        field_base = f"{source_root}.{label}"
        mime = _mime_from_preview_dict(d)
        seen: set[str] = set()
        urls: list[str] = []
        for key in _photo_url_keys_preference():
            raw = d.get(key)
            if not isinstance(raw, str) or not raw.strip():
                continue
            u = _normalize_media_url(raw.strip(), ipfs_gateway_url=ipfs_gateway_url, base_uri=base_uri)
            if u and u not in seen:
                seen.add(u)
                urls.append(u)
        for cand in _url_candidates_from_preview_dict(d):
            u = _normalize_media_url(cand, ipfs_gateway_url=ipfs_gateway_url, base_uri=base_uri)
            if u and u not in seen:
                seen.add(u)
                urls.append(u)
        for u in urls:
            sc = _score_static_photo_preview_entry(d, u, field_base, mime_hint=mime)
            if sc <= best_score:
                continue
            kind, mh = _classify_url(field_base, u, mime)
            if kind != "photo":
                continue
            best_score = sc
            best = PreviewMedia(url=u, kind="photo", mime_type=mh, source_field=field_base)
    return best, best_score


def _iter_preview_dicts(previews: Any) -> list[tuple[str, dict[str, Any]]]:
    """Плоский список (source_label, dict) для обхода."""
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(previews, list):
        for i, p in enumerate(previews):
            if isinstance(p, dict):
                found.append((f"previews[{i}]", p))
    elif isinstance(previews, dict):
        for k, v in previews.items():
            if isinstance(v, dict):
                found.append((f"previews.{k}", v))
            elif isinstance(v, str) and v.strip():
                found.append((f"previews.{k}", {"url": v}))
    return found


def _classify_url(field: str, url: str, mime_hint: str | None) -> tuple[str, str | None]:
    low = url.lower()
    mh = (mime_hint or "").lower()
    if mh.startswith("video/"):
        return "video", mime_hint
    if mh == "image/gif":
        return "animation", mime_hint
    if mh.startswith("image/"):
        return "photo", mime_hint
    if any(low.endswith(s) for s in _VIDEO_SUFFIXES):
        return "video", "video/mp4" if low.endswith(".mp4") else ("video/webm" if low.endswith(".webm") else "video/quicktime")
    if any(low.endswith(s) for s in _GIF_SUFFIXES):
        return "animation", "image/gif"
    if any(low.endswith(s) for s in (".png", ".jpg", ".jpeg", ".webp")):
        return "photo", mime_hint
    lf = field.lower()
    if "video" in lf:
        return "video", mime_hint
    if "animation" in lf:
        return "animation", mime_hint
    return "photo", mime_hint


def _parse_resolution_area(res: object) -> int | None:
    if not isinstance(res, str):
        return None
    parts = _RES_SEP_RE.split(res.strip(), maxsplit=1)
    if len(parts) != 2:
        return None
    try:
        w = int(parts[0].strip())
        h = int(parts[1].strip())
        if w > 0 and h > 0:
            return w * h
    except ValueError:
        return None
    return None


def _preview_best_and_500(previews: list[Any], *, ipfs_gateway_url: str) -> tuple[str | None, str | None]:
    url_1500: str | None = None
    url_500: str | None = None
    best_other_url: str | None = None
    best_other_area = -1
    for p in previews:
        if not isinstance(p, dict):
            continue
        url = _normalize_media_url(p.get("url"), ipfs_gateway_url=ipfs_gateway_url, base_uri=None)
        if not url:
            continue
        res = p.get("resolution") or p.get("size") or ""
        res_s = str(res).strip() if res is not None else ""
        norm = res_s.replace(" ", "").lower()
        if norm == "1500x1500":
            url_1500 = url_1500 or url
        elif norm == "500x500":
            url_500 = url_500 or url
        else:
            area = _parse_resolution_area(res_s) or 0
            if area > best_other_area:
                best_other_area = area
                best_other_url = url
            elif area == best_other_area and area == 0 and best_other_url is None:
                best_other_url = url
    if url_1500:
        return url_1500, url_500
    if url_500:
        return url_500, None
    return best_other_url, None


def extract_nft_media_urls(
    nft_item: dict[str, Any],
    *,
    ipfs_gateway_url: str = "https://ipfs.io/ipfs/",
) -> tuple[str | None, str | None]:
    """
    (image_url, preview_url): основной URL для показа и необязательный превью 500×500.
    preview_url заполняется только если отличается от image_url.
    """
    if not isinstance(nft_item, dict):
        return None, None
    gw = ipfs_gateway_url or "https://ipfs.io/ipfs/"

    previews = nft_item.get("previews")
    if isinstance(previews, list) and previews:
        best_p, u500 = _preview_best_and_500(previews, ipfs_gateway_url=gw)
        if best_p:
            prev_secondary = u500 if u500 and u500 != best_p else None
            return best_p, prev_secondary

    base = _resolve_base_uri(nft_item)
    for key in ("image", "image_url"):
        u = _normalize_media_url(nft_item.get(key), ipfs_gateway_url=gw, base_uri=base)
        if u:
            return u, None

    meta = nft_item.get("metadata") if isinstance(nft_item.get("metadata"), dict) else {}
    for key in ("image", "image_url"):
        u = _normalize_media_url(meta.get(key), ipfs_gateway_url=gw, base_uri=base)
        if u:
            return u, None

    content = nft_item.get("content") if isinstance(nft_item.get("content"), dict) else {}
    u_img = _normalize_media_url(content.get("image"), ipfs_gateway_url=gw, base_uri=base)
    if u_img:
        return u_img, None

    uri_raw = content.get("uri")
    if isinstance(uri_raw, str):
        uri = _normalize_media_url(uri_raw, ipfs_gateway_url=gw, base_uri=None)
        if uri:
            try:
                path = urlparse(uri).path.lower()
            except ValueError:
                path = ""
            if any(path.endswith(suf) for suf in _IMAGE_SUFFIXES):
                return uri, None

    prev = content.get("preview")
    if isinstance(prev, dict):
        prev = prev.get("url")
    u_prev = _normalize_media_url(prev, ipfs_gateway_url=gw, base_uri=base)
    if u_prev:
        return u_prev, None

    return None, None


def extract_nft_image_url(
    nft_item: dict[str, Any],
    *,
    ipfs_gateway_url: str = "https://ipfs.io/ipfs/",
) -> str | None:
    """Основной URL изображения NFT по правилам TonAPI (previews → metadata → content)."""
    primary, _ = extract_nft_media_urls(nft_item, ipfs_gateway_url=ipfs_gateway_url)
    return primary


def _unwrap_media_ref(raw: object) -> str | None:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, dict):
        for k in ("url", "src", "permalink", "link"):
            v = raw.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def _try_field(
    nft: dict[str, Any],
    field: str,
    raw: object,
    *,
    ipfs_gateway_url: str,
    base_uri: str | None,
) -> PreviewMedia | None:
    s = _unwrap_media_ref(raw)
    if not s:
        return None
    u = _normalize_media_url(s, ipfs_gateway_url=ipfs_gateway_url, base_uri=base_uri)
    if not u:
        return None
    kind, mime = _classify_url(field, u, None)
    return PreviewMedia(url=u, kind=kind, mime_type=mime, source_field=field)


def _scan_previews_for_kind(
    previews: Any,
    source_root: str,
    *,
    ipfs_gateway_url: str,
    base_uri: str | None,
    want: str,
) -> PreviewMedia | None:
    """
    want: "video" — только video/* или расширения видео;
          "animation" — gif / image/gif;
          "photo" — изображения (не video/gif).
    """
    for label, d in _iter_preview_dicts(previews):
        mime = _mime_from_preview_dict(d)
        field = f"{source_root}.{label}"
        for cand in _url_candidates_from_preview_dict(d):
            u = _normalize_media_url(cand, ipfs_gateway_url=ipfs_gateway_url, base_uri=base_uri)
            if not u:
                continue
            kind, mh = _classify_url(field, u, mime)
            if want == "video" and kind == "video":
                return PreviewMedia(url=u, kind="video", mime_type=mh, source_field=field)
            if want == "animation" and kind == "animation":
                return PreviewMedia(url=u, kind="animation", mime_type=mh or "image/gif", source_field=field)
            if want == "photo" and kind == "photo":
                return PreviewMedia(url=u, kind="photo", mime_type=mh, source_field=field)
    return None


def _log_extraction(nft: dict[str, Any], result: PreviewMedia) -> None:
    meta = nft.get("metadata") if isinstance(nft.get("metadata"), dict) else {}
    name = (meta.get("name") or nft.get("name") or "")[:200] or "?"
    if result.kind == "none" or not result.url:
        top = sorted(str(k) for k in nft.keys())[:40]
        content = nft.get("content") if isinstance(nft.get("content"), dict) else {}
        ckeys = sorted(str(k) for k in content.keys())[:40] if isinstance(content, dict) else []
        mkeys = sorted(str(k) for k in meta.keys())[:40]
        logger.debug(
            "nft_preview_media none name=%r top_keys=%s content_keys=%s metadata_keys=%s",
            name,
            top,
            ckeys,
            mkeys,
        )
        return
    safe = safe_media_url_for_log(result.url)
    logger.debug(
        "nft_preview_media name=%r kind=%s source_field=%r host=%s ext=%s",
        name,
        result.kind,
        result.source_field,
        safe.get("url_host"),
        safe.get("url_ext"),
    )


def extract_nft_preview_media(
    nft: dict[str, Any],
    *,
    ipfs_gateway_url: str = "https://ipfs.io/ipfs/",
) -> PreviewMedia:
    if not isinstance(nft, dict):
        return PreviewMedia(url=None, kind="none", mime_type=None, source_field=None)
    gw = ipfs_gateway_url or "https://ipfs.io/ipfs/"
    base = _resolve_base_uri(nft)
    content = nft.get("content") if isinstance(nft.get("content"), dict) else {}
    meta = nft.get("metadata") if isinstance(nft.get("metadata"), dict) else {}

    string_anim_order: list[tuple[str, object]] = [
        ("animation_url", nft.get("animation_url")),
        ("animation", nft.get("animation")),
        ("video", nft.get("video")),
        ("video_url", nft.get("video_url")),
        ("content.animation_url", content.get("animation_url")),
        ("content.animation", content.get("animation")),
        ("content.video", content.get("video")),
        ("content.video_url", content.get("video_url")),
        ("metadata.animation_url", meta.get("animation_url")),
        ("metadata.animation", meta.get("animation")),
        ("metadata.video", meta.get("video")),
        ("metadata.video_url", meta.get("video_url")),
    ]

    for field, raw in string_anim_order:
        m = _try_field(nft, field, raw, ipfs_gateway_url=gw, base_uri=base)
        if m:
            _log_extraction(nft, m)
            return m

    for root_name, pv in (
        ("previews", nft.get("previews")),
        ("content.previews", content.get("previews")),
        ("metadata.previews", meta.get("previews")),
    ):
        m = _scan_previews_for_kind(pv, root_name, ipfs_gateway_url=gw, base_uri=base, want="video")
        if m:
            _log_extraction(nft, m)
            return m
    for root_name, pv in (
        ("previews", nft.get("previews")),
        ("content.previews", content.get("previews")),
        ("metadata.previews", meta.get("previews")),
    ):
        m = _scan_previews_for_kind(pv, root_name, ipfs_gateway_url=gw, base_uri=base, want="animation")
        if m:
            _log_extraction(nft, m)
            return m

    best_photo: PreviewMedia | None = None
    best_photo_score = -1
    for root_name, pv in (
        ("previews", nft.get("previews")),
        ("content.previews", content.get("previews")),
        ("metadata.previews", meta.get("previews")),
    ):
        m, sc = _best_preview_media_from_preview_tree(pv, root_name, ipfs_gateway_url=gw, base_uri=base)
        if m and sc > best_photo_score:
            best_photo_score = sc
            best_photo = m

    prev_box = content.get("preview")
    prev_url = (prev_box.get("url") if isinstance(prev_box, dict) else prev_box) if prev_box else None
    image_order: list[tuple[str, object]] = [
        ("image", nft.get("image")),
        ("image_url", nft.get("image_url")),
        ("content.image", content.get("image")),
        ("content.image_url", content.get("image_url")),
        ("content.preview", prev_url),
        ("metadata.image", meta.get("image")),
        ("metadata.image_url", meta.get("image_url")),
    ]
    for field, raw in image_order:
        m = _try_field(nft, field, raw, ipfs_gateway_url=gw, base_uri=base)
        if not m or m.kind != "photo" or not m.url:
            continue
        sc = _score_static_photo_canonical_field(field, m.url)
        if sc > best_photo_score:
            best_photo_score = sc
            best_photo = m

    if best_photo:
        _log_extraction(nft, best_photo)
        return best_photo

    out = PreviewMedia(url=None, kind="none", mime_type=None, source_field=None)
    _log_extraction(nft, out)
    return out
