from __future__ import annotations

import os
import time
import uuid
import threading
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# -------------------------
# App / Paths
# -------------------------

ROOT = Path(__file__).resolve().parents[2]
OUTPUTS_DIR = ROOT / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")

app = FastAPI(title="MinhaIA LAST (Local)", version="0.1.0")


# -------------------------
# Models
# -------------------------

class JobCreate(BaseModel):
    profile_id: str
    mode: str
    prompt_or_script: str = ""
    inputs: List[str] = Field(default_factory=list)
    params: Dict[str, Any] = Field(default_factory=dict)
    content_sensitive: bool = False
    consent: bool = False


class JobState(BaseModel):
    id: str
    status: str
    created_at: str
    updated_at: str
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


# -------------------------
# In-memory job store
# -------------------------

_JOBS: Dict[str, JobState] = {}
_LOCK = threading.Lock()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _set_job(job_id: str, **updates: Any) -> JobState:
    with _LOCK:
        st = _JOBS.get(job_id)
        if not st:
            raise KeyError(job_id)
        data = st.model_dump()
        data.update(updates)
        data["updated_at"] = _now_iso()
        st = JobState(**data)
        _JOBS[job_id] = st
        return st


def _run_mock_video(job_id: str, prompt: str, params: Dict[str, Any]) -> None:
    """
    Gera um MP4 simples (testsrc) via ffmpeg.
    Não usa drawtext (evita problemas de fonte no container).
    """
    try:
        dur = float(params.get("duration", 3))
        fps = int(params.get("fps", 24))
        aspect = str(params.get("aspect", "16:9"))
        # Resoluções básicas
        if aspect == "9:16":
            w, h = 720, 1280
        elif aspect == "1:1":
            w, h = 1024, 1024
        else:
            w, h = 1280, 720

        out_mp4 = OUTPUTS_DIR / f"job_{job_id}.mp4"

        cmd = [
            FFMPEG, "-y",
            "-f", "lavfi",
            "-i", f"testsrc=size={w}x{h}:rate={fps}",
            "-t", str(dur),
            "-pix_fmt", "yuv420p",
            str(out_mp4),
        ]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError((p.stderr or p.stdout or "").strip()[:2000])

        _set_job(job_id, status="succeeded", result={
            "type": "video/mp4",
            "file": str(out_mp4.relative_to(ROOT)).replace("\\", "/"),
            "url": f"/outputs/{out_mp4.name}",
        })
    except Exception as e:
        _set_job(job_id, status="failed", error=str(e))


# -------------------------
# Routes
# -------------------------

@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "ts": _now_iso()}


@app.post("/jobs")
def create_job(req: JobCreate) -> JobState:
    # Mantém “controle” básico: este build só executa o modo MOCK.
    # (Você pode plugar outros modos depois.)
    job_id = uuid.uuid4().hex
    st = JobState(id=job_id, status="queued", created_at=_now_iso(), updated_at=_now_iso())
    with _LOCK:
        _JOBS[job_id] = st

    if req.mode != "mock_text_to_video":
        _set_job(job_id, status="failed", error="This build only supports mode=mock_text_to_video for now.")
        return _JOBS[job_id]

    _set_job(job_id, status="running")

    th = threading.Thread(
        target=_run_mock_video,
        args=(job_id, req.prompt_or_script or "", req.params or {}),
        daemon=True,
    )
    th.start()
    return _JOBS[job_id]


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> JobState:
    with _LOCK:
        st = _JOBS.get(job_id)
    if not st:
        raise HTTPException(status_code=404, detail="job not found")
    return st


@app.get("/outputs/{name}")
def outputs_file(name: str):
    target = (OUTPUTS_DIR / name).resolve()
    base = OUTPUTS_DIR.resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(status_code=400, detail="invalid path")
    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(str(target))
