#!/usr/bin/env python3
"""
Discover top models on Hugging Face Hub by task/pipeline_tag.

Writes:
  - config/hf_models_autolist.json
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import time
import urllib.parse
import urllib.request

HF_API = "https://huggingface.co/api/models"

def http_get_json(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"user-agent": "iadevideosmark/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="text-to-image", help="pipeline_tag (ex.: text-to-image, image-to-image, text-to-video)")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--sort", default="downloads", choices=["downloads", "likes", "lastModified"])
    ap.add_argument("--out", default="config/hf_models_autolist.json")
    args = ap.parse_args()

    qs = {
        "pipeline_tag": args.task,
        "sort": args.sort,
        "direction": "-1",
        "limit": str(args.limit),
        "full": "true",
    }
    url = HF_API + "?" + urllib.parse.urlencode(qs)
    data = http_get_json(url)
    out = []
    for m in data:
        out.append({
            "id": m.get("id"),
            "pipeline_tag": m.get("pipeline_tag"),
            "downloads": m.get("downloads"),
            "likes": m.get("likes"),
            "library_name": m.get("library_name"),
            "tags": m.get("tags", [])[:30],
            "private": m.get("private", False),
            "gated": m.get("gated", False),
        })

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({
        "generated_at": time.time(),
        "task": args.task,
        "models": out,
    }, indent=2), encoding="utf-8")

    print(f"Wrote {args.out} with {len(out)} models for task={args.task}")

if __name__ == "__main__":
    main()
