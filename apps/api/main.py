import json, os, re, shutil, sqlite3, subprocess, threading, time, uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
OUTPUTS_DIR = ROOT / "outputs"
UPLOADS_DIR = OUTPUTS_DIR / "_uploads"
STORAGE_DIR = ROOT / "storage"
LOGS_DIR = STORAGE_DIR / "logs"
DB_PATH = Path(__file__).resolve().parent / "data" / "jobs.db"

def ensure_dirs() -> None:
    (Path(__file__).resolve().parent / "data").mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def find_exe(name: str) -> Optional[str]:
    return shutil.which(name)

FFMPEG = os.environ.get("FFMPEG_PATH") or find_exe("ffmpeg")
FFPROBE = os.environ.get("FFPROBE_PATH") or find_exe("ffprobe")

def log_line(job_id: str, msg: str) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    p = LOGS_DIR / f"job-{job_id}.log"
    with p.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")

def run_cmd(cmd: List[str], job_id: str) -> None:
    log_line(job_id, "CMD: " + " ".join(cmd))
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.stdout:
        log_line(job_id, p.stdout[-6000:])
    if p.returncode != 0:
        raise RuntimeError(f"Command failed ({p.returncode})")

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

        def fps_from_rfr(r: Optional[str]):
            try:
                num, den = (r or "").split("/")
                return float(num) / float(den)
            except Exception:
                return None

        return {
            "video_codec": v.get("codec_name") if v else None,
            "audio_codec": a.get("codec_name") if a else None,
            "width": v.get("width") if v else None,
            "height": v.get("height") if v else None,
            "fps": fps_from_rfr(v.get("r_frame_rate") if v else None),
            "duration_s": float(fmt.get("duration")) if fmt.get("duration") else None,
            "bitrate": int(fmt.get("bit_rate")) if fmt.get("bit_rate") else None,
            "size": int(fmt.get("size")) if fmt.get("size") else None,
        }
    except Exception as e:
        return {"ffprobe_error": str(e)}

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

def write_job(job_id: str, **fields):
    conn = db()
    sets, vals = [], []
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
    for k in ["inputs_json", "params_json", "outputs_json", "metrics_json"]:
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
        for k in ["inputs_json", "params_json", "outputs_json", "metrics_json"]:
            if d.get(k):
                try:
                    d[k] = json.loads(d[k])
                except Exception:
                    pass
            else:
                d[k] = None
        out.append(d)
    return out

def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def contains_blocked_terms(text: str, blocked: List[str]) -> Optional[str]:
    t = (text or "").lower()
    for term in blocked:
        if term.lower() in t:
            return term
    return None

def safe_filename(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name or "")
    return (name[:200] if name else "file.bin")

QUEUE: List[dict] = []
QUEUE_LOCK = threading.Lock()
WORKER_STARTED = False

class JobCreate(BaseModel):
    profile_id: str
    mode: str
    prompt_or_script: Optional[str] = ""
    inputs: Optional[List[str]] = []
    params: Optional[Dict[str, Any]] = {}
    content_sensitive: bool = False
    consent: bool = False

class ImportCdcReq(BaseModel):
    pid: int

class ImportCommonsReq(BaseModel):
    category: str
    limit: int = 30

def _aspect_to_wh(aspect: str):
    if aspect == "16:9":
        return 1280, 720
    if aspect == "1:1":
        return 1024, 1024
    return 720, 1280  # default 9:16

def worker_loop():
    while True:
        with QUEUE_LOCK:
            job = QUEUE.pop(0) if QUEUE else None
        if not job:
            time.sleep(0.25)
            continue

        job_id = job["id"]
        try:
            write_job(job_id, status="running", progress=0.05, error=None)
            mode = job["mode"]
            params = job.get("params", {}) or {}
            prompt = job.get("prompt_or_script", "") or ""
            inputs = job.get("inputs", []) or []

            out_dir = OUTPUTS_DIR / job_id
            out_dir.mkdir(parents=True, exist_ok=True)

            if mode == "shorts_builder":
                if not FFMPEG:
                    raise RuntimeError("ffmpeg missing")
                dur = int(params.get("duration", 12))
                fps = int(params.get("fps", 30))
                w, h = (720, 1280)
                out_mp4 = out_dir / "final.mp4"
                text = (prompt or "Shorts").replace("\n", " ")
                safe = text.replace("'", "\\'").replace(":", "\\:")
                draw = f"drawtext=text='{safe}':x=40:y=h-160:fontsize=36:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=16"
                cmd = [FFMPEG, "-y", "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={fps}", "-t", str(dur), "-vf", draw, "-pix_fmt", "yuv420p", str(out_mp4)]
                run_cmd(cmd, job_id)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(ffprobe_metrics(out_mp4)), status="succeeded", progress=1.0)

            elif mode == "mock_text_to_video":
                if not FFMPEG:
                    raise RuntimeError("ffmpeg missing")
                dur = int(params.get("duration", 6))
                fps = int(params.get("fps", 30))
                w, h = _aspect_to_wh(str(params.get("aspect", "9:16")))
                out_mp4 = out_dir / "final.mp4"
                safe = prompt.replace("\n", " ").replace("'", "\\'").replace(":", "\\:")
                draw = f"drawtext=text='{safe}':x=20:y=20:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.5"
                cmd = [FFMPEG, "-y", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate={fps}", "-t", str(dur), "-vf", draw, "-pix_fmt", "yuv420p", str(out_mp4)]
                try:
                    run_cmd(cmd, job_id)
                except Exception:
                    cmd2 = [FFMPEG, "-y", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate={fps}", "-t", str(dur), "-pix_fmt", "yuv420p", str(out_mp4)]
                    run_cmd(cmd2, job_id)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(ffprobe_metrics(out_mp4)), status="succeeded", progress=1.0)

            elif mode == "mock_image_to_video":
                if not FFMPEG:
                    raise RuntimeError("ffmpeg missing")
                if not inputs:
                    raise RuntimeError("upload 1 image")
                img_path = Path(inputs[0])
                if not img_path.exists():
                    raise RuntimeError("uploaded image missing")
                dur = int(params.get("duration", 4))
                fps = int(params.get("fps", 24))
                w, h = _aspect_to_wh(str(params.get("aspect", "9:16")))
                out_mp4 = out_dir / "final.mp4"
                cmd = [
                    FFMPEG, "-y",
                    "-loop", "1", "-i", str(img_path),
                    "-t", str(dur),
                    "-vf", f"scale={w}:{h},zoompan=z='min(zoom+0.0015,1.2)':d={dur*fps}:s={w}x{h}",
                    "-r", str(fps),
                    "-pix_fmt", "yuv420p",
                    str(out_mp4),
                ]
                run_cmd(cmd, job_id)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(ffprobe_metrics(out_mp4)), status="succeeded", progress=1.0)

            elif mode == "mock_text_to_image":
                from PIL import Image, ImageDraw
                out_png = out_dir / "final.png"
                img = Image.new("RGB", (1024, 576), color=(20, 20, 20))
                d = ImageDraw.Draw(img)
                d.text((24, 24), "MOCK TEXT → IMAGE", fill=(255, 255, 255))
                d.text((24, 90), (prompt[:900] or "MOCK"), fill=(230, 230, 230))
                img.save(out_png)
                outputs = {"final": f"/files/{job_id}/final.png"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps({"size": out_png.stat().st_size}), status="succeeded", progress=1.0)

            elif mode == "ffmpeg_resize":
                if not FFMPEG:
                    raise RuntimeError("ffmpeg missing")
                if not inputs:
                    raise RuntimeError("upload 1 video")
                in_path = Path(inputs[0])
                if not in_path.exists():
                    raise RuntimeError("uploaded video missing")
                w, h = _aspect_to_wh(str(params.get("aspect", "9:16")))
                out_mp4 = out_dir / "final.mp4"
                cmd = [
                    FFMPEG, "-y", "-i", str(in_path),
                    "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "128k",
                    str(out_mp4)
                ]
                run_cmd(cmd, job_id)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(ffprobe_metrics(out_mp4)), status="succeeded", progress=1.0)

            elif mode == "ffmpeg_trim":
                if not FFMPEG:
                    raise RuntimeError("ffmpeg missing")
                if not inputs:
                    raise RuntimeError("upload 1 video")
                in_path = Path(inputs[0])
                if not in_path.exists():
                    raise RuntimeError("uploaded video missing")
                start = float(params.get("start", 0))
                dur = params.get("duration")
                end = params.get("end")
                out_mp4 = out_dir / "final.mp4"
                cmd = [FFMPEG, "-y"]
                if start > 0:
                    cmd += ["-ss", str(start)]
                cmd += ["-i", str(in_path)]
                if end is not None:
                    cmd += ["-to", str(float(end))]
                elif dur is not None:
                    cmd += ["-t", str(float(dur))]
                cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "128k", str(out_mp4)]
                run_cmd(cmd, job_id)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(ffprobe_metrics(out_mp4)), status="succeeded", progress=1.0)

            elif mode == "ffmpeg_concat":
                if not FFMPEG:
                    raise RuntimeError("ffmpeg missing")
                if len(inputs) < 2:
                    raise RuntimeError("upload 2+ videos")
                paths = [Path(x) for x in inputs]
                for pp in paths:
                    if not pp.exists():
                        raise RuntimeError("uploaded input missing")
                lst = out_dir / "concat.txt"
                lst.write_text("\n".join(["file '" + str(pp).replace("'", "\\'") + "'" for pp in paths]) + "\n", encoding="utf-8")
                out_mp4 = out_dir / "final.mp4"
                cmd = [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out_mp4)]
                try:
                    run_cmd(cmd, job_id)
                except Exception:
                    cmd2 = [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                            "-c:a", "aac", "-b:a", "128k", str(out_mp4)]
                    run_cmd(cmd2, job_id)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(ffprobe_metrics(out_mp4)), status="succeeded", progress=1.0)

            elif mode == "ffmpeg_merge_audio":
                if not FFMPEG:
                    raise RuntimeError("ffmpeg missing")
                if len(inputs) < 2:
                    raise RuntimeError("upload 1 video + 1 audio")
                v = Path(inputs[0]); a = Path(inputs[1])
                if not v.exists() or not a.exists():
                    raise RuntimeError("uploaded inputs missing")
                out_mp4 = out_dir / "final.mp4"
                cmd = [FFMPEG, "-y", "-i", str(v), "-i", str(a), "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(out_mp4)]
                run_cmd(cmd, job_id)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(ffprobe_metrics(out_mp4)), status="succeeded", progress=1.0)

            elif mode == "ffmpeg_extract_audio":
                if not FFMPEG:
                    raise RuntimeError("ffmpeg missing")
                if not inputs:
                    raise RuntimeError("upload 1 video")
                in_path = Path(inputs[0])
                if not in_path.exists():
                    raise RuntimeError("uploaded video missing")
                out_ext = str(params.get("audio_ext", "mp3")).lower().strip(".")
                out_audio = out_dir / f"audio.{out_ext}"
                cmd = [FFMPEG, "-y", "-i", str(in_path), "-vn"]
                if out_ext == "wav":
                    cmd += ["-acodec", "pcm_s16le"]
                else:
                    cmd += ["-acodec", "libmp3lame", "-b:a", "192k"]
                cmd += [str(out_audio)]
                run_cmd(cmd, job_id)
                outputs = {"final": f"/files/{job_id}/{out_audio.name}"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps({"size": out_audio.stat().st_size}), status="succeeded", progress=1.0)

            elif mode == "ffmpeg_overlay_text":
                if not FFMPEG:
                    raise RuntimeError("ffmpeg missing")
                if not inputs:
                    raise RuntimeError("upload 1 video")
                in_path = Path(inputs[0])
                if not in_path.exists():
                    raise RuntimeError("uploaded video missing")
                text = (prompt or params.get("text") or "Texto").replace("\n", " ")
                safe = text.replace("'", "\\'").replace(":", "\\:")
                x = params.get("x", "40")
                y = params.get("y", "40")
                fontsize = int(params.get("fontsize", 40))
                box = int(params.get("box", 1))
                draw = f"drawtext=text='{safe}':x={x}:y={y}:fontsize={fontsize}:fontcolor=white"
                if box:
                    draw += ":box=1:boxcolor=black@0.55:boxborderw=16"
                out_mp4 = out_dir / "final.mp4"
                cmd = [FFMPEG, "-y", "-i", str(in_path), "-vf", draw, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "copy", str(out_mp4)]
                run_cmd(cmd, job_id)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(ffprobe_metrics(out_mp4)), status="succeeded", progress=1.0)

            elif mode == "ffmpeg_watermark":
                if not FFMPEG:
                    raise RuntimeError("ffmpeg missing")
                if len(inputs) < 2:
                    raise RuntimeError("upload 1 video + 1 image (logo)")
                v = Path(inputs[0]); img = Path(inputs[1])
                if not v.exists() or not img.exists():
                    raise RuntimeError("uploaded inputs missing")
                pos = str(params.get("pos", "tr"))  # tr/tl/br/bl
                margin = int(params.get("margin", 16))
                scale_w = int(params.get("scale_w", 180))
                if pos == "tl":
                    ox, oy = f"{margin}", f"{margin}"
                elif pos == "br":
                    ox, oy = f"main_w-overlay_w-{margin}", f"main_h-overlay_h-{margin}"
                elif pos == "bl":
                    ox, oy = f"{margin}", f"main_h-overlay_h-{margin}"
                else:
                    ox, oy = f"main_w-overlay_w-{margin}", f"{margin}"
                img_arg = str(img).replace(":", "\\:")
                vf = f"movie={img_arg},scale={scale_w}:-1[wm];[in][wm]overlay={ox}:{oy}[out]"
                out_mp4 = out_dir / "final.mp4"
                cmd = [FFMPEG, "-y", "-i", str(v), "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "copy", str(out_mp4)]
                run_cmd(cmd, job_id)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(ffprobe_metrics(out_mp4)), status="succeeded", progress=1.0)

            elif mode == "ffmpeg_burn_subtitles":
                if not FFMPEG:
                    raise RuntimeError("ffmpeg missing")
                if len(inputs) < 2:
                    raise RuntimeError("upload 1 video + 1 .srt/.ass")
                v = Path(inputs[0]); s = Path(inputs[1])
                if not v.exists() or not s.exists():
                    raise RuntimeError("uploaded inputs missing")
                out_mp4 = out_dir / "final.mp4"
                sub = str(s).replace(":", "\\:")
                cmd = [FFMPEG, "-y", "-i", str(v), "-vf", f"subtitles={sub}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "copy", str(out_mp4)]
                run_cmd(cmd, job_id)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(ffprobe_metrics(out_mp4)), status="succeeded", progress=1.0)

            elif mode == "ffmpeg_fade":
                if not FFMPEG:
                    raise RuntimeError("ffmpeg missing")
                if not inputs:
                    raise RuntimeError("upload 1 video")
                in_path = Path(inputs[0])
                if not in_path.exists():
                    raise RuntimeError("uploaded video missing")
                fade_in = float(params.get("fade_in", 0.5))
                fade_out = float(params.get("fade_out", 0.5))
                meta = ffprobe_metrics(in_path)
                total = meta.get("duration_s") if isinstance(meta, dict) else None
                if not total:
                    total = float(params.get("duration", 5))
                st_out = max(float(total) - fade_out, 0.0)
                vf = f"fade=t=in:st=0:d={fade_in},fade=t=out:st={st_out}:d={fade_out}"
                af = f"afade=t=in:st=0:d={fade_in},afade=t=out:st={st_out}:d={fade_out}"
                out_mp4 = out_dir / "final.mp4"
                cmd = [FFMPEG, "-y", "-i", str(in_path), "-vf", vf, "-af", af, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", str(out_mp4)]
                run_cmd(cmd, job_id)
                outputs = {"final": f"/files/{job_id}/final.mp4"}
                write_job(job_id, outputs_json=json.dumps(outputs), metrics_json=json.dumps(ffprobe_metrics(out_mp4)), status="succeeded", progress=1.0)

            else:
                raise RuntimeError(f"Unknown mode: {mode}")

        except Exception as e:
            write_job(job_id, status="failed", error=str(e), progress=1.0)
            log_line(job_id, "ERROR: " + str(e))

app = FastAPI(title="MinhaIA Local (Executor)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def _startup():
    init_db()
    global WORKER_STARTED
    if not WORKER_STARTED:
        threading.Thread(target=worker_loop, daemon=True).start()
        WORKER_STARTED = True

@app.get("/health")
def health():
    return {"ok": True, "ffmpeg": FFMPEG, "ffprobe": FFPROBE, "time": now_iso()}

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
    dest.write_bytes(await file.read())
    return {"upload_id": uid, "path": str(dest)}

@app.post("/jobs")
def create_job(req: JobCreate):
    pol = load_json(CONFIG_DIR / "content_policy.json")
    blocked = pol.get("blocked_terms_when_sensitive_off", []) or []

    if not req.content_sensitive:
        hit = contains_blocked_terms(req.prompt_or_script or "", blocked)
        if hit:
            raise HTTPException(status_code=400, detail=f"Blocked by local policy (term='{hit}').")
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
        json.dumps(req.inputs or []), json.dumps(req.params or {}),
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
            "params": req.params or {},
        })
    return {"id": job_id}

@app.get("/jobs/{job_id}")
def job(job_id: str):
    return get_job(job_id)

@app.get("/jobs")
def jobs():
    return {"items": list_jobs(100)}

@app.get("/logs/{job_id}")
def logs(job_id: str):
    p = LOGS_DIR / f"job-{job_id}.log"
    if not p.exists():
        raise HTTPException(status_code=404, detail="log not found")
    return {"text": p.read_text(encoding="utf-8")}

@app.get("/files/{job_id}/{filename}")
def files(job_id: str, filename: str):
    base = OUTPUTS_DIR / job_id
    target = (base / filename).resolve()
    if not str(target).startswith(str(base.resolve())):
        raise HTTPException(status_code=400, detail="invalid path")
    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(str(target))

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
    items = list_items(5000)
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

INDEX_PATH = ROOT / "apps" / "web" / "index.html"
INDEX_HTML = INDEX_PATH.read_text(encoding="utf-8") if INDEX_PATH.exists() else "<h1>UI missing</h1>"

@app.get("/", response_class=HTMLResponse)
def ui_root():
    return HTMLResponse(INDEX_HTML)
