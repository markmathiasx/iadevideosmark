@echo off
setlocal
cd /d "%~dp0.."
pwsh -NoLogo -ExecutionPolicy Bypass -File "%~dp0validate.ps1"
