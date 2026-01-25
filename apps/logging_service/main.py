from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

OUTPUTS_DIR = Path("outputs").resolve()
JOBS_DIR = OUTPUTS_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="logs_viewer", version="0.1.0")


def _list_jobs() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not JOBS_DIR.exists():
        return out
    for d in sorted(JOBS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        item: Dict[str, Any] = {"id": d.name}
        # try to infer common output files
        files = []
        for f in d.glob("*"):
            if f.is_file() and f.name != ".gitkeep":
                files.append(f.name)
        item["files"] = sorted(files)
        out.append(item)
    return out


@app.get("/health")
def health():
    return {"ok": True, "jobs_dir": str(JOBS_DIR), "job_count": len(_list_jobs())}


@app.get("/", response_class=HTMLResponse)
def index():
    jobs = _list_jobs()[:50]
    rows = "\n".join(
        f"<tr><td><code>{j['id']}</code></td><td>{', '.join(j['files'])}</td>"
        f"<td><a href='/jobs/{j['id']}'>json</a></td></tr>"
        for j in jobs
    )
    html = f"""
    <html>
      <head>
        <meta charset="utf-8"/>
        <title>logs_viewer</title>
        <style>
          body{{font-family:system-ui,Segoe UI,Roboto,Arial;background:#0b0b0d;color:#e9e9ee;padding:24px}}
          table{{border-collapse:collapse;width:100%}}
          td,th{{border:1px solid #2a2a33;padding:10px}}
          a{{color:#86f3b1}}
          code{{color:#cfe1ff}}
          .muted{{opacity:.7}}
        </style>
      </head>
      <body>
        <h2>logs_viewer</h2>
        <div class="muted">Listando outputs em <code>{JOBS_DIR}</code>.</div>
        <h3>Últimos jobs</h3>
        <table>
          <thead><tr><th>ID</th><th>Arquivos</th><th>API</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </body>
    </html>
    """
    return HTMLResponse(html)


@app.get("/jobs")
def jobs():
    return JSONResponse(_list_jobs())


@app.get("/jobs/{job_id}")
def job(job_id: str):
    d = (JOBS_DIR / job_id).resolve()
    if not d.exists() or not d.is_dir():
        raise HTTPException(status_code=404, detail="job not found")
    files = {}
    for f in d.glob("*"):
        if f.is_file() and f.name != ".gitkeep":
            # only small text previews
            if f.suffix.lower() in (".json", ".jsonl", ".txt", ".log"):
                try:
                    files[f.name] = f.read_text(encoding="utf-8", errors="replace")[:20000]
                except Exception:
                    files[f.name] = "<unreadable>"
            else:
                files[f.name] = {"size": f.stat().st_size}
    return {"id": job_id, "files": files}
