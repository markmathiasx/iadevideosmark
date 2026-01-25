#!/usr/bin/env python3
"""
Baixa automaticamente listas (top 100 por downloads) de modelos do Hugging Face
para várias tasks e grava em config/hf_models_autolist.json.

Uso (na raiz do projeto):
  .\.venv\Scripts\python.exe scripts\hf_discover.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List
import time

import httpx

HF_API = "https://huggingface.co/api/models"

TASK_TO_PIPELINE = {
    "text_to_image": "text-to-image",
    "image_to_image": "image-to-image",
    "text_to_video": "text-to-video",
    "image_to_video": "image-to-video",
    "text_generation": "text-generation",
}

def fetch_models(pipeline_tag: str, limit: int = 100) -> List[dict]:
    params = {
        "pipeline_tag": pipeline_tag,
        "sort": "downloads",
        "direction": -1,
        "limit": limit,
    }
    with httpx.Client(timeout=60) as c:
        r = c.get(HF_API, params=params)
        r.raise_for_status()
        return r.json()

def main() -> None:
    out = {"generated_at": int(time.time()), "by_task": {}}
    for task, tag in TASK_TO_PIPELINE.items():
        models = fetch_models(tag, limit=100)
        # mantém só o essencial
        out["by_task"][task] = [
            {
                "id": m.get("modelId") or m.get("id"),
                "downloads": m.get("downloads"),
                "likes": m.get("likes"),
                "pipeline_tag": m.get("pipeline_tag") or tag,
                "library": m.get("library_name"),
            }
            for m in models
            if (m.get("modelId") or m.get("id"))
        ]

    Path("config").mkdir(exist_ok=True)
    p = Path("config/hf_models_autolist.json")
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] wrote {p}")

if __name__ == "__main__":
    main()
