@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0scripts\03_CHECK_SYSTEM.bat" %*
exit /b %ERRORLEVEL%
