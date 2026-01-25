$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$path = Join-Path $Root "apps\api\main.py"
if (-not (Test-Path $path)) {
  throw "apps\api\main.py não encontrado em: $path"
}

$text = Get-Content -Raw -Encoding utf8 $path

# 1) Corrige caso o 'try:' tenha sido colado ao fim da linha do cmd (SyntaxError)
#    Exemplo ruim:  ... str(out_mp4)]                try:
#    Corrige para:
#      ... str(out_mp4)]
#      (mesma indentação) try:
$lines = $text -split "`n"
$out = New-Object System.Collections.Generic.List[string]

foreach ($line in $lines) {
  if ($line -match "^(?<indent>\s*)(?<before>.*str\(out_mp4\)\])\s+(?<after>try:.*)$") {
    $indent = $Matches["indent"]
    $before = $Matches["before"]
    $after  = $Matches["after"]
    $out.Add("$indent$before")
    $out.Add("$indent$after")
  }
  else {
    $out.Add($line)
  }
}

$fixed = ($out -join "`n")

# 2) Fallback extra (caso o padrão esteja em outro formato)
$fixed2 = $fixed -replace "str\(out_mp4\)\]\s+try:", "str(out_mp4)]`n                try:"

if ($fixed2 -ne $text) {
  Set-Content -Encoding utf8 -Path $path -Value $fixed2
  Write-Host "OK: main.py corrigido (try: em nova linha)."
} else {
  Write-Host "Nada para corrigir: padrão não encontrado."
}

Write-Host "Próximo passo (Docker):"
Write-Host "  docker compose down"
Write-Host "  docker compose up --build --force-recreate"
