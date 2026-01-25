@echo off
cd /d "%~dp0.."
start "" docker compose up --build --force-recreate
timeout /t 2 >nul
start "" http://localhost:8000/
