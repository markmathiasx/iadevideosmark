\
@echo off
setlocal
cd /d "%~dp0.."
echo Starting MinhaIALAST (Docker)...
docker compose up --build --force-recreate -d
echo OPEN: http://localhost:8000/
start "" "http://localhost:8000/"
echo To stop: scripts\stop.cmd
echo To view logs: scripts\logs.cmd
endlocal
