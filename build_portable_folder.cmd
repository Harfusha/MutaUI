@echo off
setlocal
cd /d "%~dp0"
call "%~dp0build_fast.cmd"
exit /b %errorlevel%
