from __future__ import annotations
import json
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from .base import ProviderResult

class ComfyUIProvider:
    id = "comfyui"
    name = "ComfyUI (local)"

    def __init__(self, base_url: str, workflows_dir: Path):
        self.base_url = base_url.rstrip("/")
        self.workflows_dir = workflows_dir

    def capabilities(self) -> list[str]:
        return ["text_to_image","image_edit","image_upscale","text_to_video","image_to_video"]

    def _workflow_path(self, task: str) -> Path:
        mapping = {
            "text_to_image":"text_to_image.json",
            "image_edit":"image_edit.json",
            "image_upscale":"image_upscale.json",
            "text_to_video":"text_to_video.json",
            "image_to_video":"image_to_video.json",
        }
        name = mapping.get(task)
        if not name:
            raise RuntimeError(f"Task não suportada no ComfyUI: {task}")
        return self.workflows_dir / name

    def _load_workflow(self, task: str) -> dict[str, Any]:
        p = self._workflow_path(task)
        if not p.exists():
            raise RuntimeError(f"Workflow do ComfyUI não encontrado: {p}. Exporte um workflow do ComfyUI e salve com esse nome.")
        return json.loads(p.read_text(encoding="utf-8"))

    def _apply_prompt(self, wf: dict[str, Any], prompt: str, params: dict[str, Any]) -> dict[str, Any]:
        seed = int(params.get("seed", 0)) or int(time.time())
        def replace(obj):
            if isinstance(obj, str):
                return obj.replace("__PROMPT__", prompt).replace("__SEED__", str(seed))
            if isinstance(obj, list):
                return [replace(x) for x in obj]
            if isinstance(obj, dict):
                return {k: replace(v) for k, v in obj.items()}
            return obj
        return replace(wf)

    def run(self, task: str, prompt: str, params: dict[str, Any], inputs: dict[str, Path], outputs_dir: Path) -> ProviderResult:
        wf = self._apply_prompt(self._load_workflow(task), prompt, params)

        payload = {"prompt": wf, "client_id": str(uuid.uuid4())}
        with httpx.Client(timeout=120) as client:
            r = client.post(f"{self.base_url}/prompt", json=payload)
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                raise RuntimeError(f"ComfyUI validation error: {data}")
            prompt_id = data.get("prompt_id")
            if not prompt_id:
                raise RuntimeError(f"Resposta inesperada do ComfyUI: {data}")

            deadline = time.time() + float(params.get("timeout_s", 300))
            history = None
            while time.time() < deadline:
                hr = client.get(f"{self.base_url}/history/{prompt_id}")
                if hr.status_code == 200:
                    history = hr.json()
                    if isinstance(history, dict) and history.get(prompt_id):
                        break
                time.sleep(1.0)

        if history is None:
            raise RuntimeError("Timeout consultando /history do ComfyUI.")

        job_dir = outputs_dir / "jobs" / str(uuid.uuid4())
        job_dir.mkdir(parents=True, exist_ok=True)
        hist_path = job_dir / "comfy_history.json"
        hist_path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")

        return ProviderResult(outputs={"history": str(hist_path.relative_to(outputs_dir))}, meta={"mode":"comfyui","prompt_id": prompt_id})
