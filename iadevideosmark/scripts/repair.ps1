$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

function WriteFile([string]$rel, [string]$content) {
  $full = Join-Path $Root $rel
  $dir = Split-Path $full -Parent
  if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  $content | Set-Content -Encoding utf8 -Path $full
}

# Arquivos de pacote para o uvicorn conseguir importar "apps.api.main"
WriteFile "apps\__init__.py" ""
if (-not (Test-Path "apps\api\__init__.py")) { WriteFile "apps\api\__init__.py" "" }

# doctor.ps1 (sem operador ternário; compatível)
WriteFile "scripts\doctor.ps1" @"
`$ErrorActionPreference = 'Continue'
`$root = (Resolve-Path (Join-Path `$(Split-Path -Parent `$MyInvocation.MyCommand.Path) '..')).Path
Set-Location `$root

function Exists([string]`$cmd) { return [bool](Get-Command `$cmd -ErrorAction SilentlyContinue) }
function FirstLine([string]`$cmd, [string[]]`$args=@()) {
  try {
    `$out = & `$cmd @args 2>`$null
    if (`$out) { return (`$out | Select-Object -First 1) }
  } catch {}
  return ''
}

`$r = @()
`$r += '# Requirements Report'
`$r += ''
`$r += ('Root: ' + `$root)
`$r += ('Date: ' + (Get-Date -Format s))
`$r += ''
`$r += '## Versions'

if (Exists 'git')    { `$r += ('git: ' + (FirstLine 'git' @('--version'))) } else { `$r += 'git: MISSING' }
if (Exists 'python') { `$r += ('python: ' + (FirstLine 'python' @('--version'))) } else { `$r += 'python: MISSING' }
if (Exists 'pip')    { `$r += ('pip: ' + (FirstLine 'pip' @('--version'))) } else { `$r += 'pip: MISSING' }

`$out = Join-Path `$root '_requirements_report.md'
`$r -join \"`n\" | Set-Content -Encoding utf8 `$out
Write-Host 'READY'
Write-Host ('Report: ' + `$out)
"@

# setup.ps1
WriteFile "scripts\setup.ps1" @"
`$ErrorActionPreference = 'Stop'
`$root = (Resolve-Path (Join-Path `$(Split-Path -Parent `$MyInvocation.MyCommand.Path) '..')).Path
Set-Location `$root

Write-Host 'Running doctor...'
& (Join-Path `$root 'scripts\doctor.ps1')

`$venv = Join-Path `$root 'apps\api\.venv'
`$py  = Join-Path `$venv 'Scripts\python.exe'
`$pip = Join-Path `$venv 'Scripts\pip.exe'

Write-Host 'Creating venv...'
if (-not (Test-Path `$venv)) { python -m venv `$venv }

Write-Host 'Installing backend deps...'
& `$py -m pip install --upgrade pip
& `$pip install -r (Join-Path `$root 'apps\api\requirements.txt')

Write-Host 'Setup done.'
"@

# dev.ps1 (sem Start-Process; roda no processo atual)
WriteFile "scripts\dev.ps1" @"
`$ErrorActionPreference = 'Stop'
`$root = (Resolve-Path (Join-Path `$(Split-Path -Parent `$MyInvocation.MyCommand.Path) '..')).Path
Set-Location `$root

`$py = Join-Path `$root 'apps\api\.venv\Scripts\python.exe'
if (-not (Test-Path `$py)) { Write-Host 'Venv not found. Run scripts\setup.ps1 first.'; exit 1 }

`$env:PYTHONUTF8 = '1'
Write-Host 'Starting API+UI on http://127.0.0.1:8000 ...'
& `$py -m uvicorn apps.api.main:app --app-dir `$root --host 127.0.0.1 --port 8000
"@

# wrappers .cmd (sempre chamam pwsh)
WriteFile "scripts\setup.cmd"    "@echo off`r`ncd /d `"%~dp0..`"`r`npwsh -NoProfile -ExecutionPolicy Bypass -File `"%~dp0setup.ps1`" %*`r`n"
WriteFile "scripts\dev.cmd"      "@echo off`r`ncd /d `"%~dp0..`"`r`npwsh -NoProfile -ExecutionPolicy Bypass -File `"%~dp0dev.ps1`" %*`r`n"

Write-Host "REPAIR DONE."
Write-Host "Next:"
Write-Host "  1) scripts\setup.cmd"
Write-Host "  2) scripts\dev.cmd"
