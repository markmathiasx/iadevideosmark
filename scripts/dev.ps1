# PowerShell 5.1 compatible dev runner
$ErrorActionPreference = "Stop"

function Start-API {
  Write-Host "[dev] Starting API on http://127.0.0.1:8000 ..."
  $env:PYTHONPATH = ".\apps\api"
  Start-Process -WindowStyle Normal `
    -FilePath ".\.venv\Scripts\python.exe" `
    -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000","--reload" `
    -WorkingDirectory ".\apps\api"
}

function Start-WEB {
  Write-Host "[dev] Starting WEB on http://127.0.0.1:5173 ..."
  # IMPORTANT:
  # Start-Process expects an executable or a document (opened via file association).
  # If you pass "npm", Windows may resolve to npm.ps1 and open it in Notepad instead of executing.
  # Using cmd.exe ensures npm.cmd is used.
  Start-Process -WindowStyle Normal `
    -FilePath "cmd.exe" `
    -ArgumentList "/c","npm","run","dev" `
    -WorkingDirectory ".\apps\web"
}

if (-not (Test-Path ".\.venv\Scripts\python.exe")) { Write-Host "[dev] Missing venv. Run scripts\setup.ps1 first."; exit 1 }

Start-API
Start-WEB

Write-Host "[dev] Started. Close the opened windows to stop."
