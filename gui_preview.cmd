@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Nejprve spustte start.cmd, aby se nainstalovaly zavislosti.
    pause
    exit /b 1
)
set "QT_QPA_PLATFORM=offscreen"
for %%S in (1 1.5 2) do (
    set "QT_SCALE_FACTOR=%%S"
    ".venv\Scripts\python.exe" gui_capture.py "preview-%%S"
    if errorlevel 1 goto :error
)
echo Ulozeny obrazky do preview-1, preview-1.5, preview-2
pause
exit /b 0
:error
echo [CHYBA] Nepodarilo se vykreslit demo screenshoty.
pause
exit /b 1
