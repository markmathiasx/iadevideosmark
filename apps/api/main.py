import os, re, json, uuid, time, sqlite3, threading, subprocess, shutil, tempfile
from pathlib import Path
from typing import Any, Dict, Optional, List

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
OUTPUTS_DIR = ROOT / "outputs"
UPLOADS_DIR = OUTPUTS_DIR / "_uploads"
STORAGE_DIR = ROOT / "storage"
LOGS_DIR = STORAGE_DIR / "logs"
DB_PATH = Path(__file__).resolve().parent / "data" / "jobs.db"

def where_exe(name: str) -> Optional[str]:
    try:
        if os.name == "nt":
            out = subprocess.check_output(["where.exe", name], stderr=subprocess.STDOUT, text=True)
        else:
            out = subprocess.check_output(["which", name], stderr=subprocess.STDOUT, text=True)
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        return lines[0] if lines else None
    except Exception:
        return None

FFMPEG = os.environ.get("FFMPEG_PATH") or where_exe("ffmpeg")
FFPROBE = os.environ.get("FFPROBE_PATH") or where_exe("ffprobe")

def ensure_dirs():
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    (Path(__file__).resolve().parent / "data").mkdir(parents=True, exist_ok=True)
    (ROOT / "storage" / "assets" / "files").mkdir(parents=True, exist_ok=True)

def db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    ensure_dirs()
    conn = db()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS jobs ("
        "id TEXT PRIMARY KEY, "
        "created_at TEXT, "
        "profile_id TEXT, "
        "mode TEXT, "
        "status TEXT, "
        "progress REAL, "
        "error TEXT, "
        "inputs_json TEXT, "
        "params_json TEXT, "
        "outputs_json TEXT, "
        "metrics_json TEXT, "
        "content_sensitive INTEGER, "
        "consent INTEGER)"
    )
    conn.commit()
    conn.close()

def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def log_line(job_id: str, message: str):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    p = LOGS_DIR / f"job-{job_id}.log"
    with p.open("a", encoding="utf-8") as f:
        f.write(message + "\n")

def write_job(job_id: str, **fields):
    conn = db()
    sets = []
    vals = []
    for k, v in fields.items():
        sets.append(f"{k}=?")
        vals.append(v)
    vals.append(job_id)
    conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id=?", vals)
    conn.commit()
    conn.close()

def _decode_job_row(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    for k in ["inputs_json", "params_json", "outputs_json", "metrics_json"]:
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except Exception:
                pass
        else:
            d[k] = None
    return d

def get_job(job_id: str) -> Dict[str, Any]:
    conn = db()
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    return _decode_job_row(row)

def list_jobs(limit: int = 100):
    conn = db()
    rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [_decode_job_row(r) for r in rows]

def ffprobe_metrics(path: Path) -> Dict[str, Any]:
    if not FFPROBE:
        return {"ffprobe": "missing"}
    try:
        cmd = [
            FFPROBE, "-v", "error",
            "-show_entries", "format=duration,bit_rate,size:stream=codec_name,codec_type,width,height,r_frame_rate",
            "-of", "json", str(path)
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        j = json.loads(out)
        streams = j.get("streams", [])
        fmt = j.get("format", {})
        v = next((s for s in streams if s.get("codec_type") == "video"), None)
        a = next((s for s in streams if s.get("codec_type") == "audio"), None)

        def fps_from_rfr(r):
            try:
                num, den = r.split("/")
                return float(num) / float(den)
            except Exception:
                return None

        return {
            "video_codec": v.get("codec_name") if v else None,
            "audio_codec": a.get("codec_name") if a else None,
            "width": v.get("width") if v else None,
            "height": v.get("height") if v else None,
            "fps": fps_from_rfr(v.get("r_frame_rate")) if v else None,
            "duration_s": float(fmt.get("duration")) if fmt.get("duration") else None,
            "bitrate": int(fmt.get("bit_rate")) if fmt.get("bit_rate") else None,
            "size": int(fmt.get("size")) if fmt.get("size") else None
        }
    except Exception as e:
        return {"ffprobe_error": str(e)}

def run_ffmpeg(cmd: List[str], job_id: str):
    if not FFMPEG:
        raise RuntimeError("ffmpeg not found (set FFMPEG_PATH or ensure ffmpeg in PATH)")
    log_line(job_id, "FFMPEG: " + " ".join(cmd))
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.stdout:
        log_line(job_id, p.stdout[-8000:])
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with code {p.returncode}")

def safe_filename(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name or "")
    return name[:200] if name else "file.bin"

QUEUE: List[dict] = []
QUEUE_LOCK = threading.Lock()
WORKER_STARTED = False

def _aspect_wh(aspect: str):
    if aspect == "9:16":
        return (720, 1280)
    if aspect == "1:1":
        return (1024, 1024)
    return (1280, 720)

def _mk_out_dir(job_id: str) -> Path:
    out_dir = OUTPUTS_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir

def _tmp_concat_list(paths: List[Path]) -> Path:
    fd, name = tempfile.mkstemp(prefix="concat_", suffix=".txt")
    os.close(fd)
    tf = Path(name)
    lines = []
    for p in paths:
        lines.append("file '" + str(p).replace("'", "'\\''") + "'")
    tf.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tf

def worker_loop():
    while True:
        job = None
        with QUEUE_LOCK:
            if QUEUE:
                job = QUEUE.pop(0)

        if not job:
            time.sleep(0.25)
            continue

        job_id = job["id"]
        try:
            write_job(job_id, status="running", progress=0.05, error=None)
            log_line(job_id, "job started")
            mode = job["mode"]
            params = job.get("params", {}) or {}
            prompt = job.get("prompt_or_script", "") or ""
            out_dir = _mk_out_dir(job_id)

            if mode == "mock_text_to_video":
                dur = int(params.get("duration", 4))
                fps = int(params.get("fps", 24))
                w, h = _aspect_wh(str(params.get("aspect", "16:9")))
                out_mp4 = out_dir / "final.mp4"

                base = [FFMPEG, "-y", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate={fps}", "-t", str(dur)]
                safe = (prompt or "MOCK").replace("\n", " ").replace("'", r"\'").replace(":", r"\:")
                draw = f"drawtext=text='{safe}':x=20:y=20:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.5"
                cmd = base + ["-vf", draw, "-pix_fmt", "yuv420p", str(out_mp4)]
                try:
                    run_ffmpeg(cmd, job_id)
                except Exception:
                    cmd2 = base + ["-pix_fmt", "yuv420p", str(out_mp4)]
                    run_ffmpeg(cmd2, job_id)

                m = ffprobe_metrics(out_mp4)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(m), status="succeeded", progress=1.0)

            elif mode == "mock_text_to_image":
                from PIL import Image, ImageDraw
                out_png = out_dir / "final.png"
                img = Image.new("RGB", (1024, 576), color=(20, 20, 20))
                d = ImageDraw.Draw(img)
                d.text((24, 24), "MOCK TEXT → IMAGE", fill=(255, 255, 255))
                d.text((24, 80), (prompt or "MOCK")[:900], fill=(230, 230, 230))
                img.save(out_png)

                outputs = {"final": f"/files/{job_id}/final.png"}
                metrics = {"type": "image", "width": 1024, "height": 576, "size": out_png.stat().st_size}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(metrics), status="succeeded", progress=1.0)

            elif mode == "mock_image_to_video":
                dur = int(params.get("duration", 4))
                fps = int(params.get("fps", 24))
                w, h = _aspect_wh(str(params.get("aspect", "16:9")))
                inputs = job.get("inputs", []) or []
                if not inputs:
                    raise RuntimeError("mock_image_to_video requires 1 uploaded image")
                img_path = Path(inputs[0])
                if not img_path.exists():
                    raise RuntimeError("uploaded image not found")

                out_mp4 = out_dir / "final.mp4"
                cmd = [
                    FFMPEG, "-y",
                    "-loop", "1", "-i", str(img_path),
                    "-t", str(dur),
                    "-vf", f"scale={w}:{h},zoompan=z='min(zoom+0.0015,1.2)':d={dur*fps}:s={w}x{h}",
                    "-r", str(fps),
                    "-pix_fmt", "yuv420p",
                    str(out_mp4)
                ]
                run_ffmpeg(cmd, job_id)
                m = ffprobe_metrics(out_mp4)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(m), status="succeeded", progress=1.0)

            elif mode == "ffmpeg_trim":
                inputs = job.get("inputs", []) or []
                if not inputs:
                    raise RuntimeError("ffmpeg_trim requires 1 video")
                src = Path(inputs[0])
                start_s = float(params.get("start_s", 0))
                dur_s = float(params.get("duration_s", 10))
                out_mp4 = out_dir / "final.mp4"
                cmd = [FFMPEG, "-y", "-ss", str(start_s), "-i", str(src), "-t", str(dur_s), "-c", "copy", str(out_mp4)]
                try:
                    run_ffmpeg(cmd, job_id)
                except Exception:
                    cmd2 = [FFMPEG, "-y", "-ss", str(start_s), "-i", str(src), "-t", str(dur_s), "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", str(out_mp4)]
                    run_ffmpeg(cmd2, job_id)
                m = ffprobe_metrics(out_mp4)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(m), status="succeeded", progress=1.0)

            elif mode == "ffmpeg_resize":
                inputs = job.get("inputs", []) or []
                if not inputs:
                    raise RuntimeError("ffmpeg_resize requires 1 video")
                src = Path(inputs[0])
                w = int(params.get("width", 1080))
                h = int(params.get("height", 1920))
                out_mp4 = out_dir / "final.mp4"
                vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
                cmd = [FFMPEG, "-y", "-i", str(src), "-vf", vf, "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", str(out_mp4)]
                run_ffmpeg(cmd, job_id)
                m = ffprobe_metrics(out_mp4)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(m), status="succeeded", progress=1.0)

            elif mode == "ffmpeg_overlay_text":
                inputs = job.get("inputs", []) or []
                if not inputs:
                    raise RuntimeError("ffmpeg_overlay_text requires 1 video")
                src = Path(inputs[0])
                text = (prompt or "").replace("\n", " ").replace("'", r"\'").replace(":", r"\:")
                out_mp4 = out_dir / "final.mp4"
                draw = f"drawtext=text='{text}':x=(w-text_w)/2:y=h*0.08:fontsize=48:fontcolor=white:box=1:boxcolor=black@0.5"
                cmd = [FFMPEG, "-y", "-i", str(src), "-vf", draw, "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", str(out_mp4)]
                run_ffmpeg(cmd, job_id)
                m = ffprobe_metrics(out_mp4)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(m), status="succeeded", progress=1.0)

            elif mode == "ffmpeg_add_music":
                inputs = job.get("inputs", []) or []
                if len(inputs) < 2:
                    raise RuntimeError("ffmpeg_add_music requires 1 video + 1 audio")
                video = Path(inputs[0])
                audio = Path(inputs[1])
                out_mp4 = out_dir / "final.mp4"
                cmd = [
                    FFMPEG, "-y", "-i", str(video), "-i", str(audio),
                    "-filter_complex", "[1:a]volume=0.7[a1];[0:a][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                    "-map", "0:v:0", "-map", "[aout]",
                    "-c:v", "copy", "-c:a", "aac",
                    str(out_mp4)
                ]
                try:
                    run_ffmpeg(cmd, job_id)
                except Exception:
                    cmd2 = [
                        FFMPEG, "-y", "-i", str(video), "-i", str(audio),
                        "-filter_complex", "[1:a]volume=0.7[a1];[0:a][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                        "-map", "0:v:0", "-map", "[aout]",
                        "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p",
                        str(out_mp4)
                    ]
                    run_ffmpeg(cmd2, job_id)
                m = ffprobe_metrics(out_mp4)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(m), status="succeeded", progress=1.0)

            elif mode == "ffmpeg_burn_srt":
                inputs = job.get("inputs", []) or []
                if len(inputs) < 2:
                    raise RuntimeError("ffmpeg_burn_srt requires 1 video + 1 .srt")
                video = Path(inputs[0])
                srt = Path(inputs[1])
                if not srt.name.lower().endswith(".srt"):
                    raise RuntimeError("second file must be .srt")
                out_mp4 = out_dir / "final.mp4"
                cmd = [FFMPEG, "-y", "-i", str(video), "-vf", f"subtitles={str(srt)}", "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", str(out_mp4)]
                run_ffmpeg(cmd, job_id)
                m = ffprobe_metrics(out_mp4)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(m), status="succeeded", progress=1.0)

            elif mode == "ffmpeg_concat":
                inputs = job.get("inputs", []) or []
                if len(inputs) < 2:
                    raise RuntimeError("ffmpeg_concat requires 2+ videos")
                paths = [Path(p) for p in inputs]
                out_mp4 = out_dir / "final.mp4"
                lst = _tmp_concat_list(paths)
                try:
                    cmd = [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out_mp4)]
                    run_ffmpeg(cmd, job_id)
                except Exception:
                    cmd2 = [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", str(out_mp4)]
                    run_ffmpeg(cmd2, job_id)
                finally:
                    try:
                        lst.unlink()
                    except Exception:
                        pass
                m = ffprobe_metrics(out_mp4)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(m), status="succeeded", progress=1.0)

            elif mode == "ffmpeg_slideshow":
                inputs = job.get("inputs", []) or []
                if len(inputs) < 1:
                    raise RuntimeError("ffmpeg_slideshow requires 1+ images")
                fps = int(params.get("fps", 24))
                dur = float(params.get("duration_s", 10))
                out_mp4 = out_dir / "final.mp4"
                per = max(0.5, dur / max(1, len(inputs)))
                fd, name = tempfile.mkstemp(prefix="slideshow_", suffix=".txt")
                os.close(fd)
                lst = Path(name)
                lines = []
                for p in inputs:
                    pp = Path(p)
                    lines.append("file '" + str(pp).replace("'", "'\\''") + "'")
                    lines.append(f"duration {per}")
                lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
                try:
                    cmd = [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-vsync", "vfr", "-pix_fmt", "yuv420p", "-r", str(fps), "-c:v", "libx264", str(out_mp4)]
                    run_ffmpeg(cmd, job_id)
                finally:
                    try:
                        lst.unlink()
                    except Exception:
                        pass
                m = ffprobe_metrics(out_mp4)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(m), status="succeeded", progress=1.0)

elif mode == "ffmpeg_speed":
    inputs = job.get("inputs", []) or []
    if not inputs:
        raise RuntimeError("ffmpeg_speed requires 1 video")
    src = Path(inputs[0])
    speed = float(params.get("speed", 1.25))
    if speed <= 0:
        raise RuntimeError("speed must be > 0")
    out_mp4 = out_dir / "final.mp4"
    # video: setpts=PTS/speed ; audio: atempo supports 0.5-2.0 per filter, chain if needed
    vfilter = f"setpts=PTS/{speed}"
    # chain atempo for audio
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
    run_ffmpeg(cmd, job_id)
    m = ffprobe_metrics(out_mp4)
    outputs = {"final": f"/files/{job_id}/final.mp4"}
    write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(m), status="succeeded", progress=1.0)

            else:
                raise RuntimeError(f"Unknown mode: {mode}")

        except Exception as e:
            write_job(job_id, status="failed", error=str(e), progress=1.0)
            log_line(job_id, "ERROR: " + str(e))

class JobCreate(BaseModel):
    profile_id: str
    mode: str
    prompt_or_script: Optional[str] = ""
    inputs: Optional[List[str]] = []
    params: Optional[Dict[str, Any]] = {}
    content_sensitive: bool = False
    consent: bool = False

class CompareReq(BaseModel):
    a_job_id: str
    b_job_id: str

class ImportCdcReq(BaseModel):
    pid: int

class ImportCommonsReq(BaseModel):
    category: str
    limit: int = 30

app = FastAPI(title="MinhaIALAST — Studio Local")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def _startup():
    init_db()
    global WORKER_STARTED
    if not WORKER_STARTED:
        t = threading.Thread(target=worker_loop, daemon=True)
        t.start()
        WORKER_STARTED = True

@app.get("/health")
def health():
    def free_bytes(path: str):
        try:
            return shutil.disk_usage(path).free
        except Exception:
            return None
    return {
        "ok": True,
        "root": str(ROOT),
        "ffmpeg": FFMPEG,
        "ffprobe": FFPROBE,
        "free_root_bytes": free_bytes(str(ROOT)),
    }

@app.get("/profiles")
def profiles():
    return load_json(CONFIG_DIR / "profiles.json")

@app.post("/uploads")
async def uploads(file: UploadFile = File(...)):
    uid = uuid.uuid4().hex
    dest_dir = UPLOADS_DIR / uid
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = safe_filename(file.filename or "upload.bin")
    dest = dest_dir / fname
    dest.write_bytes(await file.read())
    return {"upload_id": uid, "path": str(dest)}

@app.post("/jobs")
def create_job(req: JobCreate):
    job_id = uuid.uuid4().hex
    conn = db()
    conn.execute(
        "INSERT INTO jobs (id, created_at, profile_id, mode, status, progress, error, inputs_json, params_json, outputs_json, metrics_json, content_sensitive, consent) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            job_id, now_iso(), req.profile_id, req.mode, "queued", 0.0, None,
            json.dumps(req.inputs or []),
            json.dumps(req.params or {}),
            None, None,
            1 if req.content_sensitive else 0,
            1 if req.consent else 0
        )
    )
    conn.commit()
    conn.close()

    with QUEUE_LOCK:
        QUEUE.append({
            "id": job_id,
            "mode": req.mode,
            "prompt_or_script": req.prompt_or_script,
            "inputs": req.inputs or [],
            "params": req.params or {}
        })
    return {"id": job_id}

@app.get("/jobs/{job_id}")
def job(job_id: str):
    return get_job(job_id)

@app.get("/jobs")
def jobs():
    return {"items": list_jobs(200)}

@app.post("/jobs/compare")
def compare(req: CompareReq):
    a = get_job(req.a_job_id)
    b = get_job(req.b_job_id)
    return {"a": a.get("metrics_json"), "b": b.get("metrics_json"), "a_job": a, "b_job": b}

@app.get("/files/{job_id}/{filename}")
def files(job_id: str, filename: str):
    base = OUTPUTS_DIR / job_id
    target = (base / filename).resolve()
    if not str(target).startswith(str(base.resolve())):
        raise HTTPException(status_code=400, detail="invalid path")
    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(str(target))

# Assets library
from .assets_store import list_items
from .assets_import import import_cdc_phil, import_commons_category

@app.get("/assets")
def assets(limit: int = 200):
    return {"items": list_items(limit)}

@app.post("/assets/import/cdc_phil")
def assets_import_cdc(req: ImportCdcReq):
    return import_cdc_phil(req.pid)

@app.post("/assets/import/commons_category")
def assets_import_commons(req: ImportCommonsReq):
    return import_commons_category(req.category, req.limit)

@app.get("/assets/file/{asset_id}")
def assets_file(asset_id: str):
    items = list_items(4000)
    hit = next((x for x in items if x.get("id") == asset_id), None)
    if not hit:
        raise HTTPException(status_code=404, detail="asset not found")
    rel = hit.get("local_file")
    if not rel:
        raise HTTPException(status_code=404, detail="asset file missing")
    target = (ROOT / rel).resolve()
    base = (ROOT / "storage" / "assets" / "files").resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(status_code=400, detail="invalid path")
    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(str(target))

@app.get("/", response_class=HTMLResponse)
def ui_root():
    index_path = ROOT / "apps" / "web" / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))
