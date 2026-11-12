@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\python.exe" (
  echo [CHYBA] Nejprve spustte start.cmd nebo build_fast.cmd.
  pause
  exit /b 1
)
echo [1/3] Kontrola zdrojovych souboru...
".venv\Scripts\python.exe" verify_source.py
if errorlevel 1 goto :error
echo [2/3] Logicke a databazove testy...
".venv\Scripts\python.exe" -m pytest -q tests --ignore=tests/test_gui_smoke.py
if errorlevel 1 goto :error
echo [3/3] Qt GUI test bez viditelneho okna...
".venv\Scripts\python.exe" -c "import PySide6, shiboken6"
if errorlevel 1 goto :error
set "QT_QPA_PLATFORM=offscreen"
".venv\Scripts\python.exe" -m pytest -q tests\test_gui_smoke.py
if errorlevel 1 goto :error
set "QT_QPA_PLATFORM="
echo OK: kontroly prosly.
pause
exit /b 0
:error
set "QT_QPA_PLATFORM="
echo [CHYBA] Kontrola selhala, nevytvarejte produkcni EXE.
pause
exit /b 1
