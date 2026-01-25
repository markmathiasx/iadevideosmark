@echo off
cd /d "%~dp0.."
echo Starting MinhaIALAST (Docker)...
docker compose up --build -d
if errorlevel 1 exit /b 1
start "MinhaIALAST" http://localhost:8000/
echo.
echo OPENED: http://localhost:8000/
echo To stop: scripts\stop.cmd
echo To view logs: scripts\logs.cmd
echo.
pause
