@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Verbatim AI - Every Word Matters.
cd /d "%~dp0\.."

echo ========================================================
echo   Starting Verbatim AI Application
echo   Tagline: Every Word Matters.
echo ========================================================
echo.

if exist "backend\.venv\Scripts\activate.bat" (
    call backend\.venv\Scripts\activate.bat
    set "PY_EXEC=python"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "PY_EXEC=py -3.11"
    ) else (
        set "PY_EXEC=python"
    )
)

:: Add NVIDIA pip library folders to PATH if present
if exist "backend\.venv\Lib\site-packages\nvidia\cublas\bin" (
    set "PATH=%CD%\backend\.venv\Lib\site-packages\nvidia\cublas\bin;!PATH!"
)
if exist "backend\.venv\Lib\site-packages\nvidia\cudnn\bin" (
    set "PATH=%CD%\backend\.venv\Lib\site-packages\nvidia\cudnn\bin;!PATH!"
)

:: Automatically launch default browser to local URL after 2 seconds
start "" /b powershell -NoProfile -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000'"

echo.
echo Application server is running at:
echo   --^> http://127.0.0.1:8000
echo.
echo Your default web browser will open automatically.
echo Keep this terminal window open while using Verbatim AI.
echo Press Ctrl+C or close this window to stop the server.
echo.

cd backend
%PY_EXEC% -m uvicorn app.main:app --host 127.0.0.1 --port 8000

pause
