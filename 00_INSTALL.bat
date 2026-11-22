@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0scripts\00_INSTALL.bat" %*
exit /b %ERRORLEVEL%
