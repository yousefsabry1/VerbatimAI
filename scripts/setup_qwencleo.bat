@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Verbatim AI - Setup QwenCleo 4-bit Arbiter
cd /d "%~dp0\.."

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_qwencleo.ps1" %*

echo.
echo Press any key to exit...
pause >nul
exit /b %ERRORLEVEL%
