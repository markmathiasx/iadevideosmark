@echo off
cd /d "%~dp0.."
REM Tenta ativar venv nos dois formatos comuns:
IF EXIST "myenv\.venv\Scripts\activate.bat" (
  call "myenv\.venv\Scripts\activate.bat"
) ELSE IF EXIST "myenv\Scripts\activate.bat" (
  call "myenv\Scripts\activate.bat"
)
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
