$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

$api = "http://127.0.0.1:8000"
Write-Host "Validating API..."

try {
  $h = Invoke-RestMethod -Method GET -Uri ($api + "/health") -TimeoutSec 10
} catch {
  Write-Host "FAIL: API not responding. Run scripts\dev.cmd first."
  exit 1
}

Write-Host "Creating mock_text_to_video job..."
$body = @{
  profile_id="mock_text_to_video";
  mode="mock_text_to_video";
  prompt_or_script="Teste MOCK video";
  inputs=@();
  params=@{duration=3; fps=24; aspect="16:9"};
  content_sensitive=False;
  consent=False
} | ConvertTo-Json -Depth 5

$job = Invoke-RestMethod -Method POST -Uri ($api + "/jobs") -Body $body -ContentType "application/json"
$id = $job.id
Write-Host "Job: $id"

for ($i=0; $i -lt 60; $i++) {
  Start-Sleep -Seconds 1
  $j = Invoke-RestMethod -Method GET -Uri ($api + "/jobs/$id")
  if ($j.status -eq "succeeded" -or $j.status -eq "failed") {
    Write-Host ("Status: " + $j.status)
    if ($j.status -eq "succeeded") {
      Write-Host "PASS"
      exit 0
    } else {
      Write-Host ("FAIL: " + $j.error)
      exit 1
    }
  }
}
Write-Host "FAIL: timeout"
exit 1
