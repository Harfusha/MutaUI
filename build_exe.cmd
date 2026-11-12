@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Mutagen Control 8.2 - EXE builder
set "PYTHONUTF8=1"

echo ========================================================
echo   MUTAGEN CONTROL 8.2 - Standalone Windows EXE (one-file)
echo ========================================================
echo.
echo NOTE: For the fastest application startup, use build_fast.cmd.
echo.
if /I not "%OS%"=="Windows_NT" goto :error
if not exist "app.py" goto :error

if not exist ".venv\Scripts\python.exe" (
  echo [1/5] Preparing local Python environment...
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
  if errorlevel 1 goto :error
)

echo [2/5] Checking Python and dependencies...
".venv\Scripts\python.exe" -c "import sys; assert (3,11)<=sys.version_info[:2]<(3,14), 'Use Python 3.11 through 3.13'; print(sys.version)"
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt -r requirements-build.txt
if errorlevel 1 goto :error

echo [3/5] Checking syntax and logic tests...
".venv\Scripts\python.exe" -m compileall -q app.py performance.py monitoring.py mutagen_client.py insights.py endpoint_inspector.py server_groups.py log_stream.py async_recorder.py sync_profiles.py
if errorlevel 1 goto :error
".venv\Scripts\python.exe" verify_source.py
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pytest -q tests --ignore=tests/test_gui_smoke.py
if errorlevel 1 goto :error

echo [4/5] Qt offscreen UI test...
".venv\Scripts\python.exe" -c "import PySide6; print('Qt ready')"
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -c "import PySide6, shiboken6"
if errorlevel 1 goto :error
set "QT_QPA_PLATFORM=offscreen"
".venv\Scripts\python.exe" -m pytest -q tests\test_gui_smoke.py
if errorlevel 1 goto :error
set "QT_QPA_PLATFORM="

echo [5/5] Building EXE (the first launch will unpack Qt)...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --noupx --name MutagenControl --icon "assets\mutagencontrol.ico" --version-file "assets\version_info.txt" --distpath "dist" --workpath "build" app.py
if errorlevel 1 goto :error
if not exist "dist\MutagenControl.exe" goto :error
echo [SELF-TEST] Checking the packaged EXE without connecting to Mutagen...
set "QT_QPA_PLATFORM=offscreen"
"dist\MutagenControl.exe" --self-test
if errorlevel 1 goto :error
set "QT_QPA_PLATFORM="

echo.
echo ========================================================
echo DONE: %CD%\dist\MutagenControl.exe
echo The standalone EXE includes Python and Qt; the Mutagen CLI remains external.
echo ========================================================
pause
exit /b 0

:error
set "QT_QPA_PLATFORM="
echo.
echo [ERROR] Build failed. Check the output above.
echo Requirements: Windows 10/11, Python 3.11–3.13, and internet access for pip.
pause
exit /b 1
