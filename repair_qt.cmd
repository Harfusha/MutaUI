@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Project virtual environment not found. Run start.cmd first.
  exit /b 1
)
echo Reinstalling the tested PySide6 runtime in the project environment...
".venv\Scripts\python.exe" -m pip install --force-reinstall "PySide6==6.12.0"
if errorlevel 1 goto :error
echo Checking Qt imports...
".venv\Scripts\python.exe" -c "from PySide6.QtCore import Qt; from PySide6.QtGui import QPixmap; from PySide6.QtWidgets import QApplication; print('Qt imports OK')"
if errorlevel 1 goto :error
echo Qt runtime repaired. Start the application with start.cmd.
exit /b 0
:error
echo Qt repair failed. Copy this output for diagnostics.
exit /b 1
