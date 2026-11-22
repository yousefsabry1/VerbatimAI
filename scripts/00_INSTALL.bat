@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Install Verbatim AI
cd /d "%~dp0\.."

echo ========================================================
echo   Verbatim AI - One-Click Installer
echo   Tagline: Every Word Matters.
echo ========================================================
echo.
echo Checking required dependencies...
echo.

:: 0. Initialize .env if missing
if not exist ".env" (
    if exist ".env.example" (
        copy /y ".env.example" ".env" >nul
        echo [OK] Initialized configuration file from .env.example.
    )
)

:: Ensure storage directories exist
if not exist "backend\storage\uploads" mkdir "backend\storage\uploads"
if not exist "backend\storage\outputs" mkdir "backend\storage\outputs"
if not exist "backend\storage\previews" mkdir "backend\storage\previews"
if not exist "backend\storage\models" mkdir "backend\storage\models"

:: 1. Check Python
set "PY_CMD="
py -3.11 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=py -3.11"
) else (
    python -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "PY_CMD=python"
    )
)

if not defined PY_CMD (
    echo [ERROR] Python 3.11 or 3.10 was not found on your system!
    echo Please install Python 3.11 from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo [OK] Using Python: %PY_CMD%

:: 2. Check FFmpeg
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [WARNING] FFmpeg was not detected in PATH.
    echo The app will attempt to use bundled/imageio FFmpeg binaries.
    echo For best performance, install FFmpeg from https://gyan.dev/ffmpeg/builds/
) else (
    echo [OK] FFmpeg is installed and available in PATH.
)

:: 3. Setup Python Virtual Environment in backend
echo.
echo Setting up Python virtual environment...
if not exist "backend\.venv\Scripts\activate.bat" (
    %PY_CMD% -m venv backend\.venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

call backend\.venv\Scripts\activate.bat

echo Upgrading pip and build tools...
python -m pip install --upgrade pip setuptools wheel --quiet

echo Installing backend Python libraries (FastAPI, Faster-Whisper, CTranslate2, etc.)...
echo This may take a few minutes on the first run...
python -m pip install -r backend\requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install Python dependencies. Please check your internet connection.
    pause
    exit /b 1
)
echo [OK] Backend Python dependencies installed successfully.

:: 4. Check Node.js and build frontend if needed
if not exist "frontend\dist\index.html" (
    echo.
    echo Building React production frontend...
    where npm >nul 2>nul
    if not errorlevel 1 (
        pushd frontend
        call npm install
        call npm run build
        popd
        if exist "frontend\dist\index.html" (
            echo [OK] Frontend built successfully.
        ) else (
            echo [WARNING] Frontend build did not generate dist folder.
        )
    ) else (
        echo [INFO] Node.js/npm not found. Pre-built frontend will be served if available.
    )
) else (
    echo [OK] Pre-built frontend found in frontend\dist.
)

echo.
echo ========================================================
echo   Verbatim AI Installation Complete!
echo   To launch the application, run: 01_START_VERBATIM_AI.bat
echo ========================================================
echo.
pause
exit /b 0
