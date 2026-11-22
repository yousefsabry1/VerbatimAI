@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Verbatim AI - Every Word Matters.
cd /d "%~dp0\.."

set "PROJECT_ROOT=%CD%"
set "VENV_DIR=%PROJECT_ROOT%\backend\.venv"
set "PY_EXEC=%VENV_DIR%\Scripts\python.exe"
set "DIST_INDEX=%PROJECT_ROOT%\frontend\dist\index.html"

echo ========================================================
echo   Verbatim AI - Every Word Matters.
echo ========================================================
echo.

:: 1. Verify environment installation
if not exist "%PY_EXEC%" (
    echo [WARNING] Python virtual environment was not found at:
    echo   %VENV_DIR%
    echo.
    echo Verbatim AI must be installed before running.
    set /p "RUN_INSTALL=Would you like to run the automated installer (00_INSTALL.bat) now? (Y/N): "
    if /i "!RUN_INSTALL!"=="Y" (
        call "%PROJECT_ROOT%\00_INSTALL.bat"
        if not exist "%PY_EXEC%" (
            echo [ERROR] Installation was not completed. Cannot proceed.
            pause
            exit /b 1
        )
    ) else (
        echo Please run 00_INSTALL.bat to configure the application before launching.
        pause
        exit /b 1
    )
)

if not exist "%DIST_INDEX%" (
    echo [WARNING] Production frontend bundle was not found at:
    echo   %DIST_INDEX%
    echo.
    echo The graphical user interface has not been built yet.
    set /p "RUN_INSTALL=Would you like to run the automated installer now to build the frontend? (Y/N): "
    if /i "!RUN_INSTALL!"=="Y" (
        call "%PROJECT_ROOT%\00_INSTALL.bat"
        if not exist "%DIST_INDEX%" (
            echo [ERROR] Frontend build failed or was skipped. Cannot launch full interface.
            pause
            exit /b 1
        )
    ) else (
        echo Please run 00_INSTALL.bat to build the frontend.
        pause
        exit /b 1
    )
)

:: 2. Prepend managed tools to PATH
if exist "%PROJECT_ROOT%\tools\ffmpeg\bin" (
    set "PATH=%PROJECT_ROOT%\tools\ffmpeg\bin;!PATH!"
)
if exist "%PROJECT_ROOT%\tools\node" (
    set "PATH=%PROJECT_ROOT%\tools\node;!PATH!"
)

:: Prepend NVIDIA CUDA DLL directories from site-packages if present
if exist "%VENV_DIR%\Lib\site-packages\nvidia\cublas\bin" (
    set "PATH=%VENV_DIR%\Lib\site-packages\nvidia\cublas\bin;!PATH!"
)
if exist "%VENV_DIR%\Lib\site-packages\nvidia\cudnn\bin" (
    set "PATH=%VENV_DIR%\Lib\site-packages\nvidia\cudnn\bin;!PATH!"
)
if exist "%VENV_DIR%\Lib\site-packages\nvidia\cuda_nvrtc\bin" (
    set "PATH=%VENV_DIR%\Lib\site-packages\nvidia\cuda_nvrtc\bin;!PATH!"
)

:: 3. Smoke check backend import
"%PY_EXEC%" -c "import app.main" 2>nul
if errorlevel 1 (
    echo [ERROR] Backend application module failed import validation.
    echo Testing Python traceback:
    "%PY_EXEC%" -c "import app.main"
    echo.
    echo Please run 00_INSTALL.bat to repair dependencies.
    pause
    exit /b 1
)

:: 4. Check port 8000
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$c = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue; if ($c) { try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/health' -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop; if ($r.StatusCode -eq 200 -and $r.Content -like '*Verbatim AI*') { Write-Host '[OK] Verbatim AI is already running and healthy at http://127.0.0.1:8000' -ForegroundColor Green; Write-Host 'Opening default browser...' -ForegroundColor Cyan; Start-Process 'http://127.0.0.1:8000'; exit 42; } } catch {} Write-Host ('[WARNING] Port 8000 is occupied by another process (PID: ' + $c[0].OwningProcess + ').') -ForegroundColor Yellow; }"
if "%ERRORLEVEL%"=="42" (
    echo.
    echo Verbatim AI is already active. Browser opened.
    pause
    exit /b 0
)

:: 5. Launch background health monitor and browser opener
echo Starting Verbatim AI server...
echo Waiting for application health confirmation...
echo.

set "HEALTH_SCRIPT=$url = 'http://127.0.0.1:8000/api/health'; $maxWait = 45; $waited = 0; while ($waited -lt $maxWait) { try { $res = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop; if ($res.StatusCode -eq 200) { Write-Host ''; Write-Host '========================================================' -ForegroundColor Green; Write-Host '  Verbatim AI is ready and healthy!' -ForegroundColor Green; Write-Host '  Application URL: http://127.0.0.1:8000' -ForegroundColor White; Write-Host '========================================================' -ForegroundColor Green; Write-Host ''; Start-Process 'http://127.0.0.1:8000'; break; } } catch {} Start-Sleep -Milliseconds 500; $waited += 0.5; }; if ($waited -ge $maxWait) { Write-Host '[ERROR] Server did not become healthy within 45s.' -ForegroundColor Red; }"

start "" /b powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "!HEALTH_SCRIPT!"

:: 6. Launch uvicorn server in foreground
cd /d "%PROJECT_ROOT%\backend"
"%PY_EXEC%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
set "UVICORN_EXIT=%ERRORLEVEL%"

if not "%UVICORN_EXIT%"=="0" (
    echo.
    echo ========================================================
    echo [ERROR] Verbatim AI server stopped unexpectedly (Exit code: %UVICORN_EXIT%).
    echo Keep this window open to inspect the error log above.
    echo ========================================================
    echo.
    pause
    exit /b %UVICORN_EXIT%
)

pause
exit /b 0
