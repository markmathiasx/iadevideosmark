$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $(Split-Path -Parent $MyInvocation.MyCommand.Path) '..')).Path
Set-Location $root

$api = 'http://127.0.0.1:8000'
Write-Host 'Validating API...'

try {
  $resp = Invoke-WebRequest -Uri ($api + '/health') -TimeoutSec 10
  Write-Host ('Health HTTP: ' + $resp.StatusCode)
} catch {
  Write-Host ('FAIL: ' + $_.Exception.Message)
  Write-Host 'If dev is not running, start: scripts\dev.cmd (keep the window open).'
  exit 1
}

Write-Host 'PASS: health ok'
