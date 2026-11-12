@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Nejprve spustte start.cmd & pause & exit /b 1)
".venv\Scripts\python.exe" app.py --demo
if errorlevel 1 pause
