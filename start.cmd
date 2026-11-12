@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Vytvarim virtualni prostredi...
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
  if errorlevel 1 goto :error
)
echo [2/3] Kontroluji zavislosti...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error
echo [3/3] Kontroluji strukturu a spoustim Mutagen Control...
".venv\Scripts\python.exe" verify_source.py
if errorlevel 1 goto :error
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto :error
exit /b 0
:error
echo Pri spousteni se objevila chyba. Zkopirujte tento vypis pro diagnostiku.
pause
exit /b 1
