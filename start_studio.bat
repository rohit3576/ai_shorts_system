@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Python venv was not found.
  echo Run:
  echo python -m venv .venv
  echo .\.venv\Scripts\activate
  echo python -m pip install -r requirements.txt
  pause
  exit /b 1
)

".venv\Scripts\python.exe" "start_studio.py"

echo.
echo Studio server stopped.
pause
