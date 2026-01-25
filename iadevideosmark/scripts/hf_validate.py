#!/usr/bin/env python3
"""
Best-effort validation for Hugging Face Inference API.

It calls:
  POST https://api-inference.huggingface.co/models/<model_id>

Requires:
  HF_TOKEN env var (recommended)

Writes:
  outputs/hf_validation_<task>.json
  outputs/hf_validation_<task>.md
"""
from __future__ import annotations
import argparse
import json
import os
import time
from pathlib import Path
import urllib.request

def post_json(url: str, payload: dict, token: str | None, timeout: int = 90):
    headers = {"content-type": "application/json", "user-agent": "iadevideosmark/1.0"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), json.loads(r.read().decode("utf-8"))
    except Exception as e:
        # capture error response text if available
        try:
            if hasattr(e, "read"):
                return 0, {"error": e.read().decode("utf-8", errors="replace")}
        except Exception:
            pass
        return 0, {"error": str(e)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="text-to-image")
    ap.add_argument("--models_json", default="config/hf_models_autolist.json")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--sleep", type=float, default=1.0)
    args = ap.parse_args()

    token = os.getenv("HF_TOKEN")
    if not token:
        print("WARNING: HF_TOKEN not set. Many models will fail or be rate-limited.")

    models_doc = json.loads(Path(args.models_json).read_text(encoding="utf-8"))
    models = models_doc.get("models", [])[: args.limit]

    # Minimal payloads by task (best-effort)
    payload_by_task = {
        "text-to-image": {"inputs": "a cinematic photo of a chocolate ice cream cone, best quality, ultra detail"},
        "image-to-image": {"inputs": "turn it into a chocolate ice cream cone", "parameters": {"strength": 0.6}},
        "text-to-video": {"inputs": "a dog running in a park at sunset"},
    }
    payload = payload_by_task.get(args.task, {"inputs": "hello"})

    results = []
    for m in models:
        model_id = m["id"]
        url = f"https://api-inference.huggingface.co/models/{model_id}"
        code, resp = post_json(url, payload, token)
        ok = (code == 200) and ("error" not in resp)
        results.append({
            "model": model_id,
            "code": code,
            "ok": ok,
            "response_keys": list(resp.keys())[:30] if isinstance(resp, dict) else None,
            "error": resp.get("error") if isinstance(resp, dict) else None,
        })
        print(f"[{model_id}] ok={ok} code={code}")
        time.sleep(max(0.0, args.sleep))

    out_json = Path("outputs") / f"hf_validation_{args.task}.json"
    out_md = Path("outputs") / f"hf_validation_{args.task}.md"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps({"task": args.task, "results": results, "generated_at": time.time()}, indent=2), encoding="utf-8")

    # markdown summary
    ok_models = [r for r in results if r["ok"]]
    lines = [f"# HF validation ({args.task})", "", f"- total: {len(results)}", f"- ok: {len(ok_models)}", ""]
    for r in results:
        lines.append(f"- {'✅' if r['ok'] else '❌'} `{r['model']}` (code={r['code']}) {r.get('error') or ''}".strip())
    out_md.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {out_json} and {out_md}")

if __name__ == "__main__":
    main()
