import base64
import json
import re
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

URL = "https://t.me/GetgemsNftBot/gems?startapp=L2NvbGxlY3Rpb24vRVFEMVlGcDEyQUdFZ1g2QzN1aVdoNzUxRWNSeFBabzZHdEJtSHppWTI5amNiUXpTL0VRZl90Z19naWZ0X19fX19fX19fX19fX19fX19fX19fX184U0xqX0pBQUo2S1lVbg"

def decode_startapp(url):
    u = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(u.query)
    s = qs.get("startapp", [""])[0]
    pad = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode((s + pad).encode()).decode("utf-8", "replace")

def fetch(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read()
            text = body.decode("utf-8", "replace")
            return {
                "ok": True,
                "status": r.status,
                "final_url": r.geturl(),
                "content_type": r.headers.get("content-type", ""),
                "text": text,
            }
    except urllib.error.HTTPError as e:
        body = e.read()
        text = body.decode("utf-8", "replace")
        return {
            "ok": False,
            "status": e.code,
            "final_url": url,
            "content_type": e.headers.get("content-type", "") if e.headers else "",
            "text": text,
        }
    except Exception as e:
        return {
            "ok": False,
            "status": "ERR",
            "final_url": url,
            "content_type": "",
            "text": repr(e),
        }

def title_of(html):
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(1)).strip()

def extract_addresses(text):
    friendly = re.findall(r"\b(?:EQ|UQ)[A-Za-z0-9_-]{40,90}\b", text)
    raw = re.findall(r"\b0:[A-Fa-f0-9]{64}\b", text)
    xs = []
    for x in friendly + raw:
        if x not in xs:
            xs.append(x)
    return xs[:30]

def extract_next_data(html):
    m = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html,
        re.I | re.S,
    )
    if not m:
        return None
    raw = m.group(1).strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"_parse_error": True, "_raw_start": raw[:1000]}

def walk_find(obj, keys=("name","address","raw_address","image","animation_url","attributes","traits","collection")):
    found = []
    def walk(x, path=""):
        if len(found) >= 80:
            return
        if isinstance(x, dict):
            for k, v in x.items():
                kp = f"{path}.{k}" if path else k
                if k in keys:
                    found.append((kp, v))
                walk(v, kp)
        elif isinstance(x, list):
            for i, v in enumerate(x[:30]):
                walk(v, f"{path}[{i}]")
    walk(obj)
    return found

decoded = decode_startapp(URL)
parts = [p for p in decoded.split("/") if p]

print("=== DECODED ===")
print(decoded)
print()

collection = None
raw_ref = None
if len(parts) >= 3 and parts[0] == "collection":
    collection = parts[1]
    raw_ref = parts[2]

print("collection =", collection)
print("raw_ref    =", raw_ref)
print()

urls = [
    f"https://getgems.io/collection/{collection}/{raw_ref}",
    f"https://getgems.io/nft/{raw_ref}",
    f"https://getgems.io/collection/{collection}",
]

print("=== GETGEMS WEB CHECK ===")

for i, u in enumerate(urls, 1):
    print()
    print(f"--- URL {i} ---")
    print(u)

    res = fetch(u)
    html = res["text"]

    print("status:", res["status"])
    print("final_url:", res["final_url"])
    print("content_type:", res["content_type"])
    print("length:", len(html))
    print("title:", title_of(html))
    print("contains raw_ref:", bool(raw_ref and raw_ref in html))
    print("contains __NEXT_DATA__:", "__NEXT_DATA__" in html)
    print("contains address word:", "address" in html.lower())
    print("contains attributes word:", "attributes" in html.lower())

    out = Path(f"getgems_debug_{i}.html")
    out.write_text(html, encoding="utf-8")
    print("saved:", out)

    addrs = extract_addresses(html)
    print("addresses found:", len(addrs))
    for a in addrs[:10]:
        print("  ", a)

    nd = extract_next_data(html)
    if nd is None:
        print("__NEXT_DATA__: not found")
    else:
        print("__NEXT_DATA__: found")
        print("top keys:", list(nd.keys()) if isinstance(nd, dict) else type(nd).__name__)
        hits = walk_find(nd)
        print("interesting fields:", len(hits))
        for path, val in hits[:25]:
            short = json.dumps(val, ensure_ascii=False)
            if len(short) > 300:
                short = short[:300] + "..."
            print(" ", path, "=", short)

    if raw_ref and raw_ref in html:
        pos = html.find(raw_ref)
        print("raw_ref snippet:")
        print(html[max(0, pos-300):pos+500])

print()
print("=== SUMMARY ===")
print("Если getgems_debug_1.html содержит __NEXT_DATA__ или addresses — можно писать web-resolver.")
print("Если status 403/404 или HTML пустой/без данных — Getgems mini-app ссылку без прямого NFT address нормально не вытащить этим способом.")
