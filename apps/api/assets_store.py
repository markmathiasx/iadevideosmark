import json, threading, time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = ROOT / "storage" / "assets"
FILES_DIR = ASSETS_DIR / "files"
MANIFEST = ASSETS_DIR / "manifest.json"
_LOCK = threading.Lock()

def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def load_manifest() -> Dict[str, Any]:
    if not MANIFEST.exists():
        return {"items": []}
    return json.loads(MANIFEST.read_text(encoding="utf-8"))

def save_manifest(m: Dict[str, Any]) -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")

def add_item(item: Dict[str, Any]) -> Dict[str, Any]:
    with _LOCK:
        m = load_manifest()
        items: List[Dict[str, Any]] = m.get("items", []) or []
        items.insert(0, item)
        m["items"] = items
        save_manifest(m)
    return item

def list_items(limit: int = 200) -> List[Dict[str, Any]]:
    m = load_manifest()
    return (m.get("items", []) or [])[:limit]
