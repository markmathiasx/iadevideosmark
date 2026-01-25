from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any

class SafetyError(ValueError):
    pass

def load_policy(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"blocked": {}}

def normalize(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s

def is_blocked(prompt: str, policy: dict[str, Any]) -> tuple[bool, str]:
    p = normalize(prompt)
    blocked = policy.get("blocked", {}) or {}
    for category, needles in blocked.items():
        for n in (needles or []):
            if normalize(n) in p:
                return True, f"blocked:{category}"
    if re.search(r"(\b(nude|naked)\b.*\b(child|kid|minor)\b)|(\b(child|kid|minor)\b.*\b(nude|naked)\b)", p):
        return True, "blocked:minors"
    return False, ""

def enforce(prompt: str, policy_path: Path) -> None:
    policy = load_policy(policy_path)
    blocked, reason = is_blocked(prompt, policy)
    if blocked:
        raise SafetyError(f"Prompt bloqueado pela política local ({reason}).")
