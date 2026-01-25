from __future__ import annotations
from pathlib import Path
from fastapi import HTTPException

def safe_join(base: Path, rel: str) -> Path:
    target = (base / rel).resolve()
    base_resolved = base.resolve()
    if base_resolved not in target.parents and target != base_resolved:
        raise HTTPException(status_code=400, detail="Invalid path")
    return target
