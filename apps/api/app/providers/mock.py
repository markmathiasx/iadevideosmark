from __future__ import annotations
import os
import subprocess
import textwrap
import time
import uuid
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .base import ProviderResult

class MockProvider:
    id = "mock"
    name = "Mock (offline)"

    def capabilities(self) -> list[str]:
        return ["text_to_image","image_edit","image_upscale","text_to_video","image_to_video","video_edit"]

    def _write_image(self, out_path: Path, title: str, prompt: str, size: tuple[int,int]) -> None:
        w, h = size
        img = Image.new("RGB", (w, h), (20, 20, 20))
        d = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 22)
        except Exception:
            font = ImageFont.load_default()

        d.text((20, 20), title, font=font, fill=(240,240,240))
        wrapped = textwrap.fill(prompt, width=60)
        d.text((20, 70), wrapped, font=font, fill=(200,200,200))
        d.text((20, h-40), time.strftime("%Y-%m-%d %H:%M:%S"), font=font, fill=(160,160,160))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, format="PNG")

    def _require_ffmpeg(self) -> None:
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=False)
        except FileNotFoundError:
            raise RuntimeError("FFmpeg não encontrado no PATH. Instale/adapte o PATH para gerar vídeo no modo mock.")

    def _write_video(self, out_path: Path, prompt: str, duration_s: float, fps: int, size: tuple[int,int]) -> None:
        self._require_ffmpeg()
        w, h = size
        duration_s = float(duration_s)
        if duration_s <= 0:
            duration_s = 6.0
        if duration_s < 1.0:
            duration_s = 1.0
        if duration_s > 60.0:
            duration_s = 60.0

        fontfile = "arial.ttf"
        if os.name == "nt":
            fontfile = "C\\:/Windows/Fonts/arial.ttf"

        safe_prompt = prompt.replace(":", "\\:").replace("'", "\\'")
        draw = (
            "drawtext=fontfile=" + fontfile + ":"
            "text='%{eif\\:t\\:d} s - " + safe_prompt + "':"
            "x=20:y=H-60:fontsize=24:fontcolor=white:box=1:boxcolor=black@0.5"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x202020:s={w}x{h}:r={fps}",
            "-t", f"{duration_s}",
            "-vf", draw,
            "-pix_fmt", "yuv420p",
            str(out_path),
        ]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError("FFmpeg falhou: " + (p.stderr[-800:] if p.stderr else "unknown error"))

    def run(self, task: str, prompt: str, params: dict[str, Any], inputs: dict[str, Path], outputs_dir: Path) -> ProviderResult:
        job_dir = outputs_dir / "jobs" / str(uuid.uuid4())
        if task in ("text_to_image","image_edit","image_upscale"):
            w = int(params.get("width", 768))
            h = int(params.get("height", 768))
            out_path = job_dir / "image.png"
            self._write_image(out_path, f"MOCK {task}", prompt, (w, h))
            return ProviderResult(outputs={"image": str(out_path.relative_to(outputs_dir))}, meta={"mode":"mock"})
        if task in ("text_to_video","image_to_video","video_edit"):
            w = int(params.get("width", 768))
            h = int(params.get("height", 432))
            fps = int(params.get("fps", 24))
            duration_s = float(params.get("duration_s", 6.0))
            out_path = job_dir / "video.mp4"
            self._write_video(out_path, prompt, duration_s, fps, (w, h))
            return ProviderResult(outputs={"video": str(out_path.relative_to(outputs_dir))}, meta={"mode":"mock","duration_s":duration_s})
        raise RuntimeError(f"Task não suportada no mock: {task}")
