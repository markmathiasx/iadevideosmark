$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

$py = Join-Path $root "apps\api\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
  Write-Host "Venv not found. Run scripts\setup.cmd first."
  exit 1
}

$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = $root

Write-Host "Starting API+UI on http://127.0.0.1:8000 ..."
& $py -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
