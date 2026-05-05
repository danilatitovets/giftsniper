import base64
import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error

URL = "https://t.me/GetgemsNftBot/gems?startapp=L2NvbGxlY3Rpb24vRVFEMVlGcDEyQUdFZ1g2QzN1aVdoNzUxRWNSeFBabzZHdEJtSHppWTI5amNiUXpTL0VRZl90Z19naWZ0X19fX19fX19fX19fX19fX19fX19fX184U0xqX0pBQUo2S1lVbg"

def read_env_value(name):
    try:
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return ""

TONAPI_KEY = read_env_value("TONAPI_API_KEY")
TONCENTER_KEY = read_env_value("TONCENTER_API_KEY")

def get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(body)
            except Exception:
                return r.status, {"raw": body[:1000]}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            data = json.loads(body)
        except Exception:
            data = {"raw": body[:1000]}
        return e.code, data
    except Exception as e:
        return "ERR", {"error": repr(e)}

def decode_startapp(url):
    u = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(u.query)
    s = qs.get("startapp", [""])[0]
    pad = "=" * ((4 - len(s) % 4) % 4)
    raw = base64.urlsafe_b64decode((s + pad).encode()).decode("utf-8", "replace")
    return raw

decoded = decode_startapp(URL)
parts = [p for p in decoded.split("/") if p]

print("=== DECODED STARTAPP ===")
print(decoded)
print()

collection_address = None
raw_ref = None

if len(parts) >= 3 and parts[0] == "collection":
    collection_address = parts[1]
    raw_ref = parts[2]

print("collection_address =", collection_address)
print("raw_ref            =", raw_ref)
print()

if not collection_address or not raw_ref:
    print("ERROR: startapp не похож на /collection/{collection}/{ref}")
    raise SystemExit(1)

print("=== 1) Проверяем raw_ref как NFT address через TonAPI ===")
tonapi_headers = {}
if TONAPI_KEY:
    tonapi_headers["Authorization"] = "Bearer " + TONAPI_KEY

status, data = get_json(
    "https://tonapi.io/v2/nfts/" + urllib.parse.quote(raw_ref, safe=""),
    headers=tonapi_headers,
)
print("TonAPI status:", status)
print("TonAPI keys:", list(data.keys()) if isinstance(data, dict) else type(data).__name__)
print(json.dumps(data, ensure_ascii=False, indent=2)[:1000])
print()

print("=== 2) Проверяем raw_ref через Toncenter nft/items ===")
toncenter_headers = {}
if TONCENTER_KEY:
    toncenter_headers["X-API-Key"] = TONCENTER_KEY

status, data = get_json(
    "https://toncenter.com/api/v3/nft/items?address=" + urllib.parse.quote(raw_ref, safe="") + "&limit=1",
    headers=toncenter_headers,
)
print("Toncenter status:", status)
items = []
if isinstance(data, dict):
    items = data.get("nft_items") or data.get("items") or []
    if data.get("item"):
        items = [data["item"]]
print("Toncenter item count:", len(items))
print(json.dumps(data, ensure_ascii=False, indent=2)[:1500])
print()

print("=== 3) Сканируем коллекцию через TonAPI и ищем raw_ref внутри items ===")
print("Это проверит идею: raw_ref может быть не NFT address, а внутренний Getgems/Gift reference.")
print()

limit = 1000
max_pages = 5
found = []

for page in range(max_pages):
    offset = page * limit
    url = (
        "https://tonapi.io/v2/nfts/collections/"
        + urllib.parse.quote(collection_address, safe="")
        + f"/items?limit={limit}&offset={offset}"
    )

    status, data = get_json(url, headers=tonapi_headers)
    print(f"page={page+1}, offset={offset}, status={status}")

    if status != 200 or not isinstance(data, dict):
        print("bad response:", json.dumps(data, ensure_ascii=False)[:800])
        break

    batch = data.get("nft_items") or data.get("items") or []
    print("items:", len(batch))

    for item in batch:
        text = json.dumps(item, ensure_ascii=False)
        if raw_ref in text:
            found.append(item)

    if found:
        break

    if not batch or len(batch) < limit:
        break

    time.sleep(1.25)

print()
print("=== RESULT ===")
if found:
    print("FOUND MATCHES:", len(found))
    item = found[0]
    print(json.dumps(item, ensure_ascii=False, indent=2)[:5000])

    addr = item.get("address") or item.get("raw_address")
    name = item.get("name")
    metadata = item.get("metadata") or item.get("content") or {}
    if isinstance(metadata, dict):
        name = name or metadata.get("name")

    print()
    print("possible real nft address:", addr)
    print("possible name:", name)
else:
    print("Не нашли raw_ref внутри первых", max_pages * limit, "items коллекции.")
    print()
    print("Вывод:")
    print("raw_ref из Getgems startapp не находится как публичный NFT address.")
    print("Если TonAPI/Toncenter тоже не находят его напрямую, значит для таких Telegram-ссылок нужен другой способ:")
    print("- либо прямая ссылка на NFT из браузера/Getgems/Tonviewer;")
    print("- либо отдельный Getgems API/парсинг страницы;")
    print("- либо глубокий индекс всей коллекции и поиск по metadata/external_url.")
