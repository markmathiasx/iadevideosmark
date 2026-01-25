$root = "D:\minhaiateste\MinhaIALAST"
Set-Location $root

Write-Host "Starting API+UI on http://127.0.0.1:8000 ..."
$py = "D:\minhaiateste\MinhaIALAST\apps\api\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
  Write-Host "Venv not found. Run scripts\setup.ps1 first."
  exit 1
}

Start-Process powershell -ArgumentList @(
  "-NoExit",
  "-Command",
  ""$env:PYTHONUTF8=1; & '' -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000""
)

Write-Host "Open: http://127.0.0.1:8000"
