import json
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
STORAGE = ROOT / "storage"
JOBS_DIR = STORAGE / "jobs"
UPLOADS_DIR = STORAGE / "uploads"

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")

def ensure_dirs():
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def run_cmd(cmd: List[str], cwd: Optional[Path] = None) -> None:
    p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stdout[-4000:])

def ffprobe_metrics(path: Path) -> Dict[str, Any]:
    try:
        cmd = [
            FFPROBE, "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,avg_frame_rate",
            "-show_entries", "format=duration",
            "-of", "json",
            str(path)
        ]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if p.returncode != 0:
            return {}
        j = json.loads(p.stdout)
        fmt = (j.get("format") or {})
        st = ((j.get("streams") or [{}])[0] or {})
        return {
            "duration_s": float(fmt.get("duration") or 0),
            "width": st.get("width"),
            "height": st.get("height"),
            "r_frame_rate": st.get("r_frame_rate"),
            "avg_frame_rate": st.get("avg_frame_rate"),
        }
    except Exception:
        return {}

def job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id

def job_path(job_id: str) -> Path:
    return job_dir(job_id) / "job.json"

def read_job(job_id: str) -> Dict[str, Any]:
    p = job_path(job_id)
    if not p.exists():
        raise HTTPException(404, "job not found")
    return json.loads(p.read_text(encoding="utf-8"))

def write_job(job_id: str, data: Dict[str, Any]) -> None:
    d = job_dir(job_id)
    d.mkdir(parents=True, exist_ok=True)
    job_path(job_id).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

class JobCreate(BaseModel):
    profile_id: str
    mode: str
    prompt_or_script: str = ""
    inputs: List[str] = Field(default_factory=list)
    params: Dict[str, Any] = Field(default_factory=dict)

app = FastAPI(title="MinhaIALAST", version="4.0")

ensure_dirs()
WEB_DIR = ROOT / "apps" / "web"
CONFIG_DIR = ROOT / "config"

if WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
if CONFIG_DIR.exists():
    app.mount("/config", StaticFiles(directory=str(CONFIG_DIR)), name="config")

@app.get("/", response_class=HTMLResponse)
def root():
    idx = WEB_DIR / "index.html"
    if idx.exists():
        return HTMLResponse(idx.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>UI missing</h1>")

@app.get("/health")
def health():
    return {"ok": True, "time": now_iso()}

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    ensure_dirs()
    ext = Path(file.filename or "file.bin").suffix
    fid = uuid.uuid4().hex
    out = UPLOADS_DIR / f"{fid}{ext}"
    out.write_bytes(await file.read())
    return {"path": str(out.relative_to(ROOT)).replace("\\", "/"), "filename": file.filename, "bytes": out.stat().st_size}

@app.get("/jobs")
def jobs(limit: int = 50):
    ensure_dirs()
    items = []
    for p in sorted(JOBS_DIR.glob("*/job.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
        try:
            items.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return {"items": items}

@app.get("/jobs/{job_id}")
def job_get(job_id: str):
    return read_job(job_id)

@app.get("/files/{job_id}/{name}")
def file_get(job_id: str, name: str):
    target = (job_dir(job_id) / name).resolve()
    base = job_dir(job_id).resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(400, "invalid path")
    if not target.exists():
        raise HTTPException(404, "file not found")
    return FileResponse(str(target))

# ---------- generators / editors ----------
def _mock_text_to_video(out_mp4: Path, prompt: str, dur: float, fps: int, w: int, h: int) -> None:
    base = [FFMPEG, "-y", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate={fps}", "-t", str(dur)]
    safe = (prompt or "MOCK").replace("\n", " ").replace("'", r"\'").replace(":", r"\:")
    draw = f"drawtext=text='{safe}':x=20:y=20:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.5"
    cmd = base + ["-vf", draw, "-pix_fmt", "yuv420p", str(out_mp4)]
    try:
        run_cmd(cmd)
    except Exception:
        run_cmd(base + ["-pix_fmt", "yuv420p", str(out_mp4)])

def _ff_trim(src: Path, out_mp4: Path, start_s: float, end_s: float) -> None:
    dur = max(0.1, end_s - start_s)
    cmd = [FFMPEG, "-y", "-ss", str(start_s), "-i", str(src), "-t", str(dur), "-c", "copy", str(out_mp4)]
    try:
        run_cmd(cmd)
    except Exception:
        cmd = [FFMPEG, "-y", "-ss", str(start_s), "-i", str(src), "-t", str(dur),
               "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", str(out_mp4)]
        run_cmd(cmd)

def _ff_resize(src: Path, out_mp4: Path, w: int, h: int) -> None:
    cmd = [FFMPEG, "-y", "-i", str(src), "-vf", f"scale={w}:{h}", "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", str(out_mp4)]
    run_cmd(cmd)

def _ff_overlay_text(src: Path, out_mp4: Path, text: str, x: int, y: int) -> None:
    safe = (text or "").replace("\n", " ").replace("'", r"\'").replace(":", r"\:")
    draw = f"drawtext=text='{safe}':x={x}:y={y}:fontsize=36:fontcolor=white:box=1:boxcolor=black@0.5"
    cmd = [FFMPEG, "-y", "-i", str(src), "-vf", draw, "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", str(out_mp4)]
    try:
        run_cmd(cmd)
    except Exception:
        cmd2 = [FFMPEG, "-y", "-i", str(src), "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", str(out_mp4)]
        run_cmd(cmd2)

def _ff_add_music(video: Path, audio: Path, out_mp4: Path, volume: float = 0.6) -> None:
    cmd = [
        FFMPEG, "-y",
        "-i", str(video),
        "-i", str(audio),
        "-filter_complex", f"[1:a]volume={volume}[a1]",
        "-map", "0:v:0", "-map", "[a1]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(out_mp4)
    ]
    run_cmd(cmd)

def _ff_burn_srt(video: Path, srt: Path, out_mp4: Path) -> None:
    s = str(srt).replace("\\", "/")
    cmd = [FFMPEG, "-y", "-i", str(video), "-vf", f"subtitles={s}", "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", str(out_mp4)]
    run_cmd(cmd)

def _ff_concat(videos: List[Path], out_mp4: Path) -> None:
    tmp = out_mp4.parent / "concat.txt"
    lines = []
    for v in videos:
        lines.append(f"file '{str(v).replace("'", "'\\''")}'")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cmd = [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(tmp), "-c", "copy", str(out_mp4)]
    try:
        run_cmd(cmd)
    except Exception:
        cmd = [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(tmp),
               "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", str(out_mp4)]
        run_cmd(cmd)

def _ff_slideshow(images: List[Path], out_mp4: Path, dur_each: float, fps: int, w: int, h: int) -> None:
    segs = []
    for i, img in enumerate(images):
        seg = out_mp4.parent / f"seg_{i:03d}.mp4"
        cmd = [FFMPEG, "-y", "-loop", "1", "-t", str(dur_each), "-i", str(img),
               "-vf", f"scale={w}:{h},fps={fps},format=yuv420p",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", str(seg)]
        run_cmd(cmd)
        segs.append(seg)
    _ff_concat(segs, out_mp4)

def _ff_speed(src: Path, out_mp4: Path, speed: float) -> None:
    if speed <= 0:
        raise RuntimeError("speed must be > 0")
    vfilter = f"setpts=PTS/{speed}"
    remaining = speed
    atempos = []
    while remaining > 2.0:
        atempos.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        atempos.append("atempo=0.5")
        remaining /= 0.5
    atempos.append(f"atempo={remaining}")
    afilter = ",".join(atempos)
    cmd = [FFMPEG, "-y", "-i", str(src), "-filter_complex",
           f"[0:v]{vfilter}[v];[0:a]{afilter}[a]",
           "-map","[v]","-map","[a]",
           "-c:v","libx264","-c:a","aac","-pix_fmt","yuv420p",
           str(out_mp4)]
    run_cmd(cmd)

def process_job(job_id: str) -> None:
    job = read_job(job_id)
    try:
        mode = job.get("mode")
        params = job.get("params") or {}
        prompt = job.get("prompt_or_script") or ""
        inputs = job.get("inputs") or []

        out_dir = job_dir(job_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_mp4 = out_dir / "final.mp4"

        aspect = str(params.get("aspect", "16:9"))
        fps = int(params.get("fps", 24))
        dur = float(params.get("duration", 3))
        w, h = (1280, 720)
        if aspect == "9:16":
            w, h = (720, 1280)
        elif aspect == "1:1":
            w, h = (1024, 1024)

        if mode == "mock_text_to_video":
            _mock_text_to_video(out_mp4, prompt, dur, fps, w, h)

        elif mode == "mock_voiceover":
            _mock_text_to_video(out_mp4, "VOZ (placeholder): " + prompt, dur, fps, w, h)

        elif mode == "ffmpeg_trim":
            if len(inputs) < 1: raise RuntimeError("ffmpeg_trim requires 1 video input")
            _ff_trim(ROOT / inputs[0], out_mp4, float(params.get("start_s", 0)), float(params.get("end_s", 3)))

        elif mode == "ffmpeg_resize":
            if len(inputs) < 1: raise RuntimeError("ffmpeg_resize requires 1 video input")
            _ff_resize(ROOT / inputs[0], out_mp4, int(params.get("width", w)), int(params.get("height", h)))

        elif mode == "ffmpeg_overlay_text":
            if len(inputs) < 1: raise RuntimeError("ffmpeg_overlay_text requires 1 video input")
            _ff_overlay_text(ROOT / inputs[0], out_mp4, str(params.get("text", prompt) or prompt), int(params.get("x", 20)), int(params.get("y", 20)))

        elif mode == "ffmpeg_add_music":
            if len(inputs) < 2: raise RuntimeError("ffmpeg_add_music requires video + audio")
            _ff_add_music(ROOT / inputs[0], ROOT / inputs[1], out_mp4, float(params.get("volume", 0.6)))

        elif mode == "ffmpeg_burn_srt":
            if len(inputs) < 2: raise RuntimeError("ffmpeg_burn_srt requires video + srt")
            _ff_burn_srt(ROOT / inputs[0], ROOT / inputs[1], out_mp4)

        elif mode == "ffmpeg_concat":
            if len(inputs) < 2: raise RuntimeError("ffmpeg_concat requires 2+ videos")
            _ff_concat([ROOT / p for p in inputs], out_mp4)

        elif mode == "ffmpeg_slideshow":
            if len(inputs) < 1: raise RuntimeError("ffmpeg_slideshow requires 1+ images")
            _ff_slideshow([ROOT / p for p in inputs], out_mp4, float(params.get("dur_each", 2.0)), fps, w, h)

        elif mode == "ffmpeg_speed":
            if len(inputs) < 1: raise RuntimeError("ffmpeg_speed requires 1 video input")
            _ff_speed(ROOT / inputs[0], out_mp4, float(params.get("speed", 1.25)))

        else:
            raise RuntimeError(f"Unknown mode: {mode}")

        outputs = {"final": f"/files/{job_id}/final.mp4"}
        job.update({
            "status": "succeeded",
            "progress": 1.0,
            "outputs": outputs,
            "metrics": ffprobe_metrics(out_mp4),
            "updated_at": now_iso(),
        })
        write_job(job_id, job)
    except Exception as e:
        job.update({
            "status": "failed",
            "progress": 1.0,
            "error": str(e),
            "updated_at": now_iso(),
        })
        write_job(job_id, job)

@app.post("/jobs")
def jobs_create(req: JobCreate):
    ensure_dirs()
    job_id = uuid.uuid4().hex
    job = req.model_dump()
    job.update({
        "id": job_id,
        "status": "queued",
        "progress": 0.0,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })
    write_job(job_id, job)

    t = threading.Thread(target=process_job, args=(job_id,), daemon=True)
    t.start()

    return {"id": job_id, "status": "queued", "job": job}

# -------------------------
# Assets import (CDC PHIL / Wikimedia Commons)
# -------------------------
import re
from urllib.parse import urljoin, urlencode
from urllib.request import Request, urlopen

ASSETS_DIR = STORAGE / "assets"
ASSETS_FILES = ASSETS_DIR / "files"
ASSETS_MANIFEST = ASSETS_DIR / "manifest.json"
_ASSET_LOCK = threading.Lock()
UA = "Mozilla/5.0 (compatible; MinhaIALAST/4.0; +local)"

def _asset_manifest() -> Dict[str, Any]:
    if not ASSETS_MANIFEST.exists():
        return {"items": []}
    return json.loads(ASSETS_MANIFEST.read_text(encoding="utf-8"))

def _asset_save(m: Dict[str, Any]) -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_FILES.mkdir(parents=True, exist_ok=True)
    ASSETS_MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def _http_get(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=30) as r:
        return r.read()

def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_http_get(url))

def _add_asset(item: Dict[str, Any]) -> Dict[str, Any]:
    with _ASSET_LOCK:
        m = _asset_manifest()
        items = m.get("items", []) or []
        items.insert(0, item)
        m["items"] = items
        _asset_save(m)
    return item

@app.get("/assets")
def assets_list(limit: int = 200):
    m = _asset_manifest()
    return {"items": (m.get("items", []) or [])[:limit]}

class ImportCdcReq(BaseModel):
    pid: int

@app.post("/assets/import/cdc_phil")
def assets_import_cdc(req: ImportCdcReq):
    pid = int(req.pid)
    page_url = f"https://phil.cdc.gov/Details.aspx?pid={pid}"
    html = _http_get(page_url).decode("utf-8", errors="ignore")

    patterns = [
        r'href="([^"]+)"[^>]*>\s*Click here for high resolution image',
        r'href="([^"]+)"[^>]*>\s*Clique aqui para ver a imagem em alta resolução',
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
        raise HTTPException(400, "Não consegui resolver o link do arquivo no PHIL automaticamente.")

    file_url = urljoin(page_url, href)
    ext = Path(file_url.split("?")[0]).suffix.lower() or ".jpg"
    asset_id = uuid.uuid4().hex
    filename = f"cdc_phil_{pid}_{asset_id}{ext}"
    dest = ASSETS_FILES / filename
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
        "created_at": now_iso(),
        "tags": []
    }
    return _add_asset(item)

class ImportCommonsReq(BaseModel):
    category: str
    limit: int = 30

def _commons_api(params: dict) -> dict:
    base = "https://commons.wikimedia.org/w/api.php"
    url = base + "?" + urlencode(params)
    data = _http_get(url).decode("utf-8", errors="ignore")
    return json.loads(data)

@app.post("/assets/import/commons_category")
def assets_import_commons(req: ImportCommonsReq):
    category = req.category
    limit = int(req.limit or 30)
    if not str(category).lower().startswith("category:"):
        category = "Category:" + str(category)

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
        dest = ASSETS_FILES / filename
        _download(file_url, dest)

        def mval(k):
            return (meta.get(k, {}) or {}).get("value")

        item = {
            "id": asset_id,
            "source": "wikimedia_commons",
            "source_id": title,
            "title": title,
            "original_page": "https://commons.wikimedia.org/wiki/" + title.replace(" ", "_"),
            "original_file": file_url,
            "license": mval("LicenseShortName") or "See original page",
            "license_url": mval("LicenseUrl"),
            "credit": mval("Credit") or mval("Artist") or "See original page",
            "local_file": str(dest.relative_to(ROOT)).replace("\\", "/"),
            "created_at": now_iso(),
            "tags": [category]
        }
        _add_asset(item)
        out_items.append(item)
        imported += 1

    return {"category": category, "imported": imported, "items": out_items}

@app.get("/assets/file/{asset_id}")
def assets_file(asset_id: str):
    m = _asset_manifest()
    items = m.get("items", []) or []
    hit = next((x for x in items if x.get("id") == asset_id), None)
    if not hit:
        raise HTTPException(404, "asset not found")
    rel = hit.get("local_file")
    if not rel:
        raise HTTPException(404, "asset file missing")
    target = (ROOT / rel).resolve()
    base = ASSETS_FILES.resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(400, "invalid path")
    if not target.exists():
        raise HTTPException(404, "file not found")
    return FileResponse(str(target))
