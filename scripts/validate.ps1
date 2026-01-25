# PowerShell 5.1 compatible validation
$ErrorActionPreference = "Continue"

function Resolve-NpmPath {
  $cmd = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $cmd = Get-Command "npm" -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return $null
}

Write-Host "[validate] API compile check..."
.\.venv\Scripts\python.exe -m compileall .\apps\api\app | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "[validate] compileall FAILED" }

Write-Host "[validate] pip check..."
.\.venv\Scripts\python.exe -m pip check

$npmPath = Resolve-NpmPath
if (-not $npmPath) { Write-Host "[validate] npm not found. Skipping WEB build."; exit 0 }

Write-Host "[validate] WEB build..."
Push-Location .\apps\web
& $npmPath run build
Pop-Location

Write-Host "[validate] Done."
