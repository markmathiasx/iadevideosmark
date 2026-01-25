$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

function PatchFile([string]$path, [string]$pattern, [string]$replace, [string]$label) {
  if (-not (Test-Path $path)) { throw "Arquivo não encontrado: $path" }
  $txt = Get-Content -Raw -Encoding utf8 $path
  if ($txt -match $pattern) {
    $new = [regex]::Replace($txt, $pattern, $replace)
    if ($new -ne $txt) {
      $new | Set-Content -Encoding utf8 $path
      Write-Host "OK: $label"
      return $true
    }
  }
  Write-Host "SKIP: $label (padrão não encontrado)"
  return $false
}

$mainPath = Join-Path $Root "apps\api\main.py"

# 1) Corrigir bug atual: "...]                try:" na MESMA LINHA
# Captura a indentação do try: e força quebra de linha antes dele.
$pat1 = '(str\(out_mp4\)\])([ \t]+)(try:)'
$rep1 = '$1' + "`n" + '                $3'
PatchFile $mainPath $pat1 $rep1 "main.py: quebra de linha antes do try"

# 2) Fallback: se o texto tiver ")]" e depois "try:" na mesma linha (outras variações)
$pat2 = '(\]\s*)(try:)'
$rep2 = "`n" + '                $2'
# Só aplica se existir um "cmd = base + [" na MESMA linha do try (reduz risco de mexer em outros lugares)
if ((Get-Content -Raw -Encoding utf8 $mainPath) -match 'cmd\s*=\s*base\s*\+\s*\[[^\r\n]+\]\s+try:') {
  PatchFile $mainPath 'cmd\s*=\s*base\s*\+\s*\[[^\r\n]+\]\s+try:' { 
    param($m)
    $line = $m.Value
    # troca o último " try:" por quebra de linha + indentação + try:
    $line -replace '\s+try:$', "`n                try:"
  } "main.py: fallback cmd-line try split"
}

# 3) Garantir __init__.py (para import apps.api.main dentro do container)
$appsInit = Join-Path $Root "apps\__init__.py"
$apiInit  = Join-Path $Root "apps\api\__init__.py"
if (-not (Test-Path $appsInit)) { "" | Set-Content -Encoding utf8 $appsInit; Write-Host "OK: apps/__init__.py criado" }
if (-not (Test-Path $apiInit))  { "" | Set-Content -Encoding utf8 $apiInit;  Write-Host "OK: apps/api/__init__.py criado" }

Write-Host ""
Write-Host "HOTFIX3 DONE."
Write-Host "Próximo passo (Docker):"
Write-Host "  docker compose down"
Write-Host "  docker compose up --build --force-recreate"
Write-Host ""
Write-Host "Teste:"
Write-Host "  curl http://127.0.0.1:8000/health"
