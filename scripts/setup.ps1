$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

Write-Host "Running doctor..."
& (Join-Path $root "scripts\doctor.ps1")

Write-Host "Creating venv..."
$venv = Join-Path $root "apps\api\.venv"
if (-not (Test-Path $venv)) {
  python -m venv $venv
}

Write-Host "Installing backend deps..."
$py  = Join-Path $venv "Scripts\python.exe"
$pip = Join-Path $venv "Scripts\pip.exe"

& $py -m pip install --upgrade pip
& $pip install -r (Join-Path $root "apps\api\requirements.txt")

Write-Host "Setup done."
