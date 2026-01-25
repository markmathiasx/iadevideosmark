# PowerShell 5.1 compatible setup
$ErrorActionPreference = "Stop"

function Ensure-Command($name) {
  $cmd = Get-Command $name -ErrorAction SilentlyContinue
  if (-not $cmd) { return $false }
  return $true
}

function Resolve-NpmPath {
  $cmd = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $cmd = Get-Command "npm" -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return $null
}

Write-Host "[setup] Project root: $(Get-Location)"

if (-not (Test-Path ".\apps\api")) { Write-Host "[setup] Missing apps\api. Did you unzip to the repo root?"; exit 1 }
if (-not (Test-Path ".\apps\web")) { Write-Host "[setup] Missing apps\web. Did you unzip to the repo root?"; exit 1 }

if (-not (Test-Path ".\.env")) {
  Copy-Item ".\.env.example" ".\.env" -Force
  Write-Host "[setup] Created .env from .env.example (edit if needed)."
} else {
  Write-Host "[setup] .env already exists."
}

# Python venv
if (-not (Ensure-Command "python")) {
  Write-Host "[setup] ERROR: python not found in PATH."
  Write-Host "Install Python 3.10+ and try again."
  exit 1
}

if (-not (Test-Path ".\.venv")) {
  Write-Host "[setup] Creating venv..."
  python -m venv .venv
} else {
  Write-Host "[setup] venv exists."
}

Write-Host "[setup] Installing API deps..."
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r .\apps\api\requirements.txt

# Node deps
if (-not (Ensure-Command "node")) {
  Write-Host "[setup] ERROR: node not found in PATH."
  Write-Host "Install Node.js (>=18) and try again."
  exit 1
}

$npmPath = Resolve-NpmPath
if (-not $npmPath) {
  Write-Host "[setup] ERROR: npm not found in PATH."
  exit 1
}

Write-Host "[setup] Installing WEB deps..."
Push-Location .\apps\web
& $npmPath install
Pop-Location

if (-not (Test-Path ".\outputs")) { New-Item -ItemType Directory -Path ".\outputs" | Out-Null }

Write-Host "[setup] OK."
