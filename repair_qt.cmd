@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Project virtual environment not found. Run start.cmd first.
  exit /b 1
)
echo Reinstalling the tested PySide6 runtime in the project environment...
".venv\Scripts\python.exe" -m pip install --force-reinstall "PySide6-Essentials==6.8.3" "shiboken6==6.8.3"
if errorlevel 1 goto :error
echo Checking Qt imports...
".venv\Scripts\python.exe" -c "import PySide6, shiboken6; from PySide6.QtCore import Qt; from PySide6.QtGui import QPixmap; from PySide6.QtWidgets import QApplication; assert PySide6.__version__ == '6.8.3' and shiboken6.__version__ == '6.8.3'; print('Qt 6.8.3 runtime OK')"
if errorlevel 1 goto :error
echo Qt runtime repaired. Start the application with start.cmd.
exit /b 0
:error
echo Qt repair failed. Copy this output for diagnostics.
exit /b 1
