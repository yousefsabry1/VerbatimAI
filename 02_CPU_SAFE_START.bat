@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0scripts\02_CPU_SAFE_START.bat" %*
exit /b %ERRORLEVEL%
