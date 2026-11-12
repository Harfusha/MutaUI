@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Run start.cmd or build_fast.cmd first.
  pause
  exit /b 1
)
echo [1/3] Checking source files...
".venv\Scripts\python.exe" verify_source.py
if errorlevel 1 goto :error
echo [2/3] Logic and database tests...
".venv\Scripts\python.exe" -m pytest -q tests --ignore=tests/test_gui_smoke.py
if errorlevel 1 goto :error
echo [3/3] Qt GUI test without a visible window...
".venv\Scripts\python.exe" -c "import PySide6, shiboken6"
if errorlevel 1 goto :error
set "QT_QPA_PLATFORM=offscreen"
".venv\Scripts\python.exe" -m pytest -q tests\test_gui_smoke.py
if errorlevel 1 goto :error
set "QT_QPA_PLATFORM="
echo OK: all checks passed.
pause
exit /b 0
:error
set "QT_QPA_PLATFORM="
echo [ERROR] Check failed; do not create a production EXE.
pause
exit /b 1
