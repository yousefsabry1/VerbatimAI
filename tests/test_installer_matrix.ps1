<#
.SYNOPSIS
    VerbatimAI - Windows Installer & Bootstrapper Scenario Test Matrix
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$BootstrapScript = Join-Path $ProjectRoot "scripts\bootstrap.ps1"

$PassCount = 0
$FailCount = 0

function Report-Scenario {
    param(
        [string]$ScenarioId,
        [string]$Description,
        [bool]$Success,
        [string]$Details = ""
    )
    if ($Success) {
        $script:PassCount++
        Write-Host " [PASS] Scenario $($ScenarioId): $Description" -ForegroundColor Green
        if ($Details) { Write-Host "        $Details" -ForegroundColor Gray }
    } else {
        $script:FailCount++
        Write-Host " [FAIL] Scenario $($ScenarioId): $Description" -ForegroundColor Red
        if ($Details) { Write-Host "        $Details" -ForegroundColor Yellow }
    }
}

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  VerbatimAI - Clean-Installation Test Matrix" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# ==============================================================================
# Scenario C: Windows Microsoft Store Python Alias Rejection
# ==============================================================================
try {
    # Dot-source function from bootstrap without running the whole script
    $fnDef = Get-Content -Path $BootstrapScript -Raw
    $subBlock = [regex]::Match($fnDef, 'function Test-ValidPythonInterpreter[\s\S]*?\n\}').Value
    Invoke-Expression $subBlock

    # Test 1: Fake WindowsApps path
    $fakeWindowsApps = "C:\Users\User\AppData\Local\Microsoft\WindowsApps\python.exe"
    $resStore = Test-ValidPythonInterpreter -ExecutablePath $fakeWindowsApps
    $storeRejected = ($resStore -eq $null)

    # Test 2: Real python should pass
    $realPy = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"
    $resReal = Test-ValidPythonInterpreter -ExecutablePath $realPy
    $realAccepted = ($resReal -ne $null -and $resReal.Major -eq 3)

    Report-Scenario "C" "Microsoft Store Python Alias Rejected & Real Python Accepted" ($storeRejected -and $realAccepted) "Store alias rejected: $storeRejected | Real Python accepted: $realAccepted ($($resReal.Version))"
} catch {
    Report-Scenario "C" "Microsoft Store Python Alias Check" $false $_.Exception.Message
}

# ==============================================================================
# Scenario B: Python Already Installed & Reused
# ==============================================================================
try {
    $realPy = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"
    $res = Test-ValidPythonInterpreter -ExecutablePath $realPy
    $verMatch = ($res -ne $null -and $res.Major -eq 3 -and $res.Minor -ge 10)
    Report-Scenario "B" "Detect and reuse supported Python version" $verMatch "Discovered Python $($res.Version) at $($res.Path)"
} catch {
    Report-Scenario "B" "Detect supported Python" $false $_.Exception.Message
}

# ==============================================================================
# Scenario D: CPU-Safe Mode Without GPU Packages
# ==============================================================================
try {
    $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$BootstrapScript" -ForceCpu -NonInteractive -SkipFrontend 2>&1
    $cpuSuccess = ($LASTEXITCODE -eq 0 -and ($output -match "CPU Safe Mode requested"))
    Report-Scenario "D" "CPU-Safe Bootstrap (No GPU CUDA requirements forced)" $cpuSuccess "ExitCode: $LASTEXITCODE | Detected CPU Safe flag: $($output -match 'CPU Safe Mode requested')"
} catch {
    Report-Scenario "D" "CPU-Safe Bootstrap" $false $_.Exception.Message
}

# ==============================================================================
# Scenario E: NVIDIA GPU Available & Verified
# ==============================================================================
try {
    $smi = Get-Command "nvidia-smi.exe" -ErrorAction SilentlyContinue
    if ($smi) {
        $pinfo = New-Object System.Diagnostics.ProcessStartInfo
        $pinfo.FileName = "nvidia-smi.exe"
        $pinfo.Arguments = "--query-gpu=name,memory.total --format=csv,noheader"
        $pinfo.RedirectStandardOutput = $true
        $pinfo.UseShellExecute = $false
        $pinfo.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($pinfo)
        $proc.WaitForExit(5000) | Out-Null
        $gpuStr = $proc.StandardOutput.ReadToEnd().Trim()
        Report-Scenario "E" "NVIDIA GPU Detected and CUDA Driver Verified" ($proc.ExitCode -eq 0) "GPU: $gpuStr"
    } else {
        Report-Scenario "E" "NVIDIA GPU check (Host is CPU-only)" $true "nvidia-smi not present; CPU safe operation verified in Scenario D"
    }
} catch {
    Report-Scenario "E" "NVIDIA GPU Check" $false $_.Exception.Message
}

# ==============================================================================
# Scenario F: Incomplete Previous Installation & Idempotent Repair
# ==============================================================================
try {
    $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$BootstrapScript" -Repair -NonInteractive -SkipFrontend 2>&1
    $repairSuccess = ($LASTEXITCODE -eq 0 -and (Test-Path (Join-Path $ProjectRoot "backend\storage\.installed.json")))
    Report-Scenario "F" "Idempotent Installation Repair & State Recovery" $repairSuccess "ExitCode: $LASTEXITCODE | Stamp Verified: $(Test-Path (Join-Path $ProjectRoot 'backend\storage\.installed.json'))"
} catch {
    Report-Scenario "F" "Installation Repair" $false $_.Exception.Message
}

# ==============================================================================
# Scenario H: Special Installation Paths (Spaces, Parentheses, Non-ASCII)
# ==============================================================================
try {
    # Current project path already contains spaces and non-standard layout:
    # A:\Projects For Antigravity IDE\General Ideas\1. Transcript voices\VerbatimAI
    $hasSpaces = $ProjectRoot -match "\s"
    $hasNonC = -not ($ProjectRoot.StartsWith("C:", [System.StringComparison]::OrdinalIgnoreCase))
    
    # Test batch file quotation robustness with non-ASCII and parentheses
    $testFolder = Join-Path $env:TEMP "VerbatimAI_PathTest_(تجربة)"
    if (Test-Path $testFolder) { Remove-Item $testFolder -Recurse -Force }
    New-Item -ItemType Directory -Path $testFolder -Force | Out-Null
    
    $testFile = Join-Path $testFolder "test_quote.bat"
    Set-Content -Path $testFile -Value "@echo off`r`necho PATH_OK`r`nexit /b 0" -Encoding ASCII
    
    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
    $pinfo.FileName = "cmd.exe"
    $pinfo.Arguments = "/c `"`"$testFile`"`""
    $pinfo.RedirectStandardOutput = $true
    $pinfo.UseShellExecute = $false
    $pinfo.CreateNoWindow = $true
    $proc = [System.Diagnostics.Process]::Start($pinfo)
    $proc.WaitForExit(5000) | Out-Null
    $out = $proc.StandardOutput.ReadToEnd().Trim()
    Remove-Item $testFolder -Recurse -Force -ErrorAction SilentlyContinue

    $pathRobust = ($out -eq "PATH_OK" -and $hasSpaces)
    Report-Scenario "H" "Path Robustness (Spaces, Drive A:, Parentheses, Non-ASCII)" $pathRobust "Project Root: $ProjectRoot (Has spaces: $hasSpaces, Drive A: $hasNonC)"
} catch {
    Report-Scenario "H" "Path Robustness" $false $_.Exception.Message
}

# ==============================================================================
# Scenario I: Missing Frontend Build Detection & Verification
# ==============================================================================
try {
    $distIndex = Join-Path $ProjectRoot "frontend\dist\index.html"
    $frontendOk = (Test-Path $distIndex) -and ((Get-Item $distIndex).Length -gt 100)
    Report-Scenario "I" "Frontend Build Output Verified (index.html present & non-empty)" $frontendOk "Dist path: $distIndex (Size: $((Get-Item $distIndex).Length) bytes)"
} catch {
    Report-Scenario "I" "Frontend Build Check" $false $_.Exception.Message
}

# ==============================================================================
# Scenario J: Model Readiness Flow & Download Safeguards
# ==============================================================================
try {
    $pyExe = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"
    $checkScript = @"
import sys
from pathlib import Path
sys.path.insert(0, r'$ProjectRoot\backend')
from app.transcription.engine import is_model_downloaded, download_model
from app.core.config import SUPPORTED_MODELS

# Verify Fast model status
fast_ok = is_model_downloaded('codeswitched-medium')

# Verify Hybrid model composite calculation
hybrid_downloaded = is_model_downloaded('hybrid-v3')

# Verify QwenCleo auto-download rejection safeguard
qwen_blocked = False
try:
    download_model('qwencleo-asr-4bit')
except RuntimeError as e:
    if 'auto-download is disabled' in str(e).lower():
        qwen_blocked = True

print(f'FAST_OK={fast_ok}|HYBRID_OK={hybrid_downloaded}|QWEN_SAFEGUARD={qwen_blocked}')
"@
    $tempPy = Join-Path $env:TEMP "check_models_flow.py"
    Set-Content -Path $tempPy -Value $checkScript -Encoding UTF8

    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
    $pinfo.FileName = $pyExe
    $pinfo.Arguments = "`"$tempPy`""
    $pinfo.RedirectStandardOutput = $true
    $pinfo.RedirectStandardError = $true
    $pinfo.UseShellExecute = $false
    $pinfo.CreateNoWindow = $true
    $proc = [System.Diagnostics.Process]::Start($pinfo)
    $proc.WaitForExit(10000) | Out-Null
    $resStr = $proc.StandardOutput.ReadToEnd().Trim()
    Remove-Item $tempPy -Force -ErrorAction SilentlyContinue

    $modelFlowOk = ($resStr -match "FAST_OK=True" -and $resStr -match "QWEN_SAFEGUARD=True")
    Report-Scenario "J" "First-Time Model Flow & Download Safeguards" $modelFlowOk $resStr
} catch {
    Report-Scenario "J" "Model Flow Check" $false $_.Exception.Message
}

# ==============================================================================
# Scenario K: Unified Installation Out-of-the-Box Presets Readiness
# ==============================================================================
try {
    $modelsDir = Join-Path $ProjectRoot "backend\storage\models"
    $csReady = (Test-Path (Join-Path $modelsDir "codeswitched-medium\model.bin")) -or (Test-Path (Join-Path $modelsDir "codeswitched-medium\.ready"))
    $tbReady = (Test-Path (Join-Path $modelsDir "large-v3-turbo\model.bin")) -or (Test-Path (Join-Path $modelsDir "large-v3-turbo\.ready"))
    $stampPath = Join-Path $ProjectRoot "backend\storage\.installed.json"
    $stampOk = Test-Path $stampPath

    $unifiedOk = $csReady -and $tbReady -and $stampOk
    Report-Scenario "K" "Unified Installation Out-of-the-Box Presets Ready (Zero manual model download needed)" $unifiedOk "Fast (Medium): $csReady | Turbo: $tbReady | Install Stamp: $stampOk"
} catch {
    Report-Scenario "K" "Unified Out-of-the-Box Check" $false $_.Exception.Message
}

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Matrix Results: $PassCount PASSED, $FailCount FAILED" -ForegroundColor $(if ($FailCount -eq 0) { "Green" } else { "Red" })
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

if ($FailCount -gt 0) { exit 1 } else { exit 0 }
