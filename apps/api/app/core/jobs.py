from __future__ import annotations
import json
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

@dataclass
class Job:
    id: str
    created_at: float
    status: str  # queued|running|succeeded|failed
    provider: str
    task: str
    prompt: str
    params: dict[str, Any]
    input_files: dict[str, str]
    outputs: dict[str, str]
    error: str | None = None
    meta: dict[str, Any] | None = None

def new_job(provider: str, task: str, prompt: str, params: dict[str, Any], input_files: dict[str, str]) -> Job:
    return Job(
        id=str(uuid.uuid4()),
        created_at=time.time(),
        status="queued",
        provider=provider,
        task=task,
        prompt=prompt,
        params=params,
        input_files=input_files,
        outputs={},
        error=None,
        meta={},
    )

def jobs_index_path(outputs_dir: Path) -> Path:
    return outputs_dir / "jobs.json"

def load_jobs(outputs_dir: Path) -> list[Job]:
    p = jobs_index_path(outputs_dir)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return [Job(**item) for item in data]

def save_jobs(outputs_dir: Path, jobs: list[Job]) -> None:
    outputs_dir.mkdir(parents=True, exist_ok=True)
    p = jobs_index_path(outputs_dir)
    p.write_text(json.dumps([asdict(j) for j in jobs], indent=2, ensure_ascii=False), encoding="utf-8")

def upsert_job(outputs_dir: Path, job: Job) -> None:
    jobs = load_jobs(outputs_dir)
    by_id = {j.id: j for j in jobs}
    by_id[job.id] = job
    save_jobs(outputs_dir, list(by_id.values()))

def get_job(outputs_dir: Path, job_id: str) -> Job | None:
    for j in load_jobs(outputs_dir):
        if j.id == job_id:
            return j
    return None
