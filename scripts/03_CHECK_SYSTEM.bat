@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Verbatim AI - System Diagnostics
cd /d "%~dp0\.."

echo ========================================================
echo   Verbatim AI - Hardware and Dependency Diagnostics
echo   Tagline: Every Word Matters.
echo ========================================================
echo.

echo 1. Checking Operating System...
ver
echo.

echo 2. Checking Python (3.10+ required)...
py -3.11 --version >nul 2>nul
if not errorlevel 1 (
    for /f "delims=" %%v in ('py -3.11 --version 2^>^&1') do echo [OK] Python 3.11 detected: %%v
) else (
    python --version >nul 2>nul
    if not errorlevel 1 (
        for /f "delims=" %%v in ('python --version 2^>^&1') do echo [OK] Python detected: %%v
    ) else (
        echo [FAIL] Python was not found in PATH or py launcher.
        echo Please install Python 3.11 from https://www.python.org/downloads/
    )
)
echo.

echo 3. Checking FFmpeg and FFprobe (Audio Processing)...
ffmpeg -version >nul 2>nul
if not errorlevel 1 (
    for /f "tokens=1-3" %%a in ('ffmpeg -version 2^>^&1') do (
        echo [OK] FFmpeg found: %%a %%b %%c
        goto :after_ffmpeg
    )
) else (
    echo [WARNING] FFmpeg was not detected in PATH.
    echo Local audio conversions and Whisper decoding will rely on imageio-ffmpeg.
)
:after_ffmpeg

ffprobe -version >nul 2>nul
if not errorlevel 1 (
    for /f "tokens=1-3" %%a in ('ffprobe -version 2^>^&1') do (
        echo [OK] FFprobe found: %%a %%b %%c
        goto :after_ffprobe
    )
) else (
    echo [WARNING] FFprobe was not detected in PATH.
)
:after_ffprobe
echo.

echo 4. Checking Node.js and npm (Frontend Development)...
node --version >nul 2>nul
if not errorlevel 1 (
    for /f "delims=" %%v in ('node --version 2^>^&1') do echo [OK] Node.js found: %%v
) else (
    echo [INFO] Node.js not detected - only required when rebuilding frontend from source.
)
if exist "frontend\dist\index.html" (
    echo [OK] Pre-compiled frontend bundle is present in frontend\dist.
) else (
    echo [WARNING] frontend\dist\index.html not found. Node.js required to build frontend.
)
echo.

echo 5. Checking NVIDIA GPU and CUDA Drivers...
where nvidia-smi >nul 2>nul
if not errorlevel 1 (
    echo [OK] NVIDIA GPU detected via nvidia-smi:
    nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version --format=csv,noheader
) else (
    echo [INFO] nvidia-smi not detected. The application will run smoothly in CPU Safe Mode.
)
echo.

echo 6. Checking Backend Virtual Environment...
if exist "backend\.venv\Scripts\activate.bat" (
    echo [OK] Backend virtual environment found at backend\.venv.
) else (
    echo [INFO] Backend virtual environment not initialized yet.
    echo Run 00_INSTALL.bat to set up the environment automatically.
)
echo.

echo ========================================================
echo   Diagnostics Complete!
echo ========================================================
echo.
pause
