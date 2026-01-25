from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

# Project output root
OUTPUTS_DIR = Path(os.getenv("OUTPUTS_DIR", "outputs")).resolve()
JOBS_DIR = OUTPUTS_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

# ---------- helpers ----------

def _safe_job_dir(job_id: str, subdir: Optional[str] = None) -> Path:
    job_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", job_id)[:80] or "job"
    base = JOBS_DIR
    if subdir:
        # allow nested, but sanitize each segment
        parts = [re.sub(r"[^a-zA-Z0-9_\-]", "_", p) for p in subdir.replace("\\", "/").split("/") if p]
        if parts:
            base = OUTPUTS_DIR / "/".join(parts)
    p = (base / job_id).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p

def _escape_drawtext(s: str) -> str:
    # ffmpeg drawtext escaping rules: backslash-escape special chars like ':' and '\''
    s = s.replace("\\", r"\\")
    s = s.replace(":", r"\:")
    s = s.replace("'", r"\'")
    s = s.replace("%", r"\%")
    s = s.replace("\n", r"\n")
    return s

def _ffmpeg_font_opt() -> str:
    """
    Prefer portable font selection.
    - On Windows, ffmpeg can use system font by name: font='Arial'
    - On Linux container, DejaVu Sans is typically available.
    """
    return "font='DejaVu Sans'" if os.name != "nt" else "font='Arial'"

def _run_ffmpeg(args: list[str]) -> Tuple[int, str]:
    # run without shell to avoid quoting issues
    proc = subprocess.run(args, capture_output=True, text=True)
    stderr = (proc.stderr or "") + (proc.stdout or "")
    return proc.returncode, stderr.strip()

def _best_image_size(w: int, h: int, quality: str) -> Tuple[int, int]:
    # upscale preset for mock (does not create real details; just bigger canvas)
    q = (quality or "").lower()
    mult = 1
    if q == "high":
        mult = 2
    elif q == "ultra":
        mult = 3
    return max(64, int(w * mult)), max(64, int(h * mult))

def _save_jpeg(img: Image.Image, path: Path, quality: int = 95) -> None:
    img = img.convert("RGB")
    img.save(path, format="JPEG", quality=max(60, min(quality, 100)), optimize=True, progressive=True)

def _pillow_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # avoid hardcoded font paths; use default if truetype not available
    try:
        return ImageFont.truetype("arial.ttf", size=size)
    except Exception:
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size=size)
        except Exception:
            return ImageFont.load_default()

def _ensure_ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        return True
    except Exception:
        return False

# ---------- mock provider ----------

@dataclass
class ProviderResult:
    ok: bool
    output_path: Optional[str] = None
    mime: Optional[str] = None
    error: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class MockProvider:
    """
    Placeholder provider:
    - Text/Image operations: Pillow
    - Video operations: FFmpeg (renders a still frame with drawtext)

    IMPORTANT: This does NOT do real AI editing/generation.
    """

    name = "mock"

    def text_to_image(self, *, job_id: str, prompt: str, width: int, height: int,
                      output_format: str = "jpeg", quality_profile: str = "high",
                      jpeg_quality: int = 95, output_subdir: Optional[str] = None) -> ProviderResult:
        try:
            w, h = _best_image_size(width, height, quality_profile)
            img = Image.new("RGB", (w, h), (20, 20, 24))
            d = ImageDraw.Draw(img)
            font = _pillow_font(max(16, int(min(w, h) * 0.035)))
            d.text((24, 24), "MOCK text_to_image", font=font, fill=(220, 220, 220))
            font2 = _pillow_font(max(14, int(min(w, h) * 0.03)))
            d.text((24, 90), (prompt or "").strip()[:500], font=font2, fill=(210, 210, 210))
            out_dir = _safe_job_dir(job_id, output_subdir)
            ext = "jpg" if output_format.lower() in ("jpg", "jpeg") else "png"
            out_path = out_dir / f"image.{ext}"
            if ext == "jpg":
                _save_jpeg(img, out_path, quality=jpeg_quality)
                mime = "image/jpeg"
            else:
                img.save(out_path, format="PNG", optimize=True)
                mime = "image/png"
            return ProviderResult(ok=True, output_path=str(out_path), mime=mime, meta={"provider":"mock"})
        except Exception as e:
            return ProviderResult(ok=False, error=str(e), meta={"provider":"mock"})

    def image_edit(self, *, job_id: str, prompt: str, input_image_path: str, width: int, height: int,
                   output_format: str = "jpeg", quality_profile: str = "high",
                   jpeg_quality: int = 95, output_subdir: Optional[str] = None) -> ProviderResult:
        try:
            base = Image.open(input_image_path).convert("RGB")
            w, h = _best_image_size(width or base.width, height or base.height, quality_profile)
            base = base.resize((w, h))
            d = ImageDraw.Draw(base)
            font = _pillow_font(max(16, int(min(w, h) * 0.035)))
            d.rectangle([0, 0, w, int(min(h, 110))], fill=(0, 0, 0))
            d.text((18, 18), "MOCK image_edit", font=font, fill=(230, 230, 230))
            font2 = _pillow_font(max(14, int(min(w, h) * 0.03)))
            d.text((18, 62), (prompt or "").strip()[:500], font=font2, fill=(230, 230, 230))
            out_dir = _safe_job_dir(job_id, output_subdir)
            ext = "jpg" if output_format.lower() in ("jpg", "jpeg") else "png"
            out_path = out_dir / f"image_edit.{ext}"
            if ext == "jpg":
                _save_jpeg(base, out_path, quality=jpeg_quality)
                mime = "image/jpeg"
            else:
                base.save(out_path, format="PNG", optimize=True)
                mime = "image/png"
            return ProviderResult(ok=True, output_path=str(out_path), mime=mime, meta={"provider":"mock"})
        except Exception as e:
            return ProviderResult(ok=False, error=str(e), meta={"provider":"mock"})

    def image_upscale(self, *, job_id: str, prompt: str, input_image_path: str, width: int, height: int,
                      output_format: str = "jpeg", quality_profile: str = "ultra",
                      jpeg_quality: int = 95, output_subdir: Optional[str] = None) -> ProviderResult:
        # upscale = resize; no real detail reconstruction in mock.
        try:
            base = Image.open(input_image_path).convert("RGB")
            w, h = _best_image_size(width or base.width, height or base.height, quality_profile)
            base = base.resize((w, h))
            out_dir = _safe_job_dir(job_id, output_subdir)
            ext = "jpg" if output_format.lower() in ("jpg", "jpeg") else "png"
            out_path = out_dir / f"upscaled.{ext}"
            if ext == "jpg":
                _save_jpeg(base, out_path, quality=jpeg_quality)
                mime = "image/jpeg"
            else:
                base.save(out_path, format="PNG", optimize=True)
                mime = "image/png"
            return ProviderResult(ok=True, output_path=str(out_path), mime=mime, meta={"provider":"mock"})
        except Exception as e:
            return ProviderResult(ok=False, error=str(e), meta={"provider":"mock"})

    def image_to_video(self, *, job_id: str, prompt: str, input_image_path: str, width: int, height: int,
                       duration_s: float, fps: int = 24, output_subdir: Optional[str] = None) -> ProviderResult:
        if duration_s is None or duration_s <= 0:
            duration_s = 6.0
        duration_s = max(1.0, float(duration_s))
        fps = max(1, int(fps or 24))
        if not _ensure_ffmpeg_available():
            return ProviderResult(ok=False, error="FFmpeg não encontrado no PATH.", meta={"provider":"mock"})
        try:
            out_dir = _safe_job_dir(job_id, output_subdir)
            out_path = out_dir / "video.mp4"
            font_opt = _ffmpeg_font_opt()
            text = _escape_drawtext((prompt or "").strip()[:400])
            vf = (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
                f"drawtext={font_opt}:text='{text}':x=24:y=24:fontsize=24:"
                f"fontcolor=white:box=1:boxcolor=black@0.5"
            )
            args = [
                "ffmpeg",
                "-y",
                "-loop", "1",
                "-i", input_image_path,
                "-t", f"{duration_s:.3f}",
                "-r", str(fps),
                "-vf", vf,
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                str(out_path),
            ]
            code, logs = _run_ffmpeg(args)
            if code != 0:
                return ProviderResult(ok=False, error=f"FFmpeg falhou: {logs}", meta={"provider":"mock"})
            return ProviderResult(ok=True, output_path=str(out_path), mime="video/mp4", meta={"provider":"mock"})
        except Exception as e:
            return ProviderResult(ok=False, error=str(e), meta={"provider":"mock"})

    def text_to_video(self, *, job_id: str, prompt: str, width: int, height: int,
                      duration_s: float, fps: int = 24, output_subdir: Optional[str] = None) -> ProviderResult:
        # Create a solid background and draw text; then encode as mp4.
        if duration_s is None or duration_s <= 0:
            duration_s = 6.0
        duration_s = max(1.0, float(duration_s))
        fps = max(1, int(fps or 24))
        if not _ensure_ffmpeg_available():
            return ProviderResult(ok=False, error="FFmpeg não encontrado no PATH.", meta={"provider":"mock"})
        try:
            out_dir = _safe_job_dir(job_id, output_subdir)
            out_path = out_dir / "video.mp4"
            font_opt = _ffmpeg_font_opt()
            text = _escape_drawtext((prompt or "").strip()[:400])
            vf = (
                f"color=c=#141418:s={width}x{height}:r={fps},"
                f"drawtext={font_opt}:text='MOCK text_to_video':x=24:y=24:fontsize=26:"
                f"fontcolor=white:box=1:boxcolor=black@0.5,"
                f"drawtext={font_opt}:text='{text}':x=24:y=80:fontsize=22:"
                f"fontcolor=white:box=1:boxcolor=black@0.35"
            )
            args = [
                "ffmpeg","-y",
                "-f","lavfi","-i",vf,
                "-t",f"{duration_s:.3f}",
                "-c:v","libx264","-pix_fmt","yuv420p",
                str(out_path)
            ]
            code, logs = _run_ffmpeg(args)
            if code != 0:
                return ProviderResult(ok=False, error=f"FFmpeg falhou: {logs}", meta={"provider":"mock"})
            return ProviderResult(ok=True, output_path=str(out_path), mime="video/mp4", meta={"provider":"mock"})
        except Exception as e:
            return ProviderResult(ok=False, error=str(e), meta={"provider":"mock"})
