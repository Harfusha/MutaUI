@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Mutagen Control 8.2 - EXE builder
set "PYTHONUTF8=1"

echo ========================================================
echo   MUTAGEN CONTROL 8.2 - samostatny Windows EXE (onefile)
echo ========================================================
echo.
echo POZNAMKA: pro nejrychlejsi start aplikace pouzijte build_fast.cmd.
echo.
if /I not "%OS%"=="Windows_NT" goto :error
if not exist "app.py" goto :error

if not exist ".venv\Scripts\python.exe" (
  echo [1/5] Pripravuji lokalni Python prostredi...
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
  if errorlevel 1 goto :error
)

echo [2/5] Kontrola Pythonu a zavislosti...
".venv\Scripts\python.exe" -c "import sys; assert (3,11)<=sys.version_info[:2]<(3,14), 'Pouzijte Python 3.11 az 3.13'; print(sys.version)"
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt -r requirements-build.txt
if errorlevel 1 goto :error

echo [3/5] Kontrola syntaxe a logickych testu...
".venv\Scripts\python.exe" -m compileall -q app.py performance.py monitoring.py mutagen_client.py insights.py endpoint_inspector.py server_groups.py log_stream.py async_recorder.py sync_profiles.py
if errorlevel 1 goto :error
".venv\Scripts\python.exe" verify_source.py
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pytest -q tests --ignore=tests/test_gui_smoke.py
if errorlevel 1 goto :error

echo [4/5] Qt offscreen test rozhrani...
".venv\Scripts\python.exe" -c "import PySide6; print('Qt ready')"
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -c "import PySide6, shiboken6"
if errorlevel 1 goto :error
set "QT_QPA_PLATFORM=offscreen"
".venv\Scripts\python.exe" -m pytest -q tests\test_gui_smoke.py
if errorlevel 1 goto :error
set "QT_QPA_PLATFORM="

echo [5/5] Sestavuji EXE (prvni spusteni bude rozbalovat Qt)...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --noupx --name MutagenControl --icon "assets\mutagencontrol.ico" --version-file "assets\version_info.txt" --distpath "dist" --workpath "build" app.py
if errorlevel 1 goto :error
if not exist "dist\MutagenControl.exe" goto :error
echo [SELF TEST] Overuji zabaleny EXE bez pripojeni k Mutagenu...
set "QT_QPA_PLATFORM=offscreen"
"dist\MutagenControl.exe" --self-test
if errorlevel 1 goto :error
set "QT_QPA_PLATFORM="

echo.
echo ========================================================
echo HOTOVO: %CD%\dist\MutagenControl.exe
echo Samostatny EXE ma Python a Qt; Mutagen CLI zustava externi.
echo ========================================================
pause
exit /b 0

:error
set "QT_QPA_PLATFORM="
echo.
echo [CHYBA] Sestaveni selhalo. Zkontrolujte vypis vyse.
echo Pozadavky: Windows 10/11, Python 3.11-3.13, internet pro pip.
pause
exit /b 1
