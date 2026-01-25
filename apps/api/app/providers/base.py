from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

@dataclass
class ProviderResult:
    outputs: dict[str, str]
    meta: dict[str, Any] | None = None

class Provider(Protocol):
    id: str
    name: str
    def capabilities(self) -> list[str]: ...
    def run(self, task: str, prompt: str, params: dict[str, Any], inputs: dict[str, Path], outputs_dir: Path) -> ProviderResult: ...
