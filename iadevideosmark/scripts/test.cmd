\
@echo off
setlocal
cd /d "%~dp0.."
echo Testing API health...
powershell -NoProfile -Command "try { irm http://127.0.0.1:8000/health -TimeoutSec 5 } catch { exit 1 }"
if errorlevel 1 (
  echo API not responding. Run scripts\run.cmd first.
  exit /b 1
)
echo Creating MOCK job...
powershell -NoProfile -Command ^
  "$b=@{profile_id='mock_text_to_video';mode='mock_text_to_video';prompt_or_script='Teste MOCK';inputs=@();params=@{duration=3;fps=24;aspect='16:9'} } | ConvertTo-Json -Depth 6; $j=irm -Method POST http://127.0.0.1:8000/jobs -ContentType 'application/json' -Body $b; $j"
echo Done. Open http://localhost:8000/ and check Jobs.
endlocal
