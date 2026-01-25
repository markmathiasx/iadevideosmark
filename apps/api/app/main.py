from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .core.config import OUTPUTS_DIR, DEFAULT_PROVIDER, COMFYUI_URL, COMFYUI_WORKFLOWS_DIR
from .core.jobs import Job, new_job, get_job, upsert_job, load_jobs
from .core.safety import enforce, SafetyError
from .providers.registry import load_providers
from .utils.fs import safe_join

API_DIR = Path(__file__).resolve().parents[1]  # .../apps/api
REPO_ROOT = API_DIR.parent.parent             # repo root
CONFIG_DIR = REPO_ROOT / "config"
PROVIDERS_CFG_PATH = CONFIG_DIR / "providers.json"
POLICY_PATH = CONFIG_DIR / "content_policy.json"

app = FastAPI(title="iadevideosmark API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR), html=False), name="outputs")

providers_cfg, providers = load_providers(PROVIDERS_CFG_PATH, COMFYUI_URL, COMFYUI_WORKFLOWS_DIR)

def _save_upload(job_id: str, f: UploadFile, outputs_dir: Path) -> str:
    up_dir = outputs_dir / "uploads" / job_id
    up_dir.mkdir(parents=True, exist_ok=True)
    out_path = up_dir / f.filename
    with out_path.open("wb") as w:
        while True:
            chunk = f.file.read(1024 * 1024)
            if not chunk:
                break
            w.write(chunk)
    return str(out_path.relative_to(outputs_dir))

def _run_job(job: Job) -> None:
    try:
        job.status = "running"
        upsert_job(OUTPUTS_DIR, job)

        provider = providers.get(job.provider)
        if provider is None:
            raise RuntimeError(f"Provider desconhecido: {job.provider}")

        inputs_abs = {}
        for k, rel in (job.input_files or {}).items():
            inputs_abs[k] = safe_join(OUTPUTS_DIR, rel)

        res = provider.run(
            task=job.task,
            prompt=job.prompt,
            params=job.params or {},
            inputs=inputs_abs,
            outputs_dir=OUTPUTS_DIR,
        )
        job.outputs = res.outputs
        job.meta = res.meta or {}
        job.status = "succeeded"
        upsert_job(OUTPUTS_DIR, job)
    except Exception as e:
        job.status = "failed"
        job.error = str(e)
        upsert_job(OUTPUTS_DIR, job)

@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True}

@app.get("/providers")
def list_providers() -> dict[str, Any]:
    cfg = json.loads(PROVIDERS_CFG_PATH.read_text(encoding="utf-8"))
    out = []
    for p in cfg.get("providers", []):
        pid = p.get("id")
        inst = providers.get(pid)
        out.append({**p, "available": inst is not None})
    return {
        "default_provider": cfg.get("default_provider", DEFAULT_PROVIDER),
        "providers": out,
        "services_catalog": cfg.get("services_catalog", []),
    }

@app.post("/jobs")
async def create_job(
    background_tasks: BackgroundTasks,
    provider: str = Form(DEFAULT_PROVIDER),
    task: str = Form(...),
    prompt: str = Form(""),
    params: str = Form("{}"),
    image: Optional[UploadFile] = File(None),
    video: Optional[UploadFile] = File(None),
) -> dict[str, Any]:
    try:
        enforce(prompt or "", POLICY_PATH)
    except SafetyError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        params_obj = json.loads(params) if params else {}
    except Exception:
        raise HTTPException(status_code=400, detail="params deve ser JSON válido (string).")

    job = new_job(provider=provider, task=task, prompt=prompt or "", params=params_obj, input_files={})
    input_files: dict[str, str] = {}

    if image is not None:
        input_files["image"] = _save_upload(job.id, image, OUTPUTS_DIR)
    if video is not None:
        input_files["video"] = _save_upload(job.id, video, OUTPUTS_DIR)

    job.input_files = input_files
    upsert_job(OUTPUTS_DIR, job)

    background_tasks.add_task(_run_job, job)
    return {"id": job.id, "status": job.status}

@app.get("/jobs/{job_id}")
def get_job_status(job_id: str) -> dict[str, Any]:
    j = get_job(OUTPUTS_DIR, job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return j.__dict__

@app.get("/jobs")
def list_jobs(limit: int = 30) -> dict[str, Any]:
    jobs = sorted(load_jobs(OUTPUTS_DIR), key=lambda x: x.created_at, reverse=True)[: max(1, min(limit, 200))]
    return {"jobs": [j.__dict__ for j in jobs]}

@app.get("/files/{rel_path:path}")
def get_file(rel_path: str):
    p = safe_join(OUTPUTS_DIR, rel_path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    return FileResponse(str(p))
