$ErrorActionPreference = 'Continue'
$root = (Resolve-Path (Join-Path $(Split-Path -Parent $MyInvocation.MyCommand.Path) '..')).Path
Set-Location $root

function Exists([string]$cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function FirstLine([string]$cmd, [string[]]$args=@()) {
  try {
    $out = & $cmd @args 2>$null
    if ($out) { return ($out | Select-Object -First 1) }
  } catch {}
  return ''
}

$r = @()
$r += '# Requirements Report'
$r += ''
$r += ('Root: ' + $root)
$r += ('Date: ' + (Get-Date -Format s))
$r += ''
$r += '## Versions'

if (Exists 'git')    { $r += ('git: ' + (FirstLine 'git' @('--version'))) } else { $r += 'git: MISSING' }
if (Exists 'python') { $r += ('python: ' + (FirstLine 'python' @('--version'))) } else { $r += 'python: MISSING' }
if (Exists 'pip')    { $r += ('pip: ' + (FirstLine 'pip' @('--version'))) } else { $r += 'pip: MISSING' }

$out = Join-Path $root '_requirements_report.md'
$r -join \"
\" | Set-Content -Encoding utf8 $out
Write-Host 'READY'
Write-Host ('Report: ' + $out)
