@echo off
cd /d "%~dp0.."
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*

