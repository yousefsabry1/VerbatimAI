@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0scripts\01_START_VERBATIM_AI.bat" %*
exit /b %ERRORLEVEL%
