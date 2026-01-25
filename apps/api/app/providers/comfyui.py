from __future__ import annotations

import json
import mimetypes
import re
import time
import uuid
import io
from pathlib import Path
from typing import Any, Iterable

import httpx
from PIL import Image

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

    def _coerce_numbers(self, obj: Any) -> Any:
        """Convert strings that look like numbers into int/float.

        This enables workflows to carry placeholders as strings (e.g. "__WIDTH__")
        and still validate in ComfyUI after replacement.
        """
        if isinstance(obj, str):
            s = obj.strip()
            if re.fullmatch(r"-?\d+", s):
                try:
                    return int(s)
                except Exception:
                    return obj
            if re.fullmatch(r"-?\d+\.\d+", s):
                try:
                    return float(s)
                except Exception:
                    return obj
            return obj
        if isinstance(obj, list):
            return [self._coerce_numbers(x) for x in obj]
        if isinstance(obj, dict):
            return {k: self._coerce_numbers(v) for k, v in obj.items()}
        return obj

    def _apply_prompt(self, wf: dict[str, Any], prompt: str, params: dict[str, Any], uploaded: dict[str, str] | None = None) -> dict[str, Any]:
        # Estratégia genérica: substitui placeholders em strings.
        # Use no workflow: __PROMPT__, __SEED__, __WIDTH__, __HEIGHT__, __FPS__, __DURATION_S__, __FRAMES__, __IMAGE__.
        seed = int(params.get("seed", 0) or 0) or int(time.time())
        width = int(params.get("width", 1024) or 1024)
        height = int(params.get("height", 1024) or 1024)
        fps = int(params.get("fps", 24) or 24)
        duration_s = float(params.get("duration_s", 6.0) or 6.0)
        frames = max(1, int(round(fps * max(0.1, duration_s))))

        image_name = (uploaded or {}).get("image", "")

        def replace(obj: Any) -> Any:
            if isinstance(obj, str):
                return (
                    obj.replace("__PROMPT__", prompt)
                       .replace("__SEED__", str(seed))
                       .replace("__WIDTH__", str(width))
                       .replace("__HEIGHT__", str(height))
                       .replace("__FPS__", str(fps))
                       .replace("__DURATION_S__", str(duration_s))
                       .replace("__FRAMES__", str(frames))
                       .replace("__IMAGE__", image_name)
                )
            if isinstance(obj, list):
                return [replace(x) for x in obj]
            if isinstance(obj, dict):
                return {k: replace(v) for k, v in obj.items()}
            return obj

        return self._coerce_numbers(replace(wf))

    def _upload_image_if_present(self, client: httpx.Client, inputs: dict[str, Path]) -> dict[str, str]:
        """Upload input image to ComfyUI so a LoadImage node can use it.

        ComfyUI typically requires the image be inside its input folder; the API endpoint
        /upload/image stores it there.
        """
        out: dict[str, str] = {}
        img = inputs.get("image")
        if img and img.exists():
            mime, _ = mimetypes.guess_type(str(img))
            mime = mime or "application/octet-stream"
            files = {"image": (img.name, img.read_bytes(), mime)}
            r = client.post(f"{self.base_url}/upload/image", files=files)
            r.raise_for_status()
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            # Some builds return {"name": "..."}
            name = data.get("name") or data.get("filename") or data.get("file")
            if not name:
                # fallback: some variants echo original filename
                name = img.name
            out["image"] = name
        return out

    def _iter_outputs(self, history: dict[str, Any], prompt_id: str) -> Iterable[dict[str, Any]]:
        """Yield output file descriptors from ComfyUI history."""
        h = history.get(prompt_id) if isinstance(history, dict) else None
        if not h and isinstance(history, dict):
            # Some builds return already at root
            h = history
        if not isinstance(h, dict):
            return []
        outputs = h.get("outputs") or {}
        if not isinstance(outputs, dict):
            return []
        for node_id, node_out in outputs.items():
            if not isinstance(node_out, dict):
                continue
            for key in ("images", "gifs", "videos"):
                items = node_out.get(key)
                if not isinstance(items, list):
                    continue
                for it in items:
                    if isinstance(it, dict) and it.get("filename"):
                        yield it

    def _download_view(self, client: httpx.Client, desc: dict[str, Any]) -> bytes:
        params = {
            "filename": desc.get("filename"),
            "subfolder": desc.get("subfolder", ""),
            "type": desc.get("type", "output"),
        }
        r = client.get(f"{self.base_url}/view", params=params)
        r.raise_for_status()
        return r.content

    def _save_image_bytes(self, data: bytes, out_path: Path, output_format: str, params: dict[str, Any]) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.open(io.BytesIO(data))
        fmt = (output_format or "jpeg").lower()
        if fmt in ("jpg", "jpeg"):
            q = int(params.get("jpeg_quality", 95) or 95)
            q = max(60, min(q, 100))
            out_path = out_path.with_suffix(".jpg")
            img.convert("RGB").save(out_path, format="JPEG", quality=q, optimize=True, subsampling=0)
            return out_path
        if fmt == "webp":
            q = int(params.get("webp_quality", 90) or 90)
            q = max(50, min(q, 100))
            out_path = out_path.with_suffix(".webp")
            img.save(out_path, format="WEBP", quality=q, method=6)
            return out_path
        # PNG
        out_path = out_path.with_suffix(".png")
        img.save(out_path, format="PNG")
        return out_path

    def run(self, task: str, prompt: str, params: dict[str, Any], inputs: dict[str, Path], outputs_dir: Path) -> ProviderResult:
        wf = self._load_workflow(task)

        # 1) Optionally upload inputs (image) so the workflow can reference it.
        #    Use __IMAGE__ placeholder in the LoadImage node.
        with httpx.Client(timeout=300) as client:
            uploaded = self._upload_image_if_present(client, inputs)
            wf = self._apply_prompt(wf, prompt, params, uploaded=uploaded)

            # 2) POST /prompt
            payload = {"prompt": wf, "client_id": str(uuid.uuid4())}
            r = client.post(f"{self.base_url}/prompt", json=payload)
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                raise RuntimeError(f"ComfyUI validation error: {data}")
            prompt_id = data.get("prompt_id") or data.get("prompt_id".upper()) or data.get("prompt_id".lower())
            if not prompt_id:
                # ComfyUI retorna prompt_id em data['prompt_id'] (docs); se não, devolve inteiro para debug
                raise RuntimeError(f"Resposta inesperada do ComfyUI: {data}")

            # 3) Poll /history/{prompt_id}
            deadline = time.time() + float(params.get("timeout_s", 300))
            history = None
            while time.time() < deadline:
                hr = client.get(f"{self.base_url}/history/{prompt_id}")
                if hr.status_code == 200:
                    history = hr.json()
                    # heurística: quando existe output
                    if isinstance(history, dict) and history.get(prompt_id):
                        break
                time.sleep(1.0)

            if history is None:
                raise RuntimeError("Timeout consultando /history do ComfyUI.")

        # Persistir histórico para inspeção + baixar primeiro output via /view.
        job_dir = outputs_dir / "jobs" / str(uuid.uuid4())
        job_dir.mkdir(parents=True, exist_ok=True)
        hist_path = job_dir / "comfy_history.json"
        hist_path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")

        outputs: dict[str, str] = {"history": str(hist_path.relative_to(outputs_dir))}
        meta: dict[str, Any] = {"mode": "comfyui", "prompt_id": prompt_id}

        # Download first file produced (image/video) and copy to our outputs folder.
        with httpx.Client(timeout=300) as client:
            # history returned by /history/<id> is a dict; entry is history[prompt_id]
            h_item = history.get(prompt_id) if isinstance(history, dict) else None
            if not isinstance(h_item, dict):
                raise RuntimeError("Histórico do ComfyUI não contém prompt_id; verifique o /history.")

            first = None
            for it in self._iter_outputs(history, prompt_id):
                first = it
                break
            if not first:
                raise RuntimeError("ComfyUI completou, mas não retornou outputs no /history. Verifique nós SaveImage/SaveVideo no workflow.")

            raw = self._download_view(client, first)
            fname = str(first.get("filename"))
            ext = (Path(fname).suffix or "").lower()
            out_base = job_dir / "output"
            requested_fmt = (params.get("output_format") or "jpeg").lower()

            if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
                saved = self._save_image_bytes(raw, out_base, requested_fmt, params)
                outputs["image"] = str(saved.relative_to(outputs_dir))
            else:
                # video or unknown binary; keep original extension when possible
                outp = out_base.with_suffix(ext if ext else ".bin")
                outp.write_bytes(raw)
                outputs["video" if ext in (".mp4", ".webm", ".gif", ".mov") else "file"] = str(outp.relative_to(outputs_dir))

        return ProviderResult(outputs=outputs, meta=meta)
