$ErrorActionPreference = 'Continue'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

function Exists([string]$cmd) {
  return [bool](Get-Command $cmd -ErrorAction SilentlyContinue)
}

function FirstLine([scriptblock]$sb) {
  try {
    $o = & $sb 2>&1 | Out-String
    if ([string]::IsNullOrWhiteSpace($o)) { return "N/A" }
    return ($o -split "?
")[0].Trim()
  } catch {
    return ("ERROR: " + $_.Exception.Message)
  }
}

$report = New-Object System.Collections.Generic.List[string]
$report.Add("# Requirements Report")
$report.Add("")
$report.Add("Root: $root")
$report.Add("Date: 2026-01-25T04:05:04")
$report.Add("")
$report.Add("## Versions")

$report.Add("git: "    + (if (Exists git)    { FirstLine { git --version } } else { "MISSING" }))
$report.Add("python: " + (if (Exists python) { FirstLine { python --version } } else { "MISSING" }))
$report.Add("pip: "    + (if (Exists pip)    { FirstLine { pip --version } } else { "MISSING" }))
$report.Add("node: "   + (if (Exists node)   { FirstLine { node --version } } else { "optional" }))
$report.Add("npm: "    + (if (Exists npm)    { FirstLine { npm --version } } else { "optional" }))
$report.Add("docker: " + (if (Exists docker) { FirstLine { docker --version } } else { "optional" }))
$report.Add("ffmpeg: " + (if (Exists ffmpeg) { FirstLine { ffmpeg -version } } else { "MISSING" }))
$report.Add("ffprobe: "+ (if (Exists ffprobe){ FirstLine { ffprobe -version } } else { "MISSING" }))

$report.Add("")
$report.Add("## Paths")
try { $report.Add("where python: " + ((& where.exe python 2>$null | Select-Object -First 1) -as [string])) } catch {}
try { $report.Add("where ffmpeg: " + ((& where.exe ffmpeg 2>$null | Select-Object -First 1) -as [string])) } catch {}
try { $report.Add("where ffprobe: " + ((& where.exe ffprobe 2>$null | Select-Object -First 1) -as [string])) } catch {}

$report.Add("")
$report.Add("## Disk Free (bytes)")
try { $c = Get-PSDrive C -ErrorAction SilentlyContinue; if ($c) { $report.Add("C: " + $c.Free) } } catch {}
try { $d = Get-PSDrive D -ErrorAction SilentlyContinue; if ($d) { $report.Add("D: " + $d.Free) } } catch {}

$missing = @()
if (-not (Exists git))    { $missing += "git" }
if (-not (Exists python)) { $missing += "python" }
if (-not (Exists pip))    { $missing += "pip" }
if (-not (Exists ffmpeg)) { $missing += "ffmpeg" }
if (-not (Exists ffprobe)){ $missing += "ffprobe" }

$out = Join-Path $root "_requirements_report.md"
$report | Out-File -Encoding utf8 -FilePath $out

if ($missing.Count -eq 0) { Write-Host "READY" } else { Write-Host ("MISSING: " + ($missing -join ", ")) }
Write-Host "Report: $out"
