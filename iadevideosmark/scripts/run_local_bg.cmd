@echo off
cd /d "%~dp0.."
IF EXIST "myenv\.venv\Scripts\activate.bat" (
  call "myenv\.venv\Scripts\activate.bat"
) ELSE IF EXIST "myenv\Scripts\activate.bat" (
  call "myenv\Scripts\activate.bat"
)
start "" python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
timeout /t 2 >nul
start "" http://localhost:8000/
