from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def get_env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if v is not None and v != "" else default

API_HOST = get_env("API_HOST", "127.0.0.1")
API_PORT = int(get_env("API_PORT", "8000") or "8000")
OUTPUTS_DIR = Path(get_env("OUTPUTS_DIR", "outputs") or "outputs")
DEFAULT_PROVIDER = get_env("DEFAULT_PROVIDER", "mock") or "mock"

COMFYUI_URL = get_env("COMFYUI_URL", "http://127.0.0.1:8188") or "http://127.0.0.1:8188"
COMFYUI_WORKFLOWS_DIR = Path(get_env("COMFYUI_WORKFLOWS_DIR", "config/comfyui_workflows") or "config/comfyui_workflows")
