@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0scripts\setup_qwencleo.bat" %*
exit /b %ERRORLEVEL%
