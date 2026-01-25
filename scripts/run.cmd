@echo off
cd /d "%~dp0.."
docker compose up --build --force-recreate
