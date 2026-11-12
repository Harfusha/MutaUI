@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run start.cmd first to install dependencies.
    pause
    exit /b 1
)
set "QT_QPA_PLATFORM=offscreen"
for %%S in (1 1.5 2) do (
    set "QT_SCALE_FACTOR=%%S"
    ".venv\Scripts\python.exe" gui_capture.py "preview-%%S"
    if errorlevel 1 goto :error
)
echo Screenshots saved to preview-1, preview-1.5, and preview-2
pause
exit /b 0
:error
echo [ERROR] Could not render demo screenshots.
pause
exit /b 1
