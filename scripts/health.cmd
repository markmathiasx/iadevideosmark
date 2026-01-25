@echo off
powershell -NoProfile -Command "try { irm http://127.0.0.1:8000/health } catch { $_.Exception.Message }"
