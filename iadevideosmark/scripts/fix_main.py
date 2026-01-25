#!/usr/bin/env python3
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
main = root / "apps" / "api" / "main.py"
txt = main.read_text(encoding="utf-8")

# Fix "str(out_mp4)]    try:" on same line
txt2 = re.sub(r"(str\(out_mp4\)\])([ \t]+)(try:)", r"\1\n                \3", txt)

# Optional fallback for the specific "cmd = base + [...] try:" case
txt3 = re.sub(r"(cmd\s*=\s*base\s*\+\s*\[[^\r\n]+\])\s+try:", r"\1\n                try:", txt2)

if txt3 != txt:
    main.write_text(txt3, encoding="utf-8")
    print("OK: patched main.py")
else:
    print("SKIP: no patch applied (pattern not found)")

# ensure __init__.py
(root / "apps" / "__init__.py").touch(exist_ok=True)
(root / "apps" / "api" / "__init__.py").touch(exist_ok=True)
