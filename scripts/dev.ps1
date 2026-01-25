$root = "D:\minhaiateste\MinhaIALAST"
Set-Location $root

Write-Host "Starting API+UI on http://127.0.0.1:8000 ..."
$py = Join-Path $root "apps\api\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
  Write-Host "Venv not found. Run scripts\setup.ps1 first."
  exit 1
}

# Monta comando sem quebrar o parser do PS 5.1
$cmd = "cd `"$root`"; `$env:PYTHONUTF8=1; & `"$py`" -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000"

Start-Process -WorkingDirectory $root powershell -ArgumentList "-NoExit", "-Command", $cmd

Write-Host "Open: http://127.0.0.1:8000"
