import json, re, time, uuid
from pathlib import Path
from urllib.parse import urljoin, urlencode
from urllib.request import Request, urlopen

from .assets_store import ROOT, FILES_DIR, add_item

UA = "Mozilla/5.0 (compatible; MinhaIALAST/1.0; +local)"

def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def _http_get(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=30) as r:
        return r.read()

def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_http_get(url))

def import_cdc_phil(pid: int) -> dict:
    page_url = f"https://phil.cdc.gov/Details.aspx?pid={pid}"
    html = _http_get(page_url).decode("utf-8", errors="ignore")
    patterns = [
        r'href="([^"]+)"[^>]*>\s*Click here for high resolution image',
        r'href="([^"]+)"[^>]*>\s*Click here for high resolution',
        r'href="([^"]+)"[^>]*>\s*Clique aqui.*alta resolu',
    ]
    href = None
    for p in patterns:
        m = re.search(p, html, flags=re.IGNORECASE)
        if m:
            href = m.group(1)
            break
    if not href:
        m = re.search(r'href="([^"]+\.(?:jpg|jpeg|png))"', html, flags=re.IGNORECASE)
        if m:
            href = m.group(1)
    if not href:
        raise RuntimeError("CDC PHIL: não consegui resolver o link automaticamente. Copie o link direto do arquivo na página PHIL.")
    file_url = urljoin(page_url, href)
    ext = Path(file_url.split("?")[0]).suffix.lower() or ".jpg"
    asset_id = uuid.uuid4().hex
    filename = f"cdc_phil_{pid}_{asset_id}{ext}"
    dest = FILES_DIR / filename
    _download(file_url, dest)
    item = {
        "id": asset_id,
        "source": "cdc_phil",
        "source_id": str(pid),
        "title": f"CDC PHIL pid={pid}",
        "original_page": page_url,
        "original_file": file_url,
        "license": "Public Domain (ver ficha do asset no PHIL)",
        "credit": "CDC / PHIL (ver ficha do asset)",
        "local_file": str(dest.relative_to(ROOT)).replace("\\", "/"),
        "created_at": _now_iso(),
        "tags": ["cdc_phil"]
    }
    return add_item(item)

def _commons_api(params: dict) -> dict:
    base = "https://commons.wikimedia.org/w/api.php"
    url = base + "?" + urlencode(params)
    data = _http_get(url).decode("utf-8", errors="ignore")
    return json.loads(data)

def import_commons_category(category: str, limit: int = 30) -> dict:
    if not category.lower().startswith("category:"):
        category = "Category:" + category
    cm = _commons_api({
        "action": "query",
        "list": "categorymembers",
        "cmtitle": category,
        "cmtype": "file",
        "cmlimit": str(min(max(limit, 1), 200)),
        "format": "json"
    })
    members = (cm.get("query", {}).get("categorymembers", []) or [])
    imported = 0
    out_items = []
    for it in members:
        title = it.get("title")
        if not title or not title.lower().startswith("file:"):
            continue
        info = _commons_api({
            "action": "query",
            "prop": "imageinfo",
            "titles": title,
            "iiprop": "url|extmetadata",
            "format": "json"
        })
        pages = (info.get("query", {}).get("pages", {}) or {})
        page = next(iter(pages.values()), {})
        ii = (page.get("imageinfo", []) or [])
        if not ii:
            continue
        img = ii[0]
        file_url = img.get("url")
        meta = (img.get("extmetadata", {}) or {})
        if not file_url:
            continue
        ext = Path(file_url).suffix.lower() or ".jpg"
        asset_id = uuid.uuid4().hex
        filename = f"commons_{asset_id}{ext}"
        dest = FILES_DIR / filename
        _download(file_url, dest)
        lic_short = (meta.get("LicenseShortName", {}) or {}).get("value")
        lic_url = (meta.get("LicenseUrl", {}) or {}).get("value")
        artist = (meta.get("Artist", {}) or {}).get("value")
        credit = (meta.get("Credit", {}) or {}).get("value")
        item = {
            "id": asset_id,
            "source": "wikimedia_commons",
            "source_id": title,
            "title": title,
            "original_page": "https://commons.wikimedia.org/wiki/" + title.replace(" ", "_"),
            "original_file": file_url,
            "license": lic_short or "See original page",
            "license_url": lic_url,
            "credit": credit or artist or "See original page",
            "local_file": str(dest.relative_to(ROOT)).replace("\\", "/"),
            "created_at": _now_iso(),
            "tags": [category]
        }
        add_item(item)
        out_items.append(item)
        imported += 1
    return {"category": category, "imported": imported, "items": out_items}
