@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Verbatim AI - Safe CPU Mode
cd /d "%~dp0\.."

echo ========================================================
echo   Starting Verbatim AI (CPU Safe Mode)
echo ========================================================
echo.
echo Forcing CPU processing with int8 quantization.
echo This mode bypasses GPU CUDA drivers and runs reliably on any computer.
echo.

set "VERBATIM_FORCE_CPU=1"
call "%~dp001_START_VERBATIM_AI.bat"
