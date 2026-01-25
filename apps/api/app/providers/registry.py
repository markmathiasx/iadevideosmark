from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from .mock import MockProvider
from .comfyui import ComfyUIProvider

def load_providers(config_path: Path, comfyui_url: str, comfyui_workflows_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    providers: dict[str, Any] = {
        "mock": MockProvider(),
        "comfyui": ComfyUIProvider(comfyui_url, comfyui_workflows_dir),
    }
    return cfg, providers
