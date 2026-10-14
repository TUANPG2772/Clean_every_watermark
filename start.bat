@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run: creating Python environment...
  where py >nul 2>&1
  if errorlevel 1 (
    python -m venv .venv
  ) else (
    py -3 -m venv .venv
  )
  if errorlevel 1 goto :fail
)
if not exist ".venv\clean-local-ready" (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :fail
  echo ready>".venv\clean-local-ready"
)
".venv\Scripts\python.exe" run.py
if errorlevel 1 goto :fail
exit /b 0
:fail
echo.
echo Could not start. Install Python 3.11 or newer, then try again.
echo Read the error above. See README.md for FFmpeg setup.
pause
exit /b 1
