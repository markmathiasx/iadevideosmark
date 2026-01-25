$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

function WriteFile([string]$rel, [string]$content) {
  $full = Join-Path $Root $rel
  $dir = Split-Path $full -Parent
  if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  $content | Set-Content -Encoding utf8 -Path $full
}

# ---------
# FIX 1: doctor.ps1 (-join correto)
# ---------
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
(`$r -join "`n") | Set-Content -Encoding utf8 `$out
Write-Host 'READY'
Write-Host ('Report: ' + `$out)
"@

# ---------
# FIX 2: main.py (remover \" inválido e reescrever bloco drawtext)
# ---------
$mainPath = Join-Path $Root "apps\api\main.py"
if (-not (Test-Path $mainPath)) { throw "apps\api\main.py não encontrado" }

$main = Get-Content -Raw -Encoding utf8 $mainPath

$startNeedle = "# drawtext may fail without fonts; fallback to no drawtext"
$endNeedle   = 'cmd = base + ["-vf", draw, "-pix_fmt", "yuv420p", str(out_mp4)]'

$start = $main.IndexOf($startNeedle)
if ($start -lt 0) { throw "Não achei o bloco drawtext no main.py (needle start)." }

$end = $main.IndexOf($endNeedle, $start)
if ($end -lt 0) { throw "Não achei o fim do bloco drawtext no main.py (needle end)." }

# pega até o final da linha do endNeedle
$endLine = $main.IndexOf("`n", $end)
if ($endLine -lt 0) { $endLine = $main.Length } else { $endLine = $endLine + 1 }

$before = $main.Substring(0, $start)
$after  = $main.Substring($endLine)

$indent = "                "  # 16 espaços (mesmo nível do bloco atual)

# Observação: primeira linha começa sem indent porque o $before já termina com os espaços do começo da linha.
$replacement = @"
# drawtext may fail without fonts; fallback to no drawtext
${indent}base = [FFMPEG, "-y", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate={fps}", "-t", str(dur)]
${indent}safe = (prompt or "MOCK").replace("\n", " ").replace("'", r"\'").replace(":", r"\:")
${indent}draw = f"drawtext=text='{safe}':x=20:y=20:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.5"
${indent}cmd = base + ["-vf", draw, "-pix_fmt", "yuv420p", str(out_mp4)]
"@

$main2 = $before + $replacement + $after
$main2 | Set-Content -Encoding utf8 $mainPath

Write-Host "HOTFIX DONE."
