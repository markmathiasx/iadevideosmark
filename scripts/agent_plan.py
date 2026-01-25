#!/usr/bin/env python3
"""
Gera um "plano" JSON (não é chain-of-thought) a partir de um comando em PT-BR,
usando um LLM local no Ollama (ex.: deepseek-r1-14b).

Uso:
  .\.venv\Scripts\python.exe scripts\agent_plan.py "bota um sorvete no lugar da cerveja" --image

Saída: JSON em stdout.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict

import httpx

DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "deepseek-r1:14b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

SYSTEM = """Você é um planejador para um app local de geração/edição de imagem/vídeo.
Transforme a instrução do usuário em um JSON curto com:
- task: um de ["text_to_image","image_edit","image_upscale","text_to_video","image_to_video","video_edit"]
- prompt: string final (PT-BR ok)
- params: {width:int,height:int,duration_s:float,fps:int,output_format:"jpeg|png|webp",jpeg_quality:int,webp_quality:int,video_format:"mp4|webm|gif"}
Regras:
- Se o usuário mencionou 'na imagem' ou forneceu imagem: prefira image_edit.
- Se pediu vídeo: use text_to_video ou image_to_video.
- Padrões: width=1024, height=1024, duration_s=6, fps=24, output_format="jpeg", jpeg_quality=95, video_format="mp4".
Responda APENAS com JSON válido (sem markdown)."""

def ollama_plan(model: str, user_text: str) -> Dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_text},
        ],
        "stream": False,
        "options": {"temperature": 0.2},
    }
    with httpx.Client(timeout=120) as c:
        r = c.post(f"{OLLAMA_URL}/api/chat", json=payload)
        r.raise_for_status()
        data = r.json()
        content = data.get("message", {}).get("content", "").strip()
        return json.loads(content)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("instruction")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args()

    plan = ollama_plan(args.model, args.instruction)
    print(json.dumps(plan, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
