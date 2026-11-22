@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Verbatim AI - One-Click Installer
cd /d "%~dp0\.."

echo ========================================================
echo   Verbatim AI - Automated Windows Installer
echo   Tagline: Every Word Matters.
echo ========================================================
echo.
echo Launching installer bootstrapper...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1" %*
set "INSTALL_EXIT=%ERRORLEVEL%"

if not "%INSTALL_EXIT%"=="0" (
    echo.
    echo ========================================================
    echo [ERROR] Installation did not complete successfully (Exit code: %INSTALL_EXIT%).
    echo Please review the installation log in the logs\ folder for details.
    echo ========================================================
    echo.
    pause
    exit /b %INSTALL_EXIT%
)

echo.
echo Press any key to exit installer...
pause >nul
exit /b 0
