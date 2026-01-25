param()

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function WriteUtf8($path, $content) {
  $full = Join-Path $root $path
  $dir = Split-Path $full -Parent
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  Set-Content -Path $full -Value $content -Encoding UTF8
}

# --- doctor.ps1 (sem ternário; funciona bem) ---
WriteUtf8 "scripts\doctor.ps1" @"
`$ErrorActionPreference = 'Continue'
`$root = (Resolve-Path (Join-Path `$PSScriptRoot '..')).Path
Set-Location `$root

function Exists([string]`$cmd) {
  return [bool](Get-Command `$cmd -ErrorAction SilentlyContinue)
}

function FirstLine([scriptblock]`$sb) {
  try {
    `$o = & `$sb 2>&1 | Out-String
    if ([string]::IsNullOrWhiteSpace(`$o)) { return "N/A" }
    return (`$o -split "`r?`n")[0].Trim()
  } catch {
    return ("ERROR: " + `$_.Exception.Message)
  }
}

`$report = New-Object System.Collections.Generic.List[string]
`$report.Add("# Requirements Report")
`$report.Add("")
`$report.Add("Root: `$root")
`$report.Add("Date: $(Get-Date -Format s)")
`$report.Add("")
`$report.Add("## Versions")

`$report.Add("git: "    + (if (Exists git)    { FirstLine { git --version } } else { "MISSING" }))
`$report.Add("python: " + (if (Exists python) { FirstLine { python --version } } else { "MISSING" }))
`$report.Add("pip: "    + (if (Exists pip)    { FirstLine { pip --version } } else { "MISSING" }))
`$report.Add("node: "   + (if (Exists node)   { FirstLine { node --version } } else { "optional" }))
`$report.Add("npm: "    + (if (Exists npm)    { FirstLine { npm --version } } else { "optional" }))
`$report.Add("docker: " + (if (Exists docker) { FirstLine { docker --version } } else { "optional" }))
`$report.Add("ffmpeg: " + (if (Exists ffmpeg) { FirstLine { ffmpeg -version } } else { "MISSING" }))
`$report.Add("ffprobe: "+ (if (Exists ffprobe){ FirstLine { ffprobe -version } } else { "MISSING" }))

`$report.Add("")
`$report.Add("## Paths")
try { `$report.Add("where python: " + ((& where.exe python 2>`$null | Select-Object -First 1) -as [string])) } catch {}
try { `$report.Add("where ffmpeg: " + ((& where.exe ffmpeg 2>`$null | Select-Object -First 1) -as [string])) } catch {}
try { `$report.Add("where ffprobe: " + ((& where.exe ffprobe 2>`$null | Select-Object -First 1) -as [string])) } catch {}

`$report.Add("")
`$report.Add("## Disk Free (bytes)")
try { `$c = Get-PSDrive C -ErrorAction SilentlyContinue; if (`$c) { `$report.Add("C: " + `$c.Free) } } catch {}
try { `$d = Get-PSDrive D -ErrorAction SilentlyContinue; if (`$d) { `$report.Add("D: " + `$d.Free) } } catch {}

`$missing = @()
if (-not (Exists git))    { `$missing += "git" }
if (-not (Exists python)) { `$missing += "python" }
if (-not (Exists pip))    { `$missing += "pip" }
if (-not (Exists ffmpeg)) { `$missing += "ffmpeg" }
if (-not (Exists ffprobe)){ `$missing += "ffprobe" }

`$out = Join-Path `$root "_requirements_report.md"
`$report | Out-File -Encoding utf8 -FilePath `$out

if (`$missing.Count -eq 0) { Write-Host "READY" } else { Write-Host ("MISSING: " + (`$missing -join ", ")) }
Write-Host "Report: `$out"
"@

# --- dev.ps1 (sem quoting quebrado; uvicorn no shell atual) ---
WriteUtf8 "scripts\dev.ps1" @"
`$ErrorActionPreference = 'Stop'
`$root = (Resolve-Path (Join-Path `$PSScriptRoot '..')).Path
Set-Location `$root

`$py = Join-Path `$root "apps\api\.venv\Scripts\python.exe"
if (-not (Test-Path `$py)) {
  Write-Host "Venv not found. Run scripts\setup.cmd first."
  exit 1
}

`$env:PYTHONUTF8 = "1"
`$env:PYTHONPATH = `$root

Write-Host "Starting API+UI on http://127.0.0.1:8000 ..."
& `$py -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
"@

# --- setup.ps1 (chama doctor, cria venv, instala deps) ---
WriteUtf8 "scripts\setup.ps1" @"
`$ErrorActionPreference = 'Stop'
`$root = (Resolve-Path (Join-Path `$PSScriptRoot '..')).Path
Set-Location `$root

Write-Host "Running doctor..."
& (Join-Path `$root "scripts\doctor.ps1")

Write-Host "Creating venv..."
`$venv = Join-Path `$root "apps\api\.venv"
if (-not (Test-Path `$venv)) {
  python -m venv `$venv
}

Write-Host "Installing backend deps..."
`$py  = Join-Path `$venv "Scripts\python.exe"
`$pip = Join-Path `$venv "Scripts\pip.exe"

& `$py -m pip install --upgrade pip
& `$pip install -r (Join-Path `$root "apps\api\requirements.txt")

Write-Host "Setup done."
"@

# --- validate.ps1 (igual ao seu, só garantindo URL) ---
WriteUtf8 "scripts\validate.ps1" @"
`$ErrorActionPreference = 'Stop'
`$root = (Resolve-Path (Join-Path `$PSScriptRoot '..')).Path
Set-Location `$root

`$api = "http://127.0.0.1:8000"
Write-Host "Validating API..."

try {
  `$h = Invoke-RestMethod -Method GET -Uri (`$api + "/health") -TimeoutSec 10
} catch {
  Write-Host "FAIL: API not responding. Run scripts\dev.cmd first."
  exit 1
}

Write-Host "Creating mock_text_to_video job..."
`$body = @{
  profile_id="mock_text_to_video";
  mode="mock_text_to_video";
  prompt_or_script="Teste MOCK video";
  inputs=@();
  params=@{duration=3; fps=24; aspect="16:9"};
  content_sensitive=$false;
  consent=$false
} | ConvertTo-Json -Depth 5

`$job = Invoke-RestMethod -Method POST -Uri (`$api + "/jobs") -Body `$body -ContentType "application/json"
`$id = `$job.id
Write-Host "Job: `$id"

for (`$i=0; `$i -lt 60; `$i++) {
  Start-Sleep -Seconds 1
  `$j = Invoke-RestMethod -Method GET -Uri (`$api + "/jobs/`$id")
  if (`$j.status -eq "succeeded" -or `$j.status -eq "failed") {
    Write-Host ("Status: " + `$j.status)
    if (`$j.status -eq "succeeded") {
      Write-Host "PASS"
      exit 0
    } else {
      Write-Host ("FAIL: " + `$j.error)
      exit 1
    }
  }
}
Write-Host "FAIL: timeout"
exit 1
"@

# --- wrappers .cmd (forçam pwsh) ---
WriteUtf8 "scripts\setup.cmd" @"
@echo off
setlocal
cd /d "%~dp0.."
pwsh -NoLogo -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
"@

WriteUtf8 "scripts\dev.cmd" @"
@echo off
setlocal
cd /d "%~dp0.."
pwsh -NoLogo -ExecutionPolicy Bypass -File "%~dp0dev.ps1"
"@

WriteUtf8 "scripts\validate.cmd" @"
@echo off
setlocal
cd /d "%~dp0.."
pwsh -NoLogo -ExecutionPolicy Bypass -File "%~dp0validate.ps1"
"@

WriteUtf8 "scripts\doctor.cmd" @"
@echo off
setlocal
cd /d "%~dp0.."
pwsh -NoLogo -ExecutionPolicy Bypass -File "%~dp0doctor.ps1"
"@

# --- garante pacote python apps ---
if (-not (Test-Path (Join-Path $root "apps\__init__.py"))) {
  WriteUtf8 "apps\__init__.py" ""
}
if (-not (Test-Path (Join-Path $root "apps\api\__init__.py"))) {
  WriteUtf8 "apps\api\__init__.py" ""
}

Write-Host "REPAIR DONE."
Write-Host "Next:"
Write-Host "  1) scripts\setup.cmd"
Write-Host "  2) scripts\dev.cmd   (deixe rodando)"
Write-Host "  3) em outro terminal: scripts\validate.cmd"
