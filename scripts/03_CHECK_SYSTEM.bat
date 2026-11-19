@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Verbatim AI - System Diagnostics
cd /d "%~dp0\.."

echo ========================================================
echo   Verbatim AI - Hardware & Dependency Diagnostic Check
echo ========================================================
echo.

echo 1. Checking Operating System...
ver
echo.

echo 2. Checking Python...
py -3.11 --version 2>nul
if errorlevel 1 (
    python --version 2>nul
    if errorlevel 1 (
        echo [FAIL] Python is not installed or not in PATH.
    ) else (
        echo [OK] Python found.
    )
) else (
    echo [OK] Python 3.11 detected via py launcher.
)
echo.

echo 3. Checking FFmpeg & FFprobe...
ffmpeg -version >nul 2>nul
if not errorlevel 1 (
    echo [OK] FFmpeg found:
    ffmpeg -version | findstr "version"
) else (
    echo [WARNING] ffmpeg not found in PATH.
)

ffprobe -version >nul 2>nul
if not errorlevel 1 (
    echo [OK] FFprobe found:
    ffprobe -version | findstr "version"
) else (
    echo [WARNING] ffprobe not found in PATH.
)
echo.

echo 4. Checking Node.js & npm...
node --version >nul 2>nul
if not errorlevel 1 (
    echo [OK] Node.js found:
    node --version
) else (
    echo [INFO] Node.js not detected (only needed if building frontend from source).
)
echo.

echo 5. Checking NVIDIA GPU & CUDA Drivers...
where nvidia-smi >nul 2>nul
if not errorlevel 1 (
    echo [OK] NVIDIA GPU detected via nvidia-smi:
    nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version --format=csv,noheader
) else (
    echo [INFO] nvidia-smi not detected. The application will run smoothly in CPU Safe Mode.
)
echo.

where cublas64_12.dll >nul 2>nul
if not errorlevel 1 (
    echo [OK] cublas64_12.dll found in system PATH.
) else (
    echo [INFO] cublas64_12.dll not in global PATH (Faster-Whisper auto-fallback to CPU is active).
)

echo.
echo ========================================================
echo Diagnostics Complete.
echo ========================================================
pause
