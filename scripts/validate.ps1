$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

$api = "http://127.0.0.1:8000"
Write-Host "Validating API..."

try {
  $h = Invoke-RestMethod -Method GET -Uri ($api + "/health") -TimeoutSec 10
} catch {
  Write-Host "FAIL: API not responding."
  exit 1
}

Write-Host "PASS: health ok"
Write-Host ("ffmpeg: " + $h.ffmpeg)
Write-Host ("root: " + $h.root)
