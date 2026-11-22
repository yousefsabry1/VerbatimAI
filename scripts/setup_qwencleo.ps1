<#
.SYNOPSIS
    VerbatimAI - QwenCleo 4-bit NF4 Arbiter Managed Setup
    Tagline: Every Word Matters.

.DESCRIPTION
    Sets up the optional QwenCleo 4-bit audio-LLM arbiter for Maximum Accuracy Hybrid ASR V3.
    Creates an isolated experimental_venv, installs required dependencies,
    downloads model weights (~3.8 GB), and verifies GPU capability.

.PARAMETER Force
    Skips interactive confirmation prompts.

.PARAMETER SkipGpuCheck
    Proceeds even if NVIDIA GPU detection does not meet the recommended 4 GB VRAM threshold.
#>

[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$SkipGpuCheck
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$BackendDir = Join-Path $ProjectRoot "backend"
$ExpVenvDir = Join-Path $ProjectRoot "experimental_venv"
$ExpPyExe = Join-Path $ExpVenvDir "Scripts\python.exe"
$ModelsDir = Join-Path $BackendDir "storage\models\qwencleo-asr"
$ReqFile = Join-Path $ProjectRoot "requirements-experimental.txt"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "--> $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "    [OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "    [WARNING] $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "    [ERROR] $Message" -ForegroundColor Red
}

Write-Host ""
Write-Host "========================================================" -ForegroundColor Magenta
Write-Host "  Verbatim AI - QwenCleo 4-bit Arbiter Setup" -ForegroundColor Magenta
Write-Host "  Full Tri-Model Consensus for Maximum Accuracy" -ForegroundColor White
Write-Host "  Tagline: Every Word Matters." -ForegroundColor Gray
Write-Host "========================================================" -ForegroundColor Magenta
Write-Host ""

# 1. Hardware & System Verification
Write-Step "Checking GPU and Hardware Requirements..."

$hasNvidiaGpu = $false
$gpuName = ""
$vramMb = 0

$nvidiaSmi = Get-Command "nvidia-smi.exe" -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    try {
        $pinfo = New-Object System.Diagnostics.ProcessStartInfo
        $pinfo.FileName = "nvidia-smi.exe"
        $pinfo.Arguments = "--query-gpu=name,memory.total --format=csv,noheader,nounits"
        $pinfo.RedirectStandardOutput = $true
        $pinfo.UseShellExecute = $false
        $pinfo.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($pinfo)
        $proc.WaitForExit(3000) | Out-Null
        if ($proc.ExitCode -eq 0) {
            $raw = $proc.StandardOutput.ReadToEnd().Trim()
            $lines = $raw -split "`n"
            if ($lines.Count -gt 0) {
                $parts = $lines[0] -split ","
                $gpuName = $parts[0].Trim()
                $vramMb = [double]($parts[1].Trim())
                $hasNvidiaGpu = $true
            }
        }
    } catch {}
}

if ($hasNvidiaGpu) {
    Write-Success "Detected GPU: $gpuName ($vramMb MB VRAM)"
    if ($vramMb -lt 3500 -and -not $SkipGpuCheck) {
        Write-Warn "QwenCleo 4-bit requires ~4096 MB VRAM. Available: $vramMb MB."
        Write-Warn "Performance may be degraded or experience CUDA out-of-memory errors on long audio."
    }
} else {
    Write-Warn "No NVIDIA GPU detected."
    Write-Warn "QwenCleo-ASR uses 4-bit NF4 bitsandbytes quantization which requires an NVIDIA CUDA GPU."
    Write-Warn "It cannot execute on CPU."
    if (-not $SkipGpuCheck -and -not $Force) {
        $ans = Read-Host "Proceed anyway? (Y/N)"
        if ($ans -ne "Y" -and $ans -ne "y") {
            Write-Host "Setup aborted by user." -ForegroundColor Yellow
            exit 0
        }
    }
}

# Check disk space
$driveLetter = (Split-Path -Qualifier $ProjectRoot).TrimEnd(':')
$drive = Get-PSDrive -Name $driveLetter -ErrorAction SilentlyContinue
if ($drive) {
    $freeGb = [math]::Round($drive.Free / 1GB, 1)
    Write-Success "Available disk space on drive $driveLetter`: $freeGb GB"
    if ($freeGb -lt 7.0) {
        Write-Warn "Free disk space ($freeGb GB) is close to the ~6.5 GB requirement."
    }
}

# 2. Resource Disclosure and Confirmation
Write-Step "Resource Requirements & Information:"
Write-Host "   - Model Weights: ~3.8 GB (mohammedaly22/QwenCleo-ASR)" -ForegroundColor White
Write-Host "   - Isolated Python Environment: ~2.7 GB (torch, transformers, bitsandbytes)" -ForegroundColor White
Write-Host "   - Total Disk Space: ~6.5 GB" -ForegroundColor White
Write-Host "   - Target Location: $ExpVenvDir" -ForegroundColor White
Write-Host "   - Purpose: Upgrades Maximum Accuracy from Dual-Model to Full Tri-Model Consensus" -ForegroundColor White
Write-Host ""

if (-not $Force) {
    $confirm = Read-Host "Do you want to download and configure QwenCleo 4-bit now? (Y/N)"
    if ($confirm -ne "Y" -and $confirm -ne "y") {
        Write-Host "Setup canceled by user. Verbatim AI continues running with Dual-Model Consensus." -ForegroundColor Yellow
        exit 0
    }
}

# 3. Locate Base Python Interpreter
Write-Step "Locating Base Python Interpreter..."
$basePy = Join-Path $BackendDir ".venv\Scripts\python.exe"
if (-not (Test-Path $basePy)) {
    $sysPy = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($sysPy -and $sysPy.Source -notlike "*WindowsApps*") {
        $basePy = $sysPy.Source
    } else {
        Write-Err "Python interpreter not found. Please run 00_INSTALL.bat first to configure Verbatim AI."
        exit 1
    }
}
Write-Success "Using Python interpreter: $basePy"

# 4. Create Isolated Experimental Virtual Environment
Write-Step "Configuring Isolated Python Environment (experimental_venv)..."
if (-not (Test-Path $ExpPyExe)) {
    Write-Host "   Creating virtual environment at $ExpVenvDir..." -ForegroundColor Gray
    & $basePy -m venv $ExpVenvDir
    if (-not (Test-Path $ExpPyExe)) {
        Write-Err "Failed to create virtual environment at $ExpVenvDir"
        exit 1
    }
    Write-Success "Isolated virtual environment created."
} else {
    Write-Success "Existing experimental_venv found."
}

# 5. Install Experimental Requirements
Write-Step "Installing Dependencies into experimental_venv..."
Write-Host "   Upgrading pip..." -ForegroundColor Gray
& $ExpPyExe -m pip install --upgrade pip --quiet

Write-Host "   Installing torch, transformers, bitsandbytes, and qwen-asr from $ReqFile..." -ForegroundColor Gray
if (Test-Path $ReqFile) {
    & $ExpPyExe -m pip install -r $ReqFile --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to install experimental dependencies. Check your internet connection."
        exit 1
    }
    Write-Success "Experimental dependencies installed successfully."
} else {
    Write-Err "Requirements file not found at $ReqFile"
    exit 1
}

# 6. Download Model Weights
Write-Step "Downloading QwenCleo-ASR 4-bit Model Weights (~3.8 GB)..."
New-Item -ItemType Directory -Path $ModelsDir -Force | Out-Null

$downloadScript = @"
import sys
from pathlib import Path
from huggingface_hub import snapshot_download

target_dir = Path(r'$ModelsDir')
target_dir.mkdir(parents=True, exist_ok=True)

print('Starting snapshot download from mohammedaly22/QwenCleo-ASR...')
snapshot_download(
    repo_id='mohammedaly22/QwenCleo-ASR',
    local_dir=str(target_dir),
    local_dir_use_symlinks=False,
    resume_download=True,
)
print('SNAPSHOT_COMPLETE')
"@

$dlScriptPath = Join-Path $BackendDir "storage\temp_qwen_dl.py"
Set-Content -Path $dlScriptPath -Value $downloadScript -Encoding UTF8

try {
    & $ExpPyExe $dlScriptPath
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Model download did not complete successfully."
        exit 1
    }
} finally {
    Remove-Item $dlScriptPath -Force -ErrorAction SilentlyContinue
}

# 7. Verification Gate
Write-Step "Verifying QwenCleo Setup and Runtime Import..."
$verifyScript = @"
import sys
import torch
from transformers import BitsAndBytesConfig
import qwen_asr
print('VERIFY_QWEN_OK')
"@

$vScriptPath = Join-Path $BackendDir "storage\temp_qwen_verify.py"
Set-Content -Path $vScriptPath -Value $verifyScript -Encoding UTF8

$vOut = ""
try {
    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
    $pinfo.FileName = $ExpPyExe
    $pinfo.Arguments = "`"$vScriptPath`""
    $pinfo.RedirectStandardOutput = $true
    $pinfo.RedirectStandardError = $true
    $pinfo.UseShellExecute = $false
    $pinfo.CreateNoWindow = $true
    $proc = [System.Diagnostics.Process]::Start($pinfo)
    $proc.WaitForExit(15000) | Out-Null
    $vOut = $proc.StandardOutput.ReadToEnd().Trim()
} finally {
    Remove-Item $vScriptPath -Force -ErrorAction SilentlyContinue
}

$modelSafetensors = Join-Path $ModelsDir "model.safetensors"
$configJson = Join-Path $ModelsDir "config.json"

if ($vOut -match "VERIFY_QWEN_OK" -and (Test-Path $modelSafetensors) -and (Test-Path $configJson)) {
    Write-Success "QwenCleo runtime verified: isolated environment and model weights are ready."
} else {
    Write-Err "Verification failed. Model files or import validation was unsuccessful."
    exit 1
}

# 8. Completion Banner
Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host "  QwenCleo 4-bit Setup Complete!" -ForegroundColor Green
Write-Host "  Full Tri-Model Consensus is now active in Verbatim AI." -ForegroundColor White
Write-Host "========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Verbatim AI will now automatically invoke QwenCleo 4-bit" -ForegroundColor Cyan
Write-Host "  to adjudicate complex code-switching conflicts in Maximum Accuracy mode." -ForegroundColor Cyan
Write-Host ""

exit 0
