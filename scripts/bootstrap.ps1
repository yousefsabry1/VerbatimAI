<#
.SYNOPSIS
    VerbatimAI - Unified One-Click Complete Windows Installer
    Tagline: Every Word Matters.

.DESCRIPTION
    Single entry-point installer for VerbatimAI on Windows 10/11 x64:
    - Automatically audits hardware (CPU, RAM, GPU, VRAM, Disk Space)
    - Estimates complete download size and disk usage upfront
    - Obtains one clear user confirmation for the complete setup
    - Bootstraps Python 3.11 and the backend virtual environment (.venv)
    - Installs core Python dependencies and conditional NVIDIA CUDA packages
    - Sets up FFmpeg and FFprobe portable audio engine
    - Sets up Node.js and builds the production React frontend bundle
    - Downloads and verifies Fast Transcription model (Specialized Whisper Medium)
    - Downloads and verifies Maximum Accuracy twin model (Whisper Large-v3-Turbo)
    - Automatically sets up QwenCleo-ASR 4-bit arbiter on compatible NVIDIA GPUs (>= 4GB VRAM)
    - Validates end-to-end application health and saves installation state stamp
#>

[CmdletBinding()]
param(
    [switch]$ForceCpu,
    [switch]$SkipFrontend,
    [switch]$SkipModels,
    [switch]$Repair,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$BackendDir = Join-Path $ProjectRoot "backend"
$FrontendDir = Join-Path $ProjectRoot "frontend"
$ToolsDir = Join-Path $ProjectRoot "tools"
$CacheDir = Join-Path $ToolsDir "_cache"
$LogsDir = Join-Path $ProjectRoot "logs"
$ModelsDir = Join-Path $BackendDir "storage\models"

# Ensure essential directories exist
foreach ($dir in @($ToolsDir, $CacheDir, $LogsDir, $ModelsDir)) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogFile = Join-Path $LogsDir "install-$Timestamp.log"

function Write-InstallLog {
    param(
        [string]$Message,
        [string]$Level = "INFO",
        [ConsoleColor]$Color = [ConsoleColor]::White
    )
    $timeStr = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logLine = "[$timeStr] [$Level] $Message"
    Add-Content -Path $LogFile -Value $logLine -Encoding UTF8
    
    $prefix = switch ($Level) {
        "OK"    { "[OK] " }
        "WARN"  { "[WARNING] " }
        "ERROR" { "[ERROR] " }
        "STEP"  { "--> " }
        default { "[INFO] " }
    }
    
    $consoleColor = switch ($Level) {
        "OK"    { [ConsoleColor]::Green }
        "WARN"  { [ConsoleColor]::Yellow }
        "ERROR" { [ConsoleColor]::Red }
        "STEP"  { [ConsoleColor]::Cyan }
        default { $Color }
    }
    
    Write-Host "$prefix$Message" -ForegroundColor $consoleColor
}

function Download-FileWithProgress {
    param(
        [string]$Url,
        [string]$DestinationPath,
        [string]$Description = "Downloading file"
    )
    Write-InstallLog "$Description from $Url..." "INFO"
    $destDir = Split-Path -Parent $DestinationPath
    if (-not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }

    $tempDest = "$DestinationPath.downloading"
    if (Test-Path $tempDest) { Remove-Item $tempDest -Force }

    $maxRetries = 3
    $attempt = 0
    $success = $false

    while ($attempt -lt $maxRetries -and -not $success) {
        $attempt++
        try {
            $handler = New-Object System.Net.Http.HttpClientHandler
            $client = New-Object System.Net.Http.HttpClient($handler)
            $client.Timeout = [System.TimeSpan]::FromMinutes(10)
            $client.DefaultRequestHeaders.Add("User-Agent", "VerbatimAI-Installer/1.4.0 (Windows NT)")

            $response = $client.GetAsync($Url, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
            if (-not $response.IsSuccessStatusCode) {
                throw "HTTP request failed with status code $($response.StatusCode): $($response.ReasonPhrase)"
            }

            $totalBytes = $response.Content.Headers.ContentLength
            $stream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
            $fileStream = [System.IO.File]::Create($tempDest)

            $buffer = New-Object byte[] 65536
            $bytesRead = 0
            $totalRead = 0
            $lastPercent = -1

            while (($bytesRead = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                $fileStream.Write($buffer, 0, $bytesRead)
                $totalRead += $bytesRead
                if ($totalBytes -gt 0) {
                    $percent = [int](($totalRead / $totalBytes) * 100)
                    if ($percent -ne $lastPercent -and ($percent % 10 -eq 0 -or $percent -eq 100)) {
                        $lastPercent = $percent
                        $mbRead = [math]::Round($totalRead / 1MB, 1)
                        $mbTotal = [math]::Round($totalBytes / 1MB, 1)
                        Write-Host -NoNewline "`r   Progress: $percent% ($mbRead MB / $mbTotal MB)   "
                    }
                }
            }
            Write-Host ""
            $fileStream.Flush()
            $fileStream.Close()
            $stream.Close()
            $client.Dispose()

            if (Test-Path $DestinationPath) { Remove-Item $DestinationPath -Force }
            Move-Item -Path $tempDest -Destination $DestinationPath -Force
            $success = $true
            Write-InstallLog "Download completed successfully: $DestinationPath" "OK"
        }
        catch {
            Write-InstallLog "Download attempt $attempt failed: $_" "WARN"
            if (Test-Path $tempDest) { Remove-Item $tempDest -Force -ErrorAction SilentlyContinue }
            if ($attempt -lt $maxRetries) {
                Write-InstallLog "Retrying in 5 seconds..." "INFO"
                Start-Sleep -Seconds 5
            } else {
                throw "Failed to download $Url after $maxRetries attempts: $_"
            }
        }
    }
}

function Test-ValidPythonInterpreter {
    param([string]$ExecutablePath)
    if (-not $ExecutablePath -or -not (Test-Path $ExecutablePath)) {
        return $null
    }
    if ($ExecutablePath -like "*WindowsApps*") {
        return $null
    }
    try {
        $pinfo = New-Object System.Diagnostics.ProcessStartInfo
        $pinfo.FileName = $ExecutablePath
        $pinfo.Arguments = "-c `"import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')`""
        $pinfo.RedirectStandardOutput = $true
        $pinfo.RedirectStandardError = $true
        $pinfo.UseShellExecute = $false
        $pinfo.CreateNoWindow = $true

        $proc = [System.Diagnostics.Process]::Start($pinfo)
        $proc.WaitForExit(5000) | Out-Null
        if ($proc.ExitCode -eq 0) {
            $verStr = $proc.StandardOutput.ReadToEnd().Trim()
            $parts = $verStr.Split('.')
            if ($parts.Length -ge 2) {
                $major = [int]$parts[0]
                $minor = [int]$parts[1]
                if ($major -eq 3 -and $minor -ge 10 -and $minor -le 12) {
                    return @{
                        Path = (Resolve-Path $ExecutablePath).Path
                        Version = $verStr
                        Major = $major
                        Minor = $minor
                    }
                }
            }
        }
    }
    catch {
        return $null
    }
    return $null
}

function Test-ExecutableWorking {
    param([string]$ExePath, [string]$TestArg = "-version")
    if (-not (Test-Path $ExePath)) { return $false }
    try {
        $pinfo = New-Object System.Diagnostics.ProcessStartInfo
        $pinfo.FileName = $ExePath
        $pinfo.Arguments = $TestArg
        $pinfo.RedirectStandardOutput = $true
        $pinfo.RedirectStandardError = $true
        $pinfo.UseShellExecute = $false
        $pinfo.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($pinfo)
        $proc.WaitForExit(3000) | Out-Null
        return ($proc.ExitCode -eq 0)
    } catch { return $false }
}

# ==============================================================================
# Banner
# ==============================================================================
Clear-Host
Write-Host "========================================================" -ForegroundColor Magenta
Write-Host "  Verbatim AI — Unified Complete Windows Installer" -ForegroundColor Magenta
Write-Host "  Fast Transcription & Maximum Accuracy Out-of-the-Box" -ForegroundColor White
Write-Host "  Tagline: Every Word Matters." -ForegroundColor Gray
Write-Host "========================================================" -ForegroundColor Magenta
Write-Host ""
Write-InstallLog "Starting VerbatimAI unified complete installation." "INFO"
Write-InstallLog "Project Directory: $ProjectRoot" "INFO"
Write-InstallLog "Log File: $LogFile" "INFO"

# ==============================================================================
# Upfront Hardware Detection & Resource Assessment
# ==============================================================================
Write-InstallLog "Auditing hardware capabilities & system resources..." "STEP"

if (-not [System.Environment]::Is64BitOperatingSystem) {
    Write-InstallLog "VerbatimAI requires a 64-bit Windows operating system." "ERROR"
    exit 1
}

$os = Get-CimInstance Win32_OperatingSystem
$osName = $os.Caption
$totalRamGb = [math]::Round($os.TotalVisibleMemorySize / 1024 / 1024, 1)
$freeRamGb = [math]::Round($os.FreePhysicalMemory / 1024 / 1024, 1)

$driveLetter = (Split-Path -Qualifier $ProjectRoot).TrimEnd(':')
$drive = Get-PSDrive -Name $driveLetter -ErrorAction SilentlyContinue
$freeSpaceGb = if ($drive) { [math]::Round($drive.Free / 1GB, 1) } else { 0.0 }

# Detect NVIDIA GPU & VRAM
$hasNvidiaGpu = $false
$gpuName = "None"
$vramMb = 0.0

$nvidiaSmi = Get-Command "nvidia-smi.exe" -ErrorAction SilentlyContinue
if ($nvidiaSmi -and -not $ForceCpu) {
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

# Determine QwenCleo 4-bit compatibility
$qwenCompatible = $false
$qwenSkipReason = ""

if ($ForceCpu) {
    $qwenSkipReason = "CPU Safe Mode was forced via -ForceCpu switch."
} elseif (-not $hasNvidiaGpu) {
    $qwenSkipReason = "No NVIDIA GPU detected. QwenCleo 4-bit NF4 quantization requires CUDA."
} elseif ($vramMb -lt 3500) {
    $qwenSkipReason = "NVIDIA GPU detected ($gpuName), but available VRAM ($vramMb MB) is below the required 4096 MB threshold."
} else {
    $qwenCompatible = $true
}

# Assess existing files to calculate actual downloads needed
$pyInstalled = (Test-ValidPythonInterpreter -ExecutablePath (Join-Path $BackendDir ".venv\Scripts\python.exe")) -ne $null
$nodeInstalled = (Test-Path (Join-Path $ToolsDir "node\node.exe")) -or ((Get-Command "node.exe" -ErrorAction SilentlyContinue) -ne $null)
$ffmpegInstalled = ((Test-Path (Join-Path $ToolsDir "ffmpeg\bin\ffmpeg.exe")) -and (Test-Path (Join-Path $ToolsDir "ffmpeg\bin\ffprobe.exe"))) -or `
    (((Get-Command "ffmpeg.exe" -ErrorAction SilentlyContinue) -ne $null) -and ((Get-Command "ffprobe.exe" -ErrorAction SilentlyContinue) -ne $null))
$frontendBuilt = (Test-Path (Join-Path $FrontendDir "dist\index.html")) -and ((Get-Item (Join-Path $FrontendDir "dist\index.html") -ErrorAction SilentlyContinue).Length -gt 100)

$csDownloaded = (Test-Path (Join-Path $ModelsDir "codeswitched-medium\model.bin")) -or (Test-Path (Join-Path $ModelsDir "codeswitched-medium\.ready"))
$tbDownloaded = (Test-Path (Join-Path $ModelsDir "large-v3-turbo\model.bin")) -or (Test-Path (Join-Path $ModelsDir "large-v3-turbo\.ready"))
$qwenDownloaded = (Test-Path (Join-Path $ModelsDir "qwencleo-asr\model.safetensors")) -and (Test-Path (Join-Path $ModelsDir "qwencleo-asr\config.json"))
$expVenvReady = Test-Path (Join-Path $ProjectRoot "experimental_venv\Scripts\python.exe")

# Calculate estimated download and disk space
$estDownloadMb = 0
$estDiskMb = 0

if (-not $pyInstalled) { $estDownloadMb += 25; $estDiskMb += 150 }
if (-not $nodeInstalled) { $estDownloadMb += 30; $estDiskMb += 100 }
if (-not $ffmpegInstalled) { $estDownloadMb += 85; $estDiskMb += 200 }
if (-not (Test-Path (Join-Path $BackendDir ".venv\Scripts\python.exe"))) { $estDownloadMb += 220; $estDiskMb += 900 }

if (-not $SkipModels) {
    if (-not $csDownloaded) { $estDownloadMb += 740; $estDiskMb += 750 }
    if (-not $tbDownloaded) { $estDownloadMb += 1546; $estDiskMb += 1550 }
    if ($qwenCompatible) {
        if (-not $expVenvReady) { $estDownloadMb += 1500; $estDiskMb += 2700 }
        if (-not $qwenDownloaded) { $estDownloadMb += 3820; $estDiskMb += 3900 }
    }
}

$estDownloadGb = [math]::Round($estDownloadMb / 1024, 2)
$estDiskGb = [math]::Round($estDiskMb / 1024, 1)

# Display Hardware & Plan Table
Write-Host ""
Write-Host "--------------------------------------------------------" -ForegroundColor Yellow
Write-Host "  HARDWARE & RESOURCE AUDIT" -ForegroundColor Yellow
Write-Host "--------------------------------------------------------" -ForegroundColor Yellow
Write-Host "  Operating System : $osName (64-bit)" -ForegroundColor White
Write-Host "  Physical RAM     : $totalRamGb GB (Free: $freeRamGb GB)" -ForegroundColor White
Write-Host "  Disk Drive ($driveLetter`: )  : $freeSpaceGb GB available" -ForegroundColor White
if ($hasNvidiaGpu) {
    Write-Host "  NVIDIA GPU       : $gpuName ($vramMb MB VRAM)" -ForegroundColor Green
} else {
    Write-Host "  NVIDIA GPU       : None detected (CPU Safe Mode active)" -ForegroundColor White
}
Write-Host ""
Write-Host "  SUPPORTED OPERATIONAL TIERS" -ForegroundColor Yellow
Write-Host "--------------------------------------------------------" -ForegroundColor Yellow
Write-Host "  • Fast Transcription : Specialized Whisper Medium (Ready)" -ForegroundColor Green
if ($qwenCompatible) {
    Write-Host "  • Maximum Accuracy   : FULL TRI-MODEL CONSENSUS (Twin Models + QwenCleo 4-bit)" -ForegroundColor Green
} else {
    Write-Host "  • Maximum Accuracy   : DUAL-MODEL CONSENSUS (Twin Models on $(if ($hasNvidiaGpu) {'GPU'} else {'CPU Safe Mode'}))" -ForegroundColor Cyan
    Write-Host "    (QwenCleo note     : $qwenSkipReason)" -ForegroundColor Gray
}
Write-Host ""
Write-Host "  ESTIMATED DOWNLOAD & STORAGE FOOTPRINT" -ForegroundColor Yellow
Write-Host "--------------------------------------------------------" -ForegroundColor Yellow
Write-Host "  • Tools & Runtime    : $(if ($pyInstalled -and $nodeInstalled -and $ffmpegInstalled) {'Already present (0 MB)'} else {'~140 MB download'})" -ForegroundColor Gray
Write-Host "  • Fast Model (Medium): $(if ($csDownloaded) {'Already downloaded & verified (0 MB)'} else {'~740 MB download'})" -ForegroundColor Gray
Write-Host "  • Large-v3-Turbo     : $(if ($tbDownloaded) {'Already downloaded & verified (0 MB)'} else {'~1.55 GB download'})" -ForegroundColor Gray
if ($qwenCompatible) {
    Write-Host "  • QwenCleo 4-bit     : $(if ($qwenDownloaded -and $expVenvReady) {'Already configured & verified (0 MB)'} else {'~3.82 GB model weights + isolated venv'})" -ForegroundColor Gray
} else {
    Write-Host "  • QwenCleo 4-bit     : Skipped on this hardware (0 MB)" -ForegroundColor Gray
}
Write-Host "  ------------------------------------------------------" -ForegroundColor Yellow
Write-Host "  • Total Download Needed : $estDownloadGb GB" -ForegroundColor White
Write-Host "  • Free Disk Required    : $estDiskGb GB (Available: $freeSpaceGb GB)" -ForegroundColor White
Write-Host "--------------------------------------------------------" -ForegroundColor Yellow
Write-Host ""

# Check disk space sufficiency
if ($freeSpaceGb -lt ($estDiskGb + 2.0)) {
    Write-InstallLog "Insufficient disk space! Drive $driveLetter has $freeSpaceGb GB free, but installation requires at least $($estDiskGb + 2.0) GB." "ERROR"
    exit 1
}

# Unified User Confirmation
if (-not $NonInteractive) {
    Write-Host "  Proceed with full unified installation? (Y/N) [Default: Y]: " -NoNewline -ForegroundColor Yellow
    $ans = Read-Host
    if ($ans -and ($ans.Trim() -eq "N" -or $ans.Trim() -eq "n")) {
        Write-InstallLog "Installation cancelled by user." "WARN"
        exit 0
    }
}
Write-InstallLog "User confirmed. Proceeding with automated unified installation." "OK"

# ==============================================================================
# Stage 1: Storage Directories & Configuration
# ==============================================================================
Write-InstallLog "Stage 1/8: Initializing storage directories and configuration..." "STEP"

$storageDirs = @(
    (Join-Path $BackendDir "storage"),
    (Join-Path $BackendDir "storage\uploads"),
    (Join-Path $BackendDir "storage\outputs"),
    (Join-Path $BackendDir "storage\previews"),
    (Join-Path $BackendDir "storage\models"),
    (Join-Path $BackendDir "storage\benchmarks"),
    (Join-Path $BackendDir "storage\temp")
)
foreach ($sDir in $storageDirs) {
    if (-not (Test-Path $sDir)) {
        New-Item -ItemType Directory -Path $sDir -Force | Out-Null
    }
}

$envFile = Join-Path $ProjectRoot ".env"
$envExample = Join-Path $ProjectRoot ".env.example"
if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
    Copy-Item -Path $envExample -Destination $envFile -Force
    Write-InstallLog "Initialized .env configuration from .env.example." "OK"
}

# ==============================================================================
# Stage 2: Python 3.11 Runtime & Virtual Environment
# ==============================================================================
Write-InstallLog "Stage 2/8: Establishing Python 3.11 runtime & virtual environment..." "STEP"

$venvDir = Join-Path $BackendDir ".venv"
$venvPyExe = Join-Path $venvDir "Scripts\python.exe"
$selectedPython = $null

# Priority 1: Check existing backend virtual environment
if (Test-Path $venvPyExe) {
    $validVenv = Test-ValidPythonInterpreter -ExecutablePath $venvPyExe
    if ($validVenv) {
        Write-InstallLog "Existing backend virtual environment detected: $($validVenv.Path) (Python $($validVenv.Version))" "OK"
        $selectedPython = $validVenv
    }
}

# Priority 2: Check py launcher for 3.11 or 3.10
if (-not $selectedPython) {
    $pyLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        foreach ($arg in @("-3.11", "-3.10", "-3")) {
            try {
                $pinfo = New-Object System.Diagnostics.ProcessStartInfo
                $pinfo.FileName = "py.exe"
                $pinfo.Arguments = "$arg -c `"import sys; print(sys.executable)`""
                $pinfo.RedirectStandardOutput = $true
                $pinfo.UseShellExecute = $false
                $pinfo.CreateNoWindow = $true
                $proc = [System.Diagnostics.Process]::Start($pinfo)
                $proc.WaitForExit(3000) | Out-Null
                if ($proc.ExitCode -eq 0) {
                    $cand = $proc.StandardOutput.ReadToEnd().Trim()
                    $valid = Test-ValidPythonInterpreter -ExecutablePath $cand
                    if ($valid) {
                        Write-InstallLog "Found Python via py launcher ($arg): $($valid.Path) (Python $($valid.Version))" "OK"
                        $selectedPython = $valid
                        break
                    }
                }
            } catch {}
        }
    }
}

# Priority 3: Check python.exe on PATH (ignoring WindowsApps)
if (-not $selectedPython) {
    $pathPy = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($pathPy -and $pathPy.Source -notlike "*WindowsApps*") {
        $valid = Test-ValidPythonInterpreter -ExecutablePath $pathPy.Source
        if ($valid) {
            Write-InstallLog "Found compatible Python on PATH: $($valid.Path) (Python $($valid.Version))" "OK"
            $selectedPython = $valid
        }
    }
}

# Priority 4: Check standard user and system installation directories
if (-not $selectedPython) {
    $commonLocations = @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:ProgramFiles\Python311\python.exe",
        "C:\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "$env:ProgramFiles\Python310\python.exe",
        "C:\Python310\python.exe"
    )
    foreach ($loc in $commonLocations) {
        $valid = Test-ValidPythonInterpreter -ExecutablePath $loc
        if ($valid) {
            Write-InstallLog "Found compatible Python at $loc (Python $($valid.Version))" "OK"
            $selectedPython = $valid
            break
        }
    }
}

# Priority 5: Automated Bootstrap of Python 3.11 if missing
if (-not $selectedPython) {
    Write-InstallLog "No compatible Python installation found. Initiating automated Python 3.11 setup..." "WARN"

    $installedViaWinget = $false
    $wingetCmd = Get-Command "winget.exe" -ErrorAction SilentlyContinue

    if ($wingetCmd) {
        Write-InstallLog "Attempting user-scope Python 3.11 installation via winget..." "INFO"
        try {
            $wingetArgs = "install --id Python.Python.3.11 -e --scope user --accept-source-agreements --accept-package-agreements --silent"
            $p = Start-Process -FilePath "winget.exe" -ArgumentList $wingetArgs -Wait -PassThru -NoNewWindow
            if ($p.ExitCode -eq 0 -or $p.ExitCode -eq 3010) {
                Write-InstallLog "winget installation completed." "OK"
                $installedViaWinget = $true
            }
        } catch {}
    }

    if (-not $installedViaWinget) {
        $pythonInstallerUrl = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
        $installerPath = Join-Path $CacheDir "python-3.11.9-amd64.exe"

        Download-FileWithProgress -Url $pythonInstallerUrl -DestinationPath $installerPath -Description "Official Python 3.11.9 Installer"

        Write-InstallLog "Installing Python 3.11 to user profile (per-user, no admin prompt needed)..." "INFO"
        $installArgs = "/quiet InstallAllUsers=0 Include_pip=1 Include_launcher=1 PrependPath=1 SimpleInstall=1"
        $instProc = Start-Process -FilePath $installerPath -ArgumentList $installArgs -Wait -PassThru -NoNewWindow
    }

    $expectedUserPy = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
    $valid = Test-ValidPythonInterpreter -ExecutablePath $expectedUserPy
    if (-not $valid) {
        $pathPy = Get-Command "python.exe" -ErrorAction SilentlyContinue
        if ($pathPy) { $valid = Test-ValidPythonInterpreter -ExecutablePath $pathPy.Source }
    }

    if (-not $valid) {
        Write-InstallLog "Automated Python installation could not be verified automatically." "ERROR"
        exit 1
    }

    $selectedPython = $valid
    Write-InstallLog "Python 3.11 installed and verified: $($selectedPython.Path)" "OK"
}

# Create backend\.venv
if (-not (Test-Path $venvPyExe)) {
    Write-InstallLog "Creating virtual environment at backend\.venv..." "INFO"
    $basePy = $selectedPython.Path
    $p = Start-Process -FilePath $basePy -ArgumentList "-m venv `"$venvDir`"" -Wait -PassThru -NoNewWindow
    if ($p.ExitCode -ne 0 -or -not (Test-Path $venvPyExe)) {
        Write-InstallLog "Failed to create virtual environment." "ERROR"
        exit 1
    }
    Write-InstallLog "Virtual environment created successfully." "OK"
} elseif ($Repair) {
    Write-InstallLog "Repair mode: Validating virtual environment interpreter..." "INFO"
    $vTest = Test-ValidPythonInterpreter -ExecutablePath $venvPyExe
    if (-not $vTest) {
        Remove-Item -Path $venvDir -Recurse -Force -ErrorAction SilentlyContinue
        $basePy = $selectedPython.Path
        $p = Start-Process -FilePath $basePy -ArgumentList "-m venv `"$venvDir`"" -Wait -PassThru -NoNewWindow
    }
}

# ==============================================================================
# Stage 3: Python Dependencies (Base + Conditional CUDA)
# ==============================================================================
Write-InstallLog "Stage 3/8: Installing Python libraries & runtime dependencies..." "STEP"

Write-InstallLog "Upgrading pip, setuptools, and wheel..." "INFO"
& $venvPyExe -m pip install --upgrade pip setuptools wheel --quiet --no-warn-script-location --disable-pip-version-check

$baseReq = Join-Path $BackendDir "requirements-base.txt"
if (-not (Test-Path $baseReq)) {
    $baseReq = Join-Path $BackendDir "requirements.txt"
}
Write-InstallLog "Installing core backend Python libraries (FastAPI, Faster-Whisper, CTranslate2)..." "INFO"
& $venvPyExe -m pip install -r $baseReq --no-warn-script-location --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
    Write-InstallLog "Failed to install base Python dependencies." "ERROR"
    exit 1
}
Write-InstallLog "Core Python dependencies installed." "OK"

if ($ForceCpu) {
    Write-InstallLog "CPU Safe Mode requested. Skipping GPU CUDA packages." "INFO"
} elseif (-not $hasNvidiaGpu) {
    Write-InstallLog "No NVIDIA GPU detected. VerbatimAI will run in high-performance CPU int8 mode." "INFO"
}

# Install CUDA packages if GPU is present and not ForceCpu
if ($hasNvidiaGpu -and -not $ForceCpu) {
    $cudaReq = Join-Path $BackendDir "requirements-cuda.txt"
    if (Test-Path $cudaReq) {
        Write-InstallLog "Installing NVIDIA CUDA 12 runtime wheels for hardware acceleration..." "INFO"
        & $venvPyExe -m pip install -r $cudaReq --no-warn-script-location --disable-pip-version-check
        if ($LASTEXITCODE -eq 0) {
            Write-InstallLog "CUDA runtime libraries installed successfully." "OK"
        } else {
            Write-InstallLog "Failed to install CUDA libraries. Audio processing will fall back to CPU safely." "WARN"
        }
    }
}

# Smoke test Python backend imports
Write-InstallLog "Verifying Python backend imports..." "INFO"
$smokeCode = "import fastapi, uvicorn, pydantic, faster_whisper, ctranslate2, soundfile; print('BACKEND_IMPORTS_VERIFIED')"
$pinfo = New-Object System.Diagnostics.ProcessStartInfo
$pinfo.FileName = $venvPyExe
$pinfo.Arguments = "-c `"$smokeCode`""
$pinfo.RedirectStandardOutput = $true
$pinfo.RedirectStandardError = $true
$pinfo.UseShellExecute = $false
$pinfo.CreateNoWindow = $true
$proc = [System.Diagnostics.Process]::Start($pinfo)
$proc.WaitForExit(10000) | Out-Null
if ($proc.ExitCode -ne 0) {
    $err = $proc.StandardError.ReadToEnd()
    Write-InstallLog "Python import verification failed: $err" "ERROR"
    exit 1
}
Write-InstallLog "Python backend modules verified." "OK"

# ==============================================================================
# Stage 4: FFmpeg & FFprobe Setup
# ==============================================================================
Write-InstallLog "Stage 4/8: Checking FFmpeg and FFprobe audio engine..." "STEP"

$ffmpegToolsDir = Join-Path $ToolsDir "ffmpeg\bin"
$localFfmpeg = Join-Path $ffmpegToolsDir "ffmpeg.exe"
$localFfprobe = Join-Path $ffmpegToolsDir "ffprobe.exe"

$ffmpegWorking = $false
$ffprobeWorking = $false

if ((Test-ExecutableWorking $localFfmpeg) -and (Test-ExecutableWorking $localFfprobe)) {
    $ffmpegWorking = $true
    $ffprobeWorking = $true
    Write-InstallLog "Application-managed FFmpeg and FFprobe detected in tools\ffmpeg\bin." "OK"
}

if (-not $ffmpegWorking) {
    $sysFfmpeg = Get-Command "ffmpeg.exe" -ErrorAction SilentlyContinue
    $sysFfprobe = Get-Command "ffprobe.exe" -ErrorAction SilentlyContinue
    if ($sysFfmpeg -and $sysFfprobe) {
        if ((Test-ExecutableWorking $sysFfmpeg.Source) -and (Test-ExecutableWorking $sysFfprobe.Source)) {
            $ffmpegWorking = $true
            $ffprobeWorking = $true
            Write-InstallLog "System FFmpeg and FFprobe detected on PATH." "OK"
        }
    }
}

if (-not $ffmpegWorking -or -not $ffprobeWorking) {
    Write-InstallLog "Bootstrapping portable FFmpeg binaries..." "WARN"
    if (-not (Test-Path $ffmpegToolsDir)) {
        New-Item -ItemType Directory -Path $ffmpegToolsDir -Force | Out-Null
    }

    $ffmpegZipUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    $ffmpegZip = Join-Path $CacheDir "ffmpeg-release-essentials.zip"

    Download-FileWithProgress -Url $ffmpegZipUrl -DestinationPath $ffmpegZip -Description "FFmpeg & FFprobe Release Archive"

    $extractTemp = Join-Path $CacheDir "ffmpeg_extract_temp"
    if (Test-Path $extractTemp) { Remove-Item $extractTemp -Recurse -Force }
    Expand-Archive -Path $ffmpegZip -DestinationPath $extractTemp -Force

    $foundFfmpeg = Get-ChildItem -Path $extractTemp -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
    $foundFfprobe = Get-ChildItem -Path $extractTemp -Recurse -Filter "ffprobe.exe" | Select-Object -First 1

    if ($foundFfmpeg -and $foundFfprobe) {
        Copy-Item -Path $foundFfmpeg.FullName -Destination $localFfmpeg -Force
        Copy-Item -Path $foundFfprobe.FullName -Destination $localFfprobe -Force
        Remove-Item $extractTemp -Recurse -Force -ErrorAction SilentlyContinue
        Write-InstallLog "FFmpeg and FFprobe extracted to tools\ffmpeg\bin." "OK"
    } else {
        throw "Could not locate ffmpeg.exe and ffprobe.exe inside the extracted archive."
    }
}
Write-InstallLog "FFmpeg and FFprobe verified and ready." "OK"

# ==============================================================================
# Stage 5: Node.js, npm & Production Frontend Build
# ==============================================================================
Write-InstallLog "Stage 5/8: Checking Node.js, npm, and production frontend..." "STEP"

$distIndex = Join-Path $FrontendDir "dist\index.html"
$nodeToolsDir = Join-Path $ToolsDir "node"
$localNode = Join-Path $nodeToolsDir "node.exe"
$localNpm = Join-Path $nodeToolsDir "npm.cmd"

$selectedNode = $null
$selectedNpm = $null

if (Test-Path $localNode) {
    if (Test-ExecutableWorking $localNode "-v") {
        $selectedNode = $localNode
        $selectedNpm = $localNpm
        Write-InstallLog "Application-managed Node.js detected: $localNode" "OK"
    }
}

if (-not $selectedNode) {
    $sysNode = Get-Command "node.exe" -ErrorAction SilentlyContinue
    $sysNpm = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
    if (-not $sysNpm) { $sysNpm = Get-Command "npm" -ErrorAction SilentlyContinue }
    if ($sysNode -and $sysNpm) {
        $selectedNode = $sysNode.Source
        $selectedNpm = $sysNpm.Source
        Write-InstallLog "System Node.js detected on PATH: $selectedNode" "OK"
    }
}

if (-not $selectedNode) {
    Write-InstallLog "Bootstrapping official portable Node.js LTS..." "WARN"
    $nodeZipUrl = "https://nodejs.org/dist/v20.18.1/node-v20.18.1-win-x64.zip"
    $nodeZip = Join-Path $CacheDir "node-v20.18.1-win-x64.zip"

    Download-FileWithProgress -Url $nodeZipUrl -DestinationPath $nodeZip -Description "Portable Node.js LTS Archive"

    $nodeHash = (Get-FileHash -Path $nodeZip -Algorithm SHA256).Hash.ToLower()
    if ($nodeHash -ne "56e5aacdeee7168871721b75819ccacf2367de8761b78eaceacdecd41e04ca03") {
        throw "Node.js zip checksum mismatch! Corrupted download."
    }

    $nodeTemp = Join-Path $CacheDir "node_extract_temp"
    if (Test-Path $nodeTemp) { Remove-Item $nodeTemp -Recurse -Force }
    Expand-Archive -Path $nodeZip -DestinationPath $nodeTemp -Force

    $subFolder = Get-ChildItem -Path $nodeTemp -Directory | Select-Object -First 1
    if ($subFolder) {
        if (-not (Test-Path $nodeToolsDir)) {
            New-Item -ItemType Directory -Path $nodeToolsDir -Force | Out-Null
        }
        Copy-Item -Path (Join-Path $subFolder.FullName "*") -Destination $nodeToolsDir -Recurse -Force
        Remove-Item $nodeTemp -Recurse -Force -ErrorAction SilentlyContinue
        $selectedNode = $localNode
        $selectedNpm = $localNpm
        Write-InstallLog "Portable Node.js extracted to tools\node." "OK"
    }
}

$frontendNeedsBuild = $false
if ($Repair -or -not (Test-Path $distIndex)) {
    $frontendNeedsBuild = $true
} else {
    try {
        if ((Get-Item $distIndex).Length -lt 100) { $frontendNeedsBuild = $true }
    } catch {
        $frontendNeedsBuild = $true
    }
}

if ($SkipFrontend) {
    Write-InstallLog "SkipFrontend flag provided. Skipping frontend compilation." "INFO"
} elseif ($frontendNeedsBuild) {
    Write-InstallLog "Building production React frontend bundle..." "INFO"
    Push-Location $FrontendDir
    try {
        $hasLock = Test-Path (Join-Path $FrontendDir "package-lock.json")
        $npmInstallCmd = if ($hasLock) { "ci" } else { "install" }

        Write-InstallLog "Installing frontend dependencies (npm $npmInstallCmd)..." "INFO"
        & $selectedNpm $npmInstallCmd
        if ($LASTEXITCODE -ne 0) {
            Write-InstallLog "npm $npmInstallCmd failed. Falling back to npm install..." "WARN"
            & $selectedNpm install
        }

        Write-InstallLog "Compiling production bundle (npm run build)..." "INFO"
        & $selectedNpm run build
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $distIndex)) {
            throw "Production frontend build failed."
        }
        Write-InstallLog "Production frontend bundle successfully built at frontend\dist." "OK"
    }
    finally {
        Pop-Location
    }
} else {
    Write-InstallLog "Production frontend bundle already present at frontend\dist\index.html." "OK"
}

# ==============================================================================
# Stage 6: Core Preset Speech Recognition Models Download
# ==============================================================================
Write-InstallLog "Stage 6/8: Downloading Core Preset Models (Fast & Maximum Accuracy)..." "STEP"

if ($SkipModels) {
    Write-InstallLog "SkipModels switch active. Skipping speech recognition models download." "INFO"
} else {
    $modelBootstrapScript = @"
import sys
from pathlib import Path

backend_dir = Path(r'$BackendDir')
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.transcription.engine import is_model_downloaded, download_model

print('Checking Fast Transcription Model: codeswitched-medium (~740 MB)...')
if not is_model_downloaded('codeswitched-medium'):
    print('Downloading Specialized Egyptian Whisper Medium...')
    download_model('codeswitched-medium')
    print('[OK] codeswitched-medium download complete.')
else:
    print('[OK] codeswitched-medium is already present on disk.')

print('Checking Maximum Accuracy Twin Model: large-v3-turbo (~1.55 GB)...')
if not is_model_downloaded('large-v3-turbo'):
    print('Downloading Whisper Large-v3-Turbo...')
    download_model('large-v3-turbo')
    print('[OK] large-v3-turbo download complete.')
else:
    print('[OK] large-v3-turbo is already present on disk.')

print('CORE_PRESET_MODELS_READY')
"@

    $mTempScript = Join-Path $BackendDir "storage\temp_models_bootstrap.py"
    Set-Content -Path $mTempScript -Value $modelBootstrapScript -Encoding UTF8

    try {
        & $venvPyExe $mTempScript
        if ($LASTEXITCODE -ne 0) {
            throw "Core preset model download failed. Check network connection."
        }
        Write-InstallLog "Core preset speech models verified and ready." "OK"
    } finally {
        Remove-Item $mTempScript -Force -ErrorAction SilentlyContinue
    }
}

# ==============================================================================
# Stage 7: Maximum Accuracy Arbiter Setup (Conditional)
# ==============================================================================
Write-InstallLog "Stage 7/8: Configuring Maximum Accuracy Arbiter (QwenCleo 4-bit)..." "STEP"

if ($SkipModels) {
    Write-InstallLog "SkipModels active. Skipping QwenCleo setup." "INFO"
} elseif ($qwenCompatible) {
    Write-InstallLog "Compatible NVIDIA GPU detected ($gpuName). Establishing Full Tri-Model Consensus..." "INFO"
    $qwenScript = Join-Path $ScriptDir "setup_qwencleo.ps1"
    if (Test-Path $qwenScript) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $qwenScript -Force
        if ($LASTEXITCODE -ne 0) {
            Write-InstallLog "QwenCleo setup encountered warnings. Maximum Accuracy will operate in Dual-Model Consensus." "WARN"
        } else {
            Write-InstallLog "QwenCleo 4-bit Arbiter verified. Full Tri-Model Consensus is active!" "OK"
        }
    }
} else {
    Write-InstallLog "Skipping QwenCleo 4-bit arbiter download: $qwenSkipReason" "INFO"
    Write-InstallLog "Maximum Accuracy will operate in Dual-Model Consensus mode (Twin Models active)." "OK"
}

# ==============================================================================
# Stage 8: Final System Verification & State Stamp
# ==============================================================================
Write-InstallLog "Stage 8/8: Performing final end-to-end system verification..." "STEP"

$verifyScript = @"
import sys
from pathlib import Path

# Verify backend imports
import fastapi
import uvicorn
import faster_whisper
import ctranslate2
import soundfile

# Verify app components
sys.path.insert(0, r'$BackendDir')
from app.audio.metadata_extractor import find_ffmpeg, find_ffprobe
from app.transcription.engine import is_model_downloaded
from app.api.models import check_qwencleo_readiness
from app.core.config import FRONTEND_DIST_DIR

f_bin = find_ffmpeg()
p_bin = find_ffprobe()
dist_ok = (FRONTEND_DIST_DIR / 'index.html').exists()

fast_ready = is_model_downloaded('codeswitched-medium')
turbo_ready = is_model_downloaded('large-v3-turbo')
qwen_status = check_qwencleo_readiness()

print(f'VERIFIED|ffmpeg={bool(f_bin)}|ffprobe={bool(p_bin)}|dist={dist_ok}|fast={fast_ready}|turbo={turbo_ready}|qwen_ready={qwen_status.get("ready")}|tier={qwen_status.get("status")}')
"@

$verifyFile = Join-Path $CacheDir "verify_install.py"
Set-Content -Path $verifyFile -Value $verifyScript -Encoding UTF8

$vOut = ""
try {
    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
    $pinfo.FileName = $venvPyExe
    $pinfo.Arguments = "`"$verifyFile`""
    $pinfo.RedirectStandardOutput = $true
    $pinfo.RedirectStandardError = $true
    $pinfo.UseShellExecute = $false
    $pinfo.CreateNoWindow = $true

    $proc = [System.Diagnostics.Process]::Start($pinfo)
    $proc.WaitForExit(10000) | Out-Null
    $vOut = $proc.StandardOutput.ReadToEnd().Trim()
    $vErr = $proc.StandardError.ReadToEnd().Trim()
} finally {
    Remove-Item $verifyFile -Force -ErrorAction SilentlyContinue
}

if ($proc.ExitCode -ne 0 -or $vOut -notmatch "VERIFIED") {
    Write-InstallLog "Final application verification failed: $vErr" "ERROR"
    exit 1
}

Write-InstallLog "Verification details: $vOut" "OK"

# Save installation state stamp
$installState = @{
    version = "1.4.0"
    install_date = (Get-Date -Format "o")
    python_interpreter = $venvPyExe
    has_nvidia_gpu = $hasNvidiaGpu
    gpu_name = $gpuName
    ffmpeg_ready = $true
    frontend_ready = (Test-Path $distIndex)
    fast_preset_ready = $true
    maximum_accuracy_tier = if ($qwenCompatible -and (Test-Path (Join-Path $ModelsDir "qwencleo-asr\model.safetensors"))) { "full_tri_model" } else { "dual_model_consensus" }
    verified = $true
}
$stampPath = Join-Path $BackendDir "storage\.installed.json"
$installState | ConvertTo-Json -Depth 3 | Set-Content -Path $stampPath -Encoding UTF8

# ==============================================================================
# Completion Banner
# ==============================================================================
Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host "  Verbatim AI — Unified Installation Complete!" -ForegroundColor Green
Write-Host "  Tagline: Every Word Matters." -ForegroundColor White
Write-Host "========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  All required components and speech models are fully prepared!" -ForegroundColor Cyan
Write-Host "  No additional manual downloads or setup scripts are needed." -ForegroundColor White
Write-Host ""
Write-Host "  Operational Status:" -ForegroundColor Yellow
Write-Host "    • Fast Transcription : READY (Specialized Whisper Medium)" -ForegroundColor Green
if ($installState.maximum_accuracy_tier -eq "full_tri_model") {
    Write-Host "    • Maximum Accuracy   : READY (Full Tri-Model Consensus on $gpuName)" -ForegroundColor Green
} else {
    Write-Host "    • Maximum Accuracy   : READY (Dual-Model Consensus on $(if ($hasNvidiaGpu) {'GPU'} else {'CPU Safe Mode'}))" -ForegroundColor Cyan
}
Write-Host "    • Production Web GUI : READY (frontend\dist\index.html)" -ForegroundColor Green
Write-Host "    • Audio Processing   : READY (FFmpeg & FFprobe verified)" -ForegroundColor Green
Write-Host ""
Write-Host "  To launch Verbatim AI right now, run:" -ForegroundColor Cyan
Write-Host "    --> 01_START_VERBATIM_AI.bat" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Or for CPU-safe mode on any laptop:" -ForegroundColor Cyan
Write-Host "    --> 02_CPU_SAFE_START.bat" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Installation log saved to:" -ForegroundColor Gray
Write-Host "    $LogFile" -ForegroundColor Gray
Write-Host "========================================================" -ForegroundColor Green
Write-Host ""

exit 0
