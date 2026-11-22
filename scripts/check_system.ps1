<#
.SYNOPSIS
    VerbatimAI - System Diagnostics and Hardware Readiness Inspector
#>

[CmdletBinding()]
param()

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$BackendDir = Join-Path $ProjectRoot "backend"
$FrontendDir = Join-Path $ProjectRoot "frontend"
$ToolsDir = Join-Path $ProjectRoot "tools"
$ModelsDir = Join-Path $BackendDir "storage\models"

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Verbatim AI - Hardware & Dependency Diagnostics" -ForegroundColor Cyan
Write-Host "  Tagline: Every Word Matters." -ForegroundColor White
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Operating System & Hardware
Write-Host "1. Operating System & Resources:" -ForegroundColor Yellow
$os = Get-CimInstance Win32_OperatingSystem
$osName = $os.Caption
$arch = if ([System.Environment]::Is64BitOperatingSystem) { "64-bit" } else { "32-bit" }
$ramGb = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
$freeRamGb = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
Write-Host "   OS: $osName ($arch)" -ForegroundColor White
Write-Host "   Total RAM: $ramGb GB (Free: $freeRamGb GB)" -ForegroundColor White

$driveLetter = (Split-Path -Qualifier $ProjectRoot).TrimEnd(':')
$drive = Get-PSDrive -Name $driveLetter -ErrorAction SilentlyContinue
if ($drive) {
    $freeDiskGb = [math]::Round($drive.Free / 1GB, 1)
    Write-Host "   Project Drive ($driveLetter`:): $freeDiskGb GB free" -ForegroundColor White
}
Write-Host ""

# 2. Python Environment
Write-Host "2. Python Environment:" -ForegroundColor Yellow
$venvPy = Join-Path $BackendDir ".venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    try {
        $pinfo = New-Object System.Diagnostics.ProcessStartInfo
        $pinfo.FileName = $venvPy
        $pinfo.Arguments = "-c `"import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')`""
        $pinfo.RedirectStandardOutput = $true
        $pinfo.UseShellExecute = $false
        $pinfo.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($pinfo)
        $proc.WaitForExit(3000) | Out-Null
        $ver = $proc.StandardOutput.ReadToEnd().Trim()
        Write-Host "   [OK] Backend virtualenv Python: $ver ($venvPy)" -ForegroundColor Green
    } catch {
        Write-Host "   [WARN] Backend virtualenv Python exists but could not be executed." -ForegroundColor Yellow
    }
} else {
    Write-Host "   [INFO] Backend virtualenv not found at backend\.venv." -ForegroundColor Yellow
    Write-Host "          Run 00_INSTALL.bat to configure the environment automatically." -ForegroundColor Gray
}

# Check system Python
$sysPy = Get-Command "python.exe" -ErrorAction SilentlyContinue
if ($sysPy) {
    if ($sysPy.Source -like "*WindowsApps*") {
        Write-Host "   [INFO] Microsoft Store Python alias detected on PATH (inactive)." -ForegroundColor Gray
    } else {
        Write-Host "   [OK] System Python available at: $($sysPy.Source)" -ForegroundColor Green
    }
}
Write-Host ""

# 3. Audio Binaries (FFmpeg & FFprobe)
Write-Host "3. Audio Processing Tools (FFmpeg & FFprobe):" -ForegroundColor Yellow
$localFfmpeg = Join-Path $ToolsDir "ffmpeg\bin\ffmpeg.exe"
$localFfprobe = Join-Path $ToolsDir "ffmpeg\bin\ffprobe.exe"

$ffmpegOk = $false
$ffprobeOk = $false

if ((Test-Path $localFfmpeg) -and (Test-Path $localFfprobe)) {
    Write-Host "   [OK] Application-managed FFmpeg found: $localFfmpeg" -ForegroundColor Green
    Write-Host "   [OK] Application-managed FFprobe found: $localFfprobe" -ForegroundColor Green
    $ffmpegOk = $true
    $ffprobeOk = $true
} else {
    $pathFfmpeg = Get-Command "ffmpeg.exe" -ErrorAction SilentlyContinue
    $pathFfprobe = Get-Command "ffprobe.exe" -ErrorAction SilentlyContinue
    if ($pathFfmpeg) {
        Write-Host "   [OK] System FFmpeg found on PATH: $($pathFfmpeg.Source)" -ForegroundColor Green
        $ffmpegOk = $true
    }
    if ($pathFfprobe) {
        Write-Host "   [OK] System FFprobe found on PATH: $($pathFfprobe.Source)" -ForegroundColor Green
        $ffprobeOk = $true
    }
}

if (-not $ffmpegOk -or -not $ffprobeOk) {
    Write-Host "   [WARN] FFmpeg or FFprobe missing. Run 00_INSTALL.bat to install automatically." -ForegroundColor Yellow
}
Write-Host ""

# 4. Node.js & npm (Frontend Tooling)
Write-Host "4. Node.js & Frontend Environment:" -ForegroundColor Yellow
$localNode = Join-Path $ToolsDir "node\node.exe"
if (Test-Path $localNode) {
    Write-Host "   [OK] Application-managed Node.js found: $localNode" -ForegroundColor Green
} else {
    $sysNode = Get-Command "node.exe" -ErrorAction SilentlyContinue
    if ($sysNode) {
        Write-Host "   [OK] System Node.js found on PATH: $($sysNode.Source)" -ForegroundColor Green
    } else {
        Write-Host "   [INFO] Node.js not detected on PATH." -ForegroundColor Gray
    }
}

$distIndex = Join-Path $FrontendDir "dist\index.html"
if (Test-Path $distIndex) {
    $distSize = (Get-Item $distIndex).Length
    Write-Host "   [OK] Production frontend bundle is built at frontend\dist (index.html: $distSize bytes)" -ForegroundColor Green
} else {
    Write-Host "   [WARN] frontend\dist\index.html not found. Run 00_INSTALL.bat to build frontend." -ForegroundColor Yellow
}
Write-Host ""

# 5. NVIDIA GPU & CUDA Drivers
Write-Host "5. GPU Acceleration & CUDA Drivers:" -ForegroundColor Yellow
$nvidiaSmi = Get-Command "nvidia-smi.exe" -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    try {
        $pinfo = New-Object System.Diagnostics.ProcessStartInfo
        $pinfo.FileName = "nvidia-smi.exe"
        $pinfo.Arguments = "--query-gpu=name,memory.total,memory.free,driver_version --format=csv,noheader"
        $pinfo.RedirectStandardOutput = $true
        $pinfo.UseShellExecute = $false
        $pinfo.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($pinfo)
        $proc.WaitForExit(3000) | Out-Null
        if ($proc.ExitCode -eq 0) {
            $info = $proc.StandardOutput.ReadToEnd().Trim()
            $hasNvidiaGpu = $true
            $parts = $info.Split(',')
            if ($parts.Count -ge 2) {
                $gpuName = $parts[0].Trim()
                $vramRaw = $parts[1].Trim()
                $vramMb = [double]($vramRaw -replace '[^\d.]', '')
            }
            Write-Host "   [OK] NVIDIA GPU detected: $info" -ForegroundColor Green
            Write-Host "        Hardware acceleration (CUDA float16/int8) is available." -ForegroundColor Green
        }
    } catch {
        Write-Host "   [WARN] Error executing nvidia-smi." -ForegroundColor Yellow
    }
} else {
    Write-Host "   [INFO] No NVIDIA GPU detected. VerbatimAI will run smoothly in CPU Safe Mode." -ForegroundColor White
}
Write-Host ""

# 6. Model Cache
Write-Host "6. Downloaded AI Models (backend\storage\models):" -ForegroundColor Yellow
if (Test-Path $ModelsDir) {
    $models = Get-ChildItem -Path $ModelsDir -Directory
    if ($models.Count -gt 0) {
        foreach ($m in $models) {
            $size = (Get-ChildItem -Path $m.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
            $sizeMb = if ($size) { [math]::Round($size / 1MB, 1) } else { 0 }
            Write-Host "   - $($m.Name) ($sizeMb MB)" -ForegroundColor White
        }
    } else {
        Write-Host "   [INFO] No models downloaded yet. Download models on first use in the UI." -ForegroundColor Gray
    }
} else {
    Write-Host "   [INFO] Storage models folder not created yet." -ForegroundColor Gray
}
Write-Host ""

# 7. Maximum Accuracy (Hybrid ASR V3) Operational Tier Status:
Write-Host "7. Maximum Accuracy (Hybrid ASR V3) Operational Tier Status:" -ForegroundColor Yellow
$csDownloaded = (Test-Path (Join-Path $ModelsDir "codeswitched-medium\model.bin")) -or (Test-Path (Join-Path $ModelsDir "codeswitched-medium\.ready"))
$tbDownloaded = (Test-Path (Join-Path $ModelsDir "large-v3-turbo\model.bin")) -or (Test-Path (Join-Path $ModelsDir "large-v3-turbo\.ready"))
$twinReady = $csDownloaded -and $tbDownloaded

$expPy = Join-Path $ProjectRoot "experimental_venv\Scripts\python.exe"
$expReady = Test-Path $expPy
$qwenWeights = (Test-Path (Join-Path $ModelsDir "qwencleo-asr\model.safetensors")) -and (Test-Path (Join-Path $ModelsDir "qwencleo-asr\config.json"))
$qwenGpuReady = $hasNvidiaGpu -and ($vramMb -ge 3500)
$triModelReady = $twinReady -and $expReady -and $qwenWeights -and $qwenGpuReady

if ($triModelReady) {
    Write-Host "   [OK] Operational Tier: FULL TRI-MODEL CONSENSUS READY" -ForegroundColor Green
    Write-Host "        - Twin Whisper Models: Ready" -ForegroundColor Green
    Write-Host "        - QwenCleo 4-bit Arbiter: Ready on GPU ($gpuName)" -ForegroundColor Green
    Write-Host "        - Hybrid V3 will adjudicate conflicts with full 3-model arbitration." -ForegroundColor Green
} elseif ($twinReady) {
    Write-Host "   [OK] Operational Tier: DUAL-MODEL CONSENSUS READY (Baseline)" -ForegroundColor Cyan
    Write-Host "        - Twin Whisper Models: Ready (Codeswitched Medium + Whisper Large-v3-Turbo)" -ForegroundColor Green
    if (-not $qwenGpuReady) {
        Write-Host "        - QwenCleo Arbiter: GPU unsupported (Requires NVIDIA GPU with >= 4GB VRAM)" -ForegroundColor Yellow
    } elseif (-not $expReady -or -not $qwenWeights) {
        Write-Host "        - QwenCleo Arbiter: Not configured (Optional: run scripts\setup_qwencleo.bat to enable)" -ForegroundColor Yellow
    }
    Write-Host "        - Hybrid V3 will run with calibrated dual-model fusion and repetition suppression." -ForegroundColor White
} else {
    Write-Host "   [INFO] Operational Tier: REQUIRES MODEL DOWNLOAD" -ForegroundColor Yellow
    Write-Host "          Codeswitched Medium: $(if ($csDownloaded) { 'Ready' } else { 'Needs Download' })" -ForegroundColor Gray
    Write-Host "          Whisper Large Turbo: $(if ($tbDownloaded) { 'Ready' } else { 'Needs Download' })" -ForegroundColor Gray
    Write-Host "          Download models on first use in the UI." -ForegroundColor Gray
}
Write-Host ""

# 8. Summary
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  System Diagnostics Complete!" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""
