@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Mutagen Control 8.2 - Debug builder
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\python.exe" (
  echo Run start.cmd or build_fast.cmd first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt -r requirements-build.txt
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
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --console --noupx --name MutagenControl-Debug --icon "assets\mutagencontrol.ico" --version-file "assets\version_info.txt" --distpath "dist-debug" --workpath "build-debug" app.py
if errorlevel 1 goto :error
echo.
set "QT_QPA_PLATFORM=offscreen"
"dist-debug\MutagenControl-Debug\MutagenControl-Debug.exe" --self-test
if errorlevel 1 goto :error
set "QT_QPA_PLATFORM="
echo DONE: dist-debug\MutagenControl-Debug\MutagenControl-Debug.exe
pause
exit /b 0
:error
set "QT_QPA_PLATFORM="
echo The debug build failed or the security and GUI tests did not pass.
pause
exit /b 1
