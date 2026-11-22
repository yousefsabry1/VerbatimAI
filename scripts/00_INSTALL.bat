@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Verbatim AI - One-Click Installer
cd /d "%~dp0\.."

set "PROJECT_ROOT=%CD%"
set "LOG_PATH=%PROJECT_ROOT%\backend\storage\logs\install.log"

set "IS_NON_INTERACTIVE=0"
for %%a in (%*) do (
    if /i "%%a"=="-NonInteractive" set "IS_NON_INTERACTIVE=1"
)

echo ========================================================
echo   Verbatim AI - Automated Windows Installer
echo   Tagline: Every Word Matters.
echo ========================================================
echo.
echo Launching installer bootstrapper...
echo Project Directory: %PROJECT_ROOT%
echo Log File Path    : %LOG_PATH%
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1" %*
set "INSTALL_EXIT=%ERRORLEVEL%"

if "%INSTALL_EXIT%"=="0" goto :install_success

echo.
echo ========================================================
echo [ERROR] Installation did not complete successfully.
echo Exit code: %INSTALL_EXIT%
echo.
echo Detailed diagnostic log:
echo   %LOG_PATH%
echo.
if exist "%LOG_PATH%" (
    echo Last 10 lines of installation log:
    echo --------------------------------------------------------
    powershell.exe -NoProfile -Command "Get-Content -Path '%LOG_PATH%' -Tail 10 -ErrorAction SilentlyContinue"
    echo --------------------------------------------------------
    echo.
)
echo Next Steps:
echo   1. Review the log file above for specific error details.
echo   2. Ensure internet connectivity to python.org, github.com, and huggingface.co.
echo   3. Run 00_INSTALL.bat again to retry automated setup.
echo   4. If the error persists, open an issue with the log file at:
echo      https://github.com/yousefsabry1/VerbatimAI/issues
echo ========================================================
echo.
if "%IS_NON_INTERACTIVE%"=="0" (
    echo Press any key to close this installer window...
    pause >nul
)
exit /b %INSTALL_EXIT%

:install_success
echo.
echo ========================================================
echo   Installation completed successfully!
echo ========================================================
echo.
if "%IS_NON_INTERACTIVE%"=="0" (
    echo Press any key to exit installer...
    pause >nul
)
exit /b 0
