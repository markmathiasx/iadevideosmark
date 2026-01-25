from __future__ import annotations

import os
import platform
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

    def _img_target(self, task: str, params: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
        """Return (extension, PIL_format, save_kwargs)."""
        fmt = (params.get("output_format") or "jpeg").lower().strip()
        if fmt in ("jpg", "jpeg"):
            q = int(params.get("jpeg_quality", 95) or 95)
            q = max(60, min(q, 100))
            return ("jpg", "JPEG", {"quality": q, "optimize": True, "subsampling": 0})
        if fmt == "webp":
            q = int(params.get("webp_quality", 90) or 90)
            q = max(50, min(q, 100))
            return ("webp", "WEBP", {"quality": q, "method": 6})
        # default: PNG
        return ("png", "PNG", {})

    def _write_image(self, out_path: Path, title: str, prompt: str, size: tuple[int,int], pil_format: str, save_kwargs: dict[str, Any]) -> None:
        w, h = size
        img = Image.new("RGB", (w, h), (20, 20, 20))
        d = ImageDraw.Draw(img)
        # Fonte: tenta padrão; se falhar, usa default
        try:
            font = ImageFont.truetype("arial.ttf", 22)
        except Exception:
            font = ImageFont.load_default()

        d.text((20, 20), title, font=font, fill=(240,240,240))
        wrapped = textwrap.fill(prompt, width=60)
        d.text((20, 70), wrapped, font=font, fill=(200,200,200))
        d.text((20, h-40), time.strftime("%Y-%m-%d %H:%M:%S"), font=font, fill=(160,160,160))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, format=pil_format, **(save_kwargs or {}))

    def _require_ffmpeg(self) -> None:
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=False)
        except FileNotFoundError:
            raise RuntimeError("FFmpeg não encontrado no PATH. Instale ou adicione ao PATH para gerar vídeo no modo mock.")

    def _ffmpeg_font_opt(self) -> str:
    """Return drawtext font option prefix ending with ':' or empty string.

    Nota: no Windows, evitar 'fontfile=C:\...'(drive ':') porque o parser do
    filtro drawtext é sensível a ':' e costuma quebrar. Preferimos nome de fonte.
    """
    sys = platform.system().lower()
    if "windows" in sys:
        # Usa o nome da fonte (sem caminho) para evitar problemas de escaping.
        return "font=Arial:"
    # Linux/macOS: best effort com fontfile (mais estável nessas plataformas).
    for cand in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ):
        if Path(cand).exists():
            return f"fontfile={cand}:"
    return ""
def _escape_drawtext(self, s: str) -> str:
        # Minimal escaping for ffmpeg drawtext filter parser
        return (
            s.replace("\\\\", "\\\\\\\\")
             .replace(":", "\\\\:")
             .replace("'", "\\\\'")
        )

    def _write_video(self, out_path: Path, prompt: str, duration_s: float, fps: int, size: tuple[int,int], video_format: str = "mp4") -> None:
        self._require_ffmpeg()
        w, h = size
        duration_s = float(duration_s)
        if duration_s <= 0:
            duration_s = 6.0
        if duration_s < 1.0:
            duration_s = 1.0
        if duration_s > 60.0:
            duration_s = 60.0

        # Vídeo colorido + drawtext (placeholder). Se drawtext falhar (font/escape),
        # fazemos fallback para um vídeo simples sem overlay (para não quebrar o pipeline).
        font_opt = self._ffmpeg_font_opt()
        safe_prompt = self._escape_drawtext(prompt or "")
        draw = (
            "drawtext="
            + font_opt
            + "text='%{eif\\:t\\:d} s - "
            + safe_prompt
            + "':x=20:y=H-60:fontsize=24:fontcolor=white:box=1:boxcolor=black@0.5"
        )

        video_format = (video_format or "mp4").lower()
        if video_format not in ("mp4", "webm", "gif"):
            video_format = "mp4"

        base = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x202020:s={w}x{h}:r={fps}",
            "-t", f"{duration_s}",
        ]

        def cmd_with_vf(vf: str | None) -> list[str]:
            cmd = base.copy()
            if vf:
                cmd += ["-vf", vf]
            if video_format == "webm":
                # Pode falhar se seu ffmpeg não tiver vp9; nesse caso faremos fallback.
                cmd += ["-c:v", "libvpx-vp9", "-crf", "33", "-b:v", "0", "-pix_fmt", "yuv420p"]
            elif video_format == "gif":
                cmd += ["-f", "gif"]
            else:
                cmd += ["-pix_fmt", "yuv420p", "-movflags", "+faststart"]
            cmd += [str(out_path)]
            return cmd

        out_path.parent.mkdir(parents=True, exist_ok=True)

        # 1) tenta com drawtext
        p = subprocess.run(cmd_with_vf(draw), capture_output=True, text=True)
        if p.returncode != 0:
            # 2) fallback: sem drawtext
            p2 = subprocess.run(cmd_with_vf(None), capture_output=True, text=True)
            if p2.returncode != 0 and video_format in ("webm", "gif"):
                # 3) fallback final: mp4
                video_format = "mp4"
                out_path_mp4 = out_path.with_suffix(".mp4")
                p3 = subprocess.run(
                    [
                        "ffmpeg","-y","-f","lavfi",
                        "-i", f"color=c=0x202020:s={w}x{h}:r={fps}",
                        "-t", f"{duration_s}",
                        "-pix_fmt","yuv420p",
                        "-movflags","+faststart",
                        str(out_path_mp4),
                    ],
                    capture_output=True,
                    text=True,
                )
                if p3.returncode != 0:
                    raise RuntimeError("FFmpeg falhou: " + (p3.stderr[-800:] if p3.stderr else "unknown error"))
                return
            if p2.returncode != 0:
                raise RuntimeError("FFmpeg falhou: " + (p2.stderr[-800:] if p2.stderr else "unknown error"))

    def run(self, task: str, prompt: str, params: dict[str, Any], inputs: dict[str, Path], outputs_dir: Path) -> ProviderResult:
        job_dir = outputs_dir / "jobs" / str(uuid.uuid4())
        if task in ("text_to_image","image_edit","image_upscale"):
            w = int(params.get("width", 1024))
            h = int(params.get("height", 1024))
            ext, pil_fmt, save_kwargs = self._img_target(task, params)
            out_path = job_dir / f"image.{ext}"
            title = f"MOCK {task}"
            self._write_image(out_path, title, prompt, (w, h), pil_fmt, save_kwargs)
            return ProviderResult(outputs={"image": str(out_path.relative_to(outputs_dir))}, meta={"mode":"mock"})
        elif task in ("text_to_video","image_to_video","video_edit"):
            w = int(params.get("width", 1280))
            h = int(params.get("height", 720))
            fps = int(params.get("fps", 24))
            duration_s = float(params.get("duration_s", 6.0))
            video_fmt = str(params.get("video_format", "mp4")).lower()
            ext = "mp4"
            if video_fmt == "webm":
                ext = "webm"
            elif video_fmt == "gif":
                ext = "gif"
            out_path = job_dir / f"video.{ext}"
            self._write_video(out_path, prompt, duration_s, fps, (w, h), video_fmt)
            return ProviderResult(outputs={"video": str(out_path.relative_to(outputs_dir))}, meta={"mode":"mock","duration_s":duration_s,"video_format":video_fmt})
        else:
            raise RuntimeError(f"Task não suportada no mock: {task}")