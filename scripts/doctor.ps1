$root = "D:\minhaiateste\MinhaIALAST"
Set-Location $root

function Exists($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

function OneLine($cmd, $args) {
  try {
    $out = & $cmd @args 2>&1 | Out-String
    $out = ($out -split "`r?`n" | Where-Object { $_ -and $_.Trim() -ne "" } | Select-Object -First 1)
    if (-not $out) { return "N/A" }
    return $out.Trim()
  } catch {
    return "N/A"
  }
}

$r = @()
$r += "# Requirements Report"
$r += ""
$r += "Root: $root"
$r += "Date: $(Get-Date -Format s)"
$r += ""
$r += "## Versions"

$r += "git: "    + ($(if (Exists git)    { OneLine git @("--version") } else { "MISSING" }))
$r += "python: " + ($(if (Exists python) { OneLine python @("--version") } else { "MISSING" }))
$r += "pip: "    + ($(if (Exists pip)    { OneLine pip @("--version") } else { "MISSING" }))
$r += "node: "   + ($(if (Exists node)   { OneLine node @("--version") } else { "optional" }))
$r += "npm: "    + ($(if (Exists npm)    { OneLine npm @("--version") } else { "optional" }))
$r += "docker: " + ($(if (Exists docker) { OneLine docker @("--version") } else { "optional" }))
$r += "ffmpeg: " + ($(if (Exists ffmpeg) { OneLine ffmpeg @("-version") } else { "MISSING" }))
$r += "ffprobe: "+ ($(if (Exists ffprobe){ OneLine ffprobe @("-version") } else { "MISSING" }))

$r += ""
$r += "## Paths"
try { $r += "where.exe python: " + ((& where.exe python 2>$null | Select-Object -First 1) -as [string]) } catch { $r += "where.exe python: N/A" }
try { $r += "where.exe ffmpeg: " + ((& where.exe ffmpeg 2>$null | Select-Object -First 1) -as [string]) } catch { $r += "where.exe ffmpeg: N/A" }
try { $r += "where.exe ffprobe: " + ((& where.exe ffprobe 2>$null | Select-Object -First 1) -as [string]) } catch { $r += "where.exe ffprobe: N/A" }

$r += ""
$r += "## Disk Free (bytes)"
try {
  $c = Get-PSDrive C -ErrorAction SilentlyContinue
  $d = Get-PSDrive D -ErrorAction SilentlyContinue
  if ($c) { $r += "C: " + $c.Free }
  if ($d) { $r += "D: " + $d.Free }
} catch {}

$missing = @()
if (-not (Exists git))    { $missing += "git" }
if (-not (Exists python)) { $missing += "python" }
if (-not (Exists pip))    { $missing += "pip" }
if (-not (Exists ffmpeg)) { $missing += "ffmpeg" }
if (-not (Exists ffprobe)){ $missing += "ffprobe" }

$out = Join-Path $root "_requirements_report.md"
$r -join "`n" | Out-File -Encoding utf8 $out

if ($missing.Count -eq 0) { Write-Host "READY" } else { Write-Host ("MISSING: " + ($missing -join ", ")) }
Write-Host "Report: $out"
