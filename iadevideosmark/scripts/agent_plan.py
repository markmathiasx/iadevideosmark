#!/usr/bin/env python3
"""
Turn a natural-language instruction into a *job plan* JSON.

Backends supported:
- Ollama (local): POST /api/chat (recommended for DeepSeek R1-14B)
- OpenAI (optional): chat completions (requires OPENAI_API_KEY)

This does NOT expose "chain-of-thought". It outputs an auditable plan.
"""
from __future__ import annotations
import argparse
import json
import os
import urllib.request

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:14b")

SYSTEM = """Você é um planejador de jobs para um app multimídia. Gere SOMENTE JSON.
Esquema:
{
  "provider": "mock|comfyui|huggingface|openai",
  "task": "text_to_image|image_edit|image_upscale|image_to_video|text_to_video",
  "prompt": "string",
  "width": 1280,
  "height": 1024,
  "duration_s": 6,
  "fps": 24,
  "output_format": "jpeg|png|mp4",
  "output_profile": "draft|high|ultra",
  "output_subdir": "jobs",
  "jpeg_quality": 95
}
Regras:
- Se o pedido for editar uma imagem (trocar um objeto), use task=image_edit.
- Se pedir vídeo a partir de imagem: image_to_video. A partir de texto: text_to_video.
- Sempre setar output_format correto (mp4 em vídeo, jpeg em imagem).
- Se faltar info, use defaults seguros (1280x1024, 6s, 24fps, high, jpeg 95).
"""

def post_json(url: str, payload: dict, timeout: int = 60):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"content-type":"application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def ollama_plan(text: str, hint_task: str | None = None, hint_provider: str | None = None):
    url = f"{OLLAMA_HOST}/api/chat"
    user = text if not hint_task else f"{text}\n\n(hint_task={hint_task}, hint_provider={hint_provider})"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role":"system","content": SYSTEM},
            {"role":"user","content": user},
        ],
        "stream": False,
        "options": {"temperature": 0.2},
    }
    resp = post_json(url, payload)
    content = resp.get("message", {}).get("content", "").strip()
    return json.loads(content)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("--hint_task", default=None)
    ap.add_argument("--hint_provider", default=None)
    args = ap.parse_args()

    plan = ollama_plan(args.text, args.hint_task, args.hint_provider)
    print(json.dumps(plan, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
