@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "IS_NON_INTERACTIVE=0"
for %%a in (%*) do (
    if /i "%%a"=="-NonInteractive" set "IS_NON_INTERACTIVE=1"
)

call "%~dp0scripts\00_INSTALL.bat" %*
set "INSTALLER_EXIT=%ERRORLEVEL%"

if "%INSTALLER_EXIT%"=="0" exit /b 0

echo.
echo ========================================================
echo [INSTALLER TERMINATED WITH ERROR CODE %INSTALLER_EXIT%]
echo Log file: %~dp0backend\storage\logs\install.log
echo ========================================================
echo.
if "%IS_NON_INTERACTIVE%"=="0" (
    echo Press any key to close this window...
    pause >nul
)
exit /b %INSTALLER_EXIT%
