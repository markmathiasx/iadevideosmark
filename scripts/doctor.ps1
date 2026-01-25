$root = "D:\minhaiateste\MinhaIALAST"
Set-Location $root

function Exists($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

$r = @()
$r += "# Requirements Report"
$r += ""
$r += "Root: $root"
$r += "Date: 2026-01-25T02:38:31"
$r += ""
$r += "## Versions"

$r += "git: " + ( (Exists git) ? (git --version) : "MISSING" )
$r += "python: " + ( (Exists python) ? (python --version) : "MISSING" )
$r += "pip: " + ( (Exists pip) ? (pip --version) : "MISSING" )
$r += "node: " + ( (Exists node) ? (node --version) : "optional" )
$r += "npm: " + ( (Exists npm) ? (npm --version) : "optional" )
$r += "docker: " + ( (Exists docker) ? (docker --version) : "optional" )
$r += "ffmpeg: " + ( (Exists ffmpeg) ? ((ffmpeg -version | Select-Object -First 1) -join '') : "MISSING" )
$r += "ffprobe: " + ( (Exists ffprobe) ? ((ffprobe -version | Select-Object -First 1) -join '') : "MISSING" )

$r += ""
$r += "## Paths"
$r += "where.exe python: " + ( & where.exe python 2>$null | Select-Object -First 1 )
$r += "where.exe ffmpeg: " + ( & where.exe ffmpeg 2>$null | Select-Object -First 1 )
$r += "where.exe ffprobe: " + ( & where.exe ffprobe 2>$null | Select-Object -First 1 )

$r += ""
$r += "## Disk Free (bytes)"
try {
  $c = Get-PSDrive C -ErrorAction SilentlyContinue
  $d = Get-PSDrive D -ErrorAction SilentlyContinue
  if ($c) { $r += "C: " + $c.Free }
  if ($d) { $r += "D: " + $d.Free }
} catch {}

$missing = @()
if (-not (Exists git)) { $missing += "git" }
if (-not (Exists python)) { $missing += "python" }
if (-not (Exists pip)) { $missing += "pip" }
if (-not (Exists ffmpeg)) { $missing += "ffmpeg" }
if (-not (Exists ffprobe)) { $missing += "ffprobe" }

$out = Join-Path $root "_requirements_report.md"
$r -join "
" | Out-File -Encoding utf8 $out

if ($missing.Count -eq 0) { Write-Host "READY" } else { Write-Host ("MISSING: " + ($missing -join ", ")) }
Write-Host "Report: $out"
