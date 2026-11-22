@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Verbatim AI - System Diagnostics
cd /d "%~dp0\.."

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_system.ps1" %*

echo.
echo Press any key to exit diagnostics...
pause >nul
exit /b 0
