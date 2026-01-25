#!/usr/bin/env python3
"""
Valida (best-effort) modelos do Hugging Face via Inference API serverless.

Requisitos:
- Defina HF_TOKEN no ambiente (Settings > Access Tokens no Hugging Face).
- Rode scripts/hf_discover.py antes (gera config/hf_models_autolist.json).

Exemplos:
  setx HF_TOKEN "hf_..."
  .\.venv\Scripts\python.exe scripts\hf_validate.py --task text_to_image --limit 30

Saídas:
- outputs/hf_validation_<task>.json
- outputs/hf_validation_<task>.md
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import httpx

HF_TOKEN = os.environ.get("HF_TOKEN", "").strip()
INFER_URL = "https://api-inference.huggingface.co/models"

DEFAULT_PROMPTS = {
    "text_to_image": "um anão ruivo em uma taverna segurando um sorvete de chocolate no lugar de uma caneca de cerveja, ultra detalhado, cinematic lighting",
    "text_generation": "Crie um prompt detalhado (PT-BR) para gerar uma imagem: anão ruivo na taverna segurando um sorvete no lugar da cerveja.",
    "text_to_video": "um anão ruivo em uma taverna segurando um sorvete de chocolate no lugar de uma caneca de cerveja, cinematic, 6 seconds, 24fps",
}

def load_models(task: str) -> List[str]:
    p = Path("config/hf_models_autolist.json")
    data = json.loads(p.read_text(encoding="utf-8"))
    items = data["by_task"].get(task, [])
    return [it["id"] for it in items if it.get("id")]

def infer_json(model_id: str, payload: Dict[str, Any], timeout_s: int = 180) -> Tuple[bool, float, str]:
    if not HF_TOKEN:
        return False, 0.0, "missing HF_TOKEN"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout_s) as c:
            r = c.post(f"{INFER_URL}/{model_id}", headers=headers, json=payload)
            dt = time.perf_counter() - t0
            if r.status_code == 200:
                return True, dt, "ok"
            # HF costuma retornar JSON com erro
            try:
                msg = r.json()
            except Exception:
                msg = r.text[:400]
            return False, dt, f"{r.status_code}: {msg}"
    except Exception as e:
        dt = time.perf_counter() - t0
        return False, dt, repr(e)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True, choices=["text_to_image","text_generation","text_to_video"])
    ap.add_argument("--limit", type=int, default=30, help="Quantos modelos testar (rate limit pode bloquear >30).")
    ap.add_argument("--sleep", type=float, default=0.6, help="Delay entre requests (evita 429).")
    ap.add_argument("--prompt", default=None)
    args = ap.parse_args()

    models = load_models(args.task)[: max(1, args.limit)]
    prompt = args.prompt or DEFAULT_PROMPTS[args.task]

    if args.task == "text_to_image":
        payload = {"inputs": prompt}
    elif args.task == "text_to_video":
        payload = {"inputs": prompt}
    else:
        payload = {"inputs": prompt}

    out_rows = []
    for i, mid in enumerate(models, 1):
        ok, dt, msg = infer_json(mid, payload)
        out_rows.append({"model": mid, "ok": ok, "latency_s": round(dt, 3), "msg": msg})
        print(f"[{i:03d}/{len(models):03d}] {mid} -> {'OK' if ok else 'FAIL'} ({dt:.2f}s)")
        time.sleep(max(0.0, args.sleep))

    Path("outputs").mkdir(exist_ok=True)
    out_json = Path(f"outputs/hf_validation_{args.task}.json")
    out_json.write_text(json.dumps(out_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    # markdown resumo
    ok_rows = [r for r in out_rows if r["ok"]]
    fail_rows = [r for r in out_rows if not r["ok"]]
    md = [f"# HF validation — {args.task}", "", f"Testados: {len(out_rows)}", f"OK: {len(ok_rows)}", f"FAIL: {len(fail_rows)}", ""]
    md.append("## Top OK (por menor latência)")
    md.append("")
    for r in sorted(ok_rows, key=lambda x: x["latency_s"])[:15]:
        md.append(f"- {r['model']} — {r['latency_s']}s")
    md.append("")
    md.append("## Falhas (primeiros 20)")
    md.append("")
    for r in fail_rows[:20]:
        md.append(f"- {r['model']} — {r['msg']}")
    out_md = Path(f"outputs/hf_validation_{args.task}.md")
    out_md.write_text("\n".join(md), encoding="utf-8")

    print(f"[ok] wrote {out_json}")
    print(f"[ok] wrote {out_md}")

if __name__ == "__main__":
    main()
