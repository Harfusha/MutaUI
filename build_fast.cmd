@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Mutagen Control 8.2 - Fast-start builder
set "PYTHONUTF8=1"
echo ========================================================
echo   MUTAGEN CONTROL 8.2 - Fast Startup (one-folder)
echo ========================================================
echo.
if /I not "%OS%"=="Windows_NT" goto :error
if not exist "app.py" goto :error

if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
  if errorlevel 1 goto :error
)
".venv\Scripts\python.exe" -c "import sys; assert (3,11)<=sys.version_info[:2]<(3,14), 'Use Python 3.11 through 3.13'"
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt -r requirements-build.txt
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m compileall -q app.py performance.py monitoring.py async_recorder.py mutagen_client.py insights.py endpoint_inspector.py server_groups.py log_stream.py sync_profiles.py
if errorlevel 1 goto :error
".venv\Scripts\python.exe" verify_source.py
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pytest -q tests --ignore=tests/test_gui_smoke.py
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -c "import PySide6, shiboken6"
if errorlevel 1 goto :error
set "QT_QPA_PLATFORM=offscreen"
".venv\Scripts\python.exe" -m pytest -q tests\test_gui_smoke.py
if errorlevel 1 goto :error
set "QT_QPA_PLATFORM="
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed --noupx --collect-all paramiko --name MutagenControl --icon "assets\mutagencontrol.ico" --version-file "assets\version_info.txt" --distpath "dist-fast" --workpath "build-fast" app.py
if errorlevel 1 goto :error
if not exist "dist-fast\MutagenControl\MutagenControl.exe" goto :error
echo [SELF-TEST] Checking the packaged EXE without connecting to Mutagen...
set "QT_QPA_PLATFORM=offscreen"
"dist-fast\MutagenControl\MutagenControl.exe" --self-test
if errorlevel 1 goto :error
set "QT_QPA_PLATFORM="

echo.
echo DONE: %CD%\dist-fast\MutagenControl\MutagenControl.exe
echo Copy the entire MutagenControl folder, not just the EXE.
pause
exit /b 0
:error
set "QT_QPA_PLATFORM="
echo [ERROR] Fast build failed; check the output.
pause
exit /b 1
