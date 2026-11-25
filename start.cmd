@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating virtual environment...
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
  if errorlevel 1 goto :error
)
".venv\Scripts\python.exe" -c "import sys; assert sys.version_info[:2] == (3, 12), f'Python 3.12 required, found {sys.version}. Please use Python 3.12.'; print(f'Python {sys.version.split()[0]} OK')"
if errorlevel 1 goto :error
echo [2/3] Checking dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error
echo [3/3] Checking the installation and starting Mutagen Control...
".venv\Scripts\python.exe" verify_source.py
if errorlevel 1 goto :error
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto :error
exit /b 0
:error
echo An error occurred during startup. Copy this output for diagnostics.
pause
exit /b 1
