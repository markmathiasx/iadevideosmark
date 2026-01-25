import os, re, json, uuid, time, sqlite3, threading, subprocess
from pathlib import Path
from typing import Any, Dict, Optional, List
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]  # .../MinhaIALAST
CONFIG_DIR = ROOT / "config"
OUTPUTS_DIR = ROOT / "outputs"
UPLOADS_DIR = OUTPUTS_DIR / "_uploads"
STORAGE_DIR = ROOT / "storage"
LOGS_DIR = STORAGE_DIR / "logs"
DB_PATH = Path(__file__).resolve().parent / "data" / "jobs.db"

def where_exe(name: str) -> Optional[str]:
    # Use where.exe on Windows
    try:
        out = subprocess.check_output(["where.exe", name], stderr=subprocess.STDOUT, text=True)
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

def db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    ensure_dirs()
    conn = db()
    conn.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
      id TEXT PRIMARY KEY,
      created_at TEXT,
      profile_id TEXT,
      mode TEXT,
      status TEXT,
      progress REAL,
      error TEXT,
      inputs_json TEXT,
      params_json TEXT,
      outputs_json TEXT,
      metrics_json TEXT,
      content_sensitive INTEGER,
      consent INTEGER
    )
    """)
    conn.commit()
    conn.close()

def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def contains_blocked_terms(text: str, blocked: List[str]) -> Optional[str]:
    t = (text or "").lower()
    for term in blocked:
        if term.lower() in t:
            return term
    return None

def log_line(job_id: str, msg: str):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    p = LOGS_DIR / f"job-{job_id}.log"
    p.write_text((p.read_text(encoding="utf-8") if p.exists() else "") + msg + "\n", encoding="utf-8")

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

def get_job(job_id: str) -> Dict[str, Any]:
    conn = db()
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    d = dict(row)
    for k in ["inputs_json","params_json","outputs_json","metrics_json"]:
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except Exception:
                pass
        else:
            d[k] = None
    return d

def list_jobs(limit=100):
    conn = db()
    rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        for k in ["inputs_json","params_json","outputs_json","metrics_json"]:
            if d.get(k):
                try:
                    d[k] = json.loads(d[k])
                except Exception:
                    pass
            else:
                d[k] = None
        out.append(d)
    return out

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
        # summarize
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
    log_line(job_id, p.stdout[-6000:] if p.stdout else "")
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with code {p.returncode}")

def safe_filename(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name)
    return name[:200] if name else "file.bin"

# Job queue
QUEUE: "list[dict]" = []
QUEUE_LOCK = threading.Lock()
WORKER_STARTED = False

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
            params = job.get("params", {})
            prompt = job.get("prompt_or_script", "")

            out_dir = OUTPUTS_DIR / job_id
            out_dir.mkdir(parents=True, exist_ok=True)

            if mode == "mock_text_to_video":
                dur = int(params.get("duration", 4))
                fps = int(params.get("fps", 24))
                w, h = (1280, 720)
                aspect = params.get("aspect", "16:9")
                if aspect == "9:16": w, h = (720, 1280)
                if aspect == "1:1": w, h = (1024, 1024)
                out_mp4 = out_dir / "final.mp4"
                # drawtext may fail without fonts; fallback to no drawtext
                base = [FFMPEG, "-y", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate={fps}", "-t", str(dur)]
                draw = f"drawtext=text='{(prompt or 'MOCK').replace(\"'\", \"\\\\'\")}'" \
                       f":x=20:y=20:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.5"
                cmd = base + ["-vf", draw, "-pix_fmt", "yuv420p", str(out_mp4)]
                try:
                    run_ffmpeg(cmd, job_id)
                except Exception:
                    cmd2 = base + ["-pix_fmt", "yuv420p", str(out_mp4)]
                    run_ffmpeg(cmd2, job_id)

                write_job(job_id, progress=0.9)
                m = ffprobe_metrics(out_mp4)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(m), status="succeeded", progress=1.0)

            elif mode == "mock_text_to_image":
                from PIL import Image, ImageDraw, ImageFont
                out_png = out_dir / "final.png"
                img = Image.new("RGB", (1024, 576), color=(20, 20, 20))
                draw = ImageDraw.Draw(img)
                text = prompt or "MOCK"
                draw.text((24, 24), "MOCK TEXT  IMAGE", fill=(255, 255, 255))
                draw.text((24, 80), text[:900], fill=(230, 230, 230))
                img.save(out_png)
                m = {"type": "image", "width": 1024, "height": 576, "size": out_png.stat().st_size}
                outputs = {"final": f"/files/{job_id}/final.png"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(m), status="succeeded", progress=1.0)

            elif mode == "mock_image_to_video":
                # expects one uploaded image in inputs
                dur = int(params.get("duration", 4))
                fps = int(params.get("fps", 24))
                aspect = params.get("aspect", "16:9")
                w, h = (1280, 720)
                if aspect == "9:16": w, h = (720, 1280)
                if aspect == "1:1": w, h = (1024, 1024)

                inputs = job.get("inputs", [])
                if not inputs:
                    raise RuntimeError("mock_image_to_video requires an uploaded image")
                img_path = Path(inputs[0])
                if not img_path.exists():
                    raise RuntimeError("uploaded image not found")

                out_mp4 = out_dir / "final.mp4"
                # zoompan simple
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

app = FastAPI(title="AI Studio Local (MVP)")

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
    def free_bytes(drive: str) -> Optional[int]:
        try:
            p = Path(drive)
            st = os.statvfs(str(p))
            return st.f_bavail * st.f_frsize
        except Exception:
            return None

    return {
        "ok": True,
        "root": str(ROOT),
        "ffmpeg": FFMPEG,
        "ffprobe": FFPROBE,
        "free_D_bytes": free_bytes("D:\\"),
        "free_C_bytes": free_bytes("C:\\"),
    }

@app.get("/profiles")
def profiles():
    return load_json(CONFIG_DIR / "profiles.json")

@app.get("/policy")
def policy():
    return load_json(CONFIG_DIR / "content_policy.json")

@app.post("/uploads")
async def uploads(file: UploadFile = File(...)):
    uid = uuid.uuid4().hex
    dest_dir = UPLOADS_DIR / uid
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = safe_filename(file.filename or "upload.bin")
    dest = dest_dir / fname
    content = await file.read()
    dest.write_bytes(content)
    return {"upload_id": uid, "path": str(dest)}

@app.post("/jobs")
def create_job(req: JobCreate):
    pol = load_json(CONFIG_DIR / "content_policy.json")
    blocked = pol.get("blocked_terms_when_sensitive_off", [])
    if not req.content_sensitive:
        hit = contains_blocked_terms(req.prompt_or_script or "", blocked)
        if hit:
            raise HTTPException(status_code=400, detail=f"Blocked by policy (term='{hit}'). Enable sensitive toggle to proceed (requires consent).")
    else:
        if pol.get("require_consent_for_sensitive", True) and not req.consent:
            raise HTTPException(status_code=400, detail="Consent required for sensitive mode.")

    job_id = uuid.uuid4().hex
    conn = db()
    conn.execute("""
      INSERT INTO jobs (id, created_at, profile_id, mode, status, progress, error,
                        inputs_json, params_json, outputs_json, metrics_json, content_sensitive, consent)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job_id, now_iso(), req.profile_id, req.mode, "queued", 0.0, None,
        json.dumps(req.inputs or []),
        json.dumps(req.params or {}),
        None, None,
        1 if req.content_sensitive else 0,
        1 if req.consent else 0
    ))
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
    return {"items": list_jobs(100)}

@app.post("/jobs/compare")
def compare(req: CompareReq):
    a = get_job(req.a_job_id)
    b = get_job(req.b_job_id)
    return {"a": a.get("metrics_json"), "b": b.get("metrics_json"), "a_job": a, "b_job": b}

@app.get("/files/{job_id}/{filename}")
def files(job_id: str, filename: str):
    # Serve only within outputs/<job_id>/
    base = OUTPUTS_DIR / job_id
    target = (base / filename).resolve()
    if not str(target).startswith(str(base.resolve())):
        raise HTTPException(status_code=400, detail="invalid path")
    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(str(target))

# Serve a simple UI without Node
INDEX = (ROOT / "apps" / "web" / "index.html").read_text(encoding="utf-8")

@app.get("/", response_class=HTMLResponse)
def ui_root():
    return HTMLResponse(INDEX)
