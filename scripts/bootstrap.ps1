<#
.SYNOPSIS
    VerbatimAI - Fully Automated Windows Installer & Dependency Bootstrapper
    Tagline: Every Word Matters.

.DESCRIPTION
    Bootstraps all required dependencies for VerbatimAI on a fresh Windows system:
    - Windows 10/11 x64 environment validation
    - Python 3.11 detection or automated user-scope installation
    - Virtual environment creation (backend\.venv)
    - Python dependencies (base + conditional CUDA)
    - FFmpeg and FFprobe binaries download & verification
    - Node.js & npm portable bootstrap
    - Production React frontend build
    - Configuration and storage initialization
    - Comprehensive verification and logging
#>

[CmdletBinding()]
param(
    [switch]$ForceCpu,
    [switch]$SkipFrontend,
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

# Ensure essential directories exist
foreach ($dir in @($ToolsDir, $CacheDir, $LogsDir)) {
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
            # Use System.Net.Http.HttpClient with reasonable timeout
            $handler = New-Object System.Net.Http.HttpClientHandler
            $client = New-Object System.Net.Http.HttpClient($handler)
            $client.Timeout = [System.TimeSpan]::FromMinutes(10)
            $client.DefaultRequestHeaders.Add("User-Agent", "VerbatimAI-Installer/1.3.0 (Windows NT)")

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
    # Reject Microsoft Store execution aliases
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

# ==============================================================================
# Banner
# ==============================================================================
Clear-Host
Write-Host "========================================================" -ForegroundColor Magenta
Write-Host "  Verbatim AI - Fully Automated Windows Installer" -ForegroundColor Magenta
Write-Host "  Tagline: Every Word Matters." -ForegroundColor White
Write-Host "========================================================" -ForegroundColor Magenta
Write-Host ""
Write-InstallLog "Starting VerbatimAI automated dependency installation." "INFO"
Write-InstallLog "Project Directory: $ProjectRoot" "INFO"
Write-InstallLog "Log File: $LogFile" "INFO"

# ==============================================================================
# Step 1: System Checks (OS, RAM, Disk)
# ==============================================================================
Write-InstallLog "Validating Windows environment..." "STEP"

if (-not [System.Environment]::Is64BitOperatingSystem) {
    Write-InstallLog "VerbatimAI requires a 64-bit Windows operating system." "ERROR"
    exit 1
}

$os = Get-CimInstance Win32_OperatingSystem
$osName = $os.Caption
$totalRamGb = [math]::Round($os.TotalVisibleMemorySize / 1024 / 1024, 1)
Write-InstallLog "Operating System: $osName (64-bit)" "OK"
Write-InstallLog "System Physical Memory: $totalRamGb GB" "INFO"

$driveLetter = (Split-Path -Qualifier $ProjectRoot).TrimEnd(':')
$drive = Get-PSDrive -Name $driveLetter -ErrorAction SilentlyContinue
if ($drive) {
    $freeSpaceGb = [math]::Round($drive.Free / 1GB, 1)
    Write-InstallLog "Free disk space on drive $driveLetter`: $freeSpaceGb GB" "INFO"
    if ($freeSpaceGb -lt 4.0) {
        Write-InstallLog "Low disk space ($freeSpaceGb GB). VerbatimAI installation requires at least 4 GB free space." "WARN"
    }
}

# ==============================================================================
# Step 2: Storage Directories & Configuration
# ==============================================================================
Write-InstallLog "Initializing storage directories and configuration..." "STEP"

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
# Step 3: Python Discovery & Installation
# ==============================================================================
Write-InstallLog "Checking for compatible Python (3.11 preferred, 3.10-3.12 supported)..." "STEP"

$venvPy = Join-Path $BackendDir ".venv\Scripts\python.exe"
$selectedPython = $null

# Priority 1: Check existing project virtual environment
if (Test-Path $venvPy) {
    $validVenv = Test-ValidPythonInterpreter -ExecutablePath $venvPy
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

# Priority 5: Missing -> Automated Bootstrap of Python 3.11
if (-not $selectedPython) {
    Write-InstallLog "No compatible Python installation found. Initiating automated Python 3.11 setup..." "WARN"

    $installedViaWinget = $false
    $wingetCmd = Get-Command "winget.exe" -ErrorAction SilentlyContinue

    if ($wingetCmd) {
        Write-InstallLog "Attempting user-scope Python 3.11 installation via Windows Package Manager (winget)..." "INFO"
        try {
            $wingetArgs = "install --id Python.Python.3.11 -e --scope user --accept-source-agreements --accept-package-agreements --silent"
            $p = Start-Process -FilePath "winget.exe" -ArgumentList $wingetArgs -Wait -PassThru -NoNewWindow
            if ($p.ExitCode -eq 0 -or $p.ExitCode -eq 3010) {
                Write-InstallLog "winget installation completed." "OK"
                $installedViaWinget = $true
            } else {
                Write-InstallLog "winget exited with code $($p.ExitCode). Falling back to direct installer..." "WARN"
            }
        }
        catch {
            Write-InstallLog "winget execution failed: $_. Falling back to direct installer..." "WARN"
        }
    }

    if (-not $installedViaWinget) {
        # Direct official Python 3.11.9 64-bit installer
        $pythonInstallerUrl = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
        $installerPath = Join-Path $CacheDir "python-3.11.9-amd64.exe"

        Download-FileWithProgress -Url $pythonInstallerUrl -DestinationPath $installerPath -Description "Official Python 3.11.9 Installer"

        # Verify Authenticode Signature
        Write-InstallLog "Verifying official Python installer digital signature..." "INFO"
        $sig = Get-AuthenticodeSignature -FilePath $installerPath
        if ($sig.Status -ne "Valid") {
            Write-InstallLog "Authenticode signature status is $($sig.Status). Validating MD5 checksum..." "WARN"
            $hash = (Get-FileHash -Path $installerPath -Algorithm MD5).Hash.ToLower()
            if ($hash -ne "e8dcd502e34932eebcaf1be056d5cbcd") {
                throw "Python installer checksum verification failed! Downloaded file may be corrupted."
            }
        } else {
            Write-InstallLog "Digital signature verified: $($sig.SignerCertificate.Subject)" "OK"
        }

        Write-InstallLog "Installing Python 3.11 to user profile (per-user, no admin prompt needed)..." "INFO"
        $installArgs = "/quiet InstallAllUsers=0 Include_pip=1 Include_launcher=1 PrependPath=1 SimpleInstall=1"
        $instProc = Start-Process -FilePath $installerPath -ArgumentList $installArgs -Wait -PassThru -NoNewWindow
        if ($instProc.ExitCode -ne 0 -and $instProc.ExitCode -ne 3010) {
            Write-InstallLog "Python installer exited with code $($instProc.ExitCode)." "WARN"
        }
    }

    # Re-scan for installed Python
    $expectedUserPy = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
    $valid = Test-ValidPythonInterpreter -ExecutablePath $expectedUserPy
    if (-not $valid) {
        # Check PATH again
        $pathPy = Get-Command "python.exe" -ErrorAction SilentlyContinue
        if ($pathPy) { $valid = Test-ValidPythonInterpreter -ExecutablePath $pathPy.Source }
    }

    if (-not $valid) {
        Write-InstallLog "Automated Python installation could not be verified automatically." "ERROR"
        Write-InstallLog "Please install Python 3.11 manually from https://www.python.org/downloads/ and re-run this script." "ERROR"
        exit 1
    }

    $selectedPython = $valid
    Write-InstallLog "Python 3.11 installed and verified: $($selectedPython.Path)" "OK"
}

# ==============================================================================
# Step 4: Python Virtual Environment (backend\.venv)
# ==============================================================================
Write-InstallLog "Setting up backend virtual environment..." "STEP"

$venvDir = Join-Path $BackendDir ".venv"
$venvPyExe = Join-Path $venvDir "Scripts\python.exe"

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
        Write-InstallLog "Virtual environment interpreter appears corrupted. Recreating..." "WARN"
        Remove-Item -Path $venvDir -Recurse -Force -ErrorAction SilentlyContinue
        $basePy = $selectedPython.Path
        $p = Start-Process -FilePath $basePy -ArgumentList "-m venv `"$venvDir`"" -Wait -PassThru -NoNewWindow
        if ($p.ExitCode -ne 0 -or -not (Test-Path $venvPyExe)) {
            Write-InstallLog "Failed to re-create virtual environment." "ERROR"
            exit 1
        }
    } else {
        Write-InstallLog "Virtual environment interpreter is valid." "OK"
    }
}

# Upgrade pip, wheel, setuptools
Write-InstallLog "Upgrading pip, setuptools, and wheel in virtual environment..." "INFO"
& $venvPyExe -m pip install --upgrade pip setuptools wheel --quiet --no-warn-script-location --disable-pip-version-check

# ==============================================================================
# Step 5: Python Dependencies (Base + Conditional CUDA)
# ==============================================================================
Write-InstallLog "Detecting hardware capabilities for Python dependencies..." "STEP"

$hasNvidiaGpu = $false
$gpuName = ""
$nvidiaSmi = Get-Command "nvidia-smi.exe" -ErrorAction SilentlyContinue
if ($nvidiaSmi -and -not $ForceCpu) {
    try {
        $pinfo = New-Object System.Diagnostics.ProcessStartInfo
        $pinfo.FileName = "nvidia-smi.exe"
        $pinfo.Arguments = "--query-gpu=name,memory.total --format=csv,noheader"
        $pinfo.RedirectStandardOutput = $true
        $pinfo.UseShellExecute = $false
        $pinfo.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($pinfo)
        $proc.WaitForExit(3000) | Out-Null
        if ($proc.ExitCode -eq 0) {
            $gpuInfo = $proc.StandardOutput.ReadToEnd().Trim()
            if ($gpuInfo) {
                $hasNvidiaGpu = $true
                $gpuName = $gpuInfo
                Write-InstallLog "NVIDIA GPU detected: $gpuName" "OK"
            }
        }
    } catch {}
}

if ($ForceCpu) {
    Write-InstallLog "CPU Safe Mode requested. Skipping GPU CUDA packages." "INFO"
} elseif (-not $hasNvidiaGpu) {
    Write-InstallLog "No NVIDIA GPU detected. VerbatimAI will run in high-performance CPU int8 mode." "INFO"
}

# Install base requirements
$baseReq = Join-Path $BackendDir "requirements-base.txt"
if (-not (Test-Path $baseReq)) {
    $baseReq = Join-Path $BackendDir "requirements.txt"
}
Write-InstallLog "Installing core backend Python libraries (FastAPI, Faster-Whisper, CTranslate2, etc.)..." "INFO"
& $venvPyExe -m pip install -r $baseReq --no-warn-script-location --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
    Write-InstallLog "Failed to install base Python dependencies. Check internet connectivity." "ERROR"
    exit 1
}
Write-InstallLog "Core Python dependencies installed." "OK"

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
# Step 6: FFmpeg & FFprobe Setup
# ==============================================================================
Write-InstallLog "Checking FFmpeg and FFprobe binaries..." "STEP"

$ffmpegToolsDir = Join-Path $ToolsDir "ffmpeg\bin"
$localFfmpeg = Join-Path $ffmpegToolsDir "ffmpeg.exe"
$localFfprobe = Join-Path $ffmpegToolsDir "ffprobe.exe"

$ffmpegWorking = $false
$ffprobeWorking = $false

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

# Check local project tools first
if ((Test-ExecutableWorking $localFfmpeg) -and (Test-ExecutableWorking $localFfprobe)) {
    $ffmpegWorking = $true
    $ffprobeWorking = $true
    Write-InstallLog "Application-managed FFmpeg and FFprobe detected in tools\ffmpeg\bin." "OK"
}

# Check system PATH if local not present
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

# If missing, bootstrap portable FFmpeg binaries
if (-not $ffmpegWorking -or -not $ffprobeWorking) {
    Write-InstallLog "FFmpeg or FFprobe missing. Initiating automated setup..." "WARN"
    if (-not (Test-Path $ffmpegToolsDir)) {
        New-Item -ItemType Directory -Path $ffmpegToolsDir -Force | Out-Null
    }

    $ffmpegZipUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    $ffmpegZip = Join-Path $CacheDir "ffmpeg-release-essentials.zip"

    Download-FileWithProgress -Url $ffmpegZipUrl -DestinationPath $ffmpegZip -Description "FFmpeg & FFprobe Release Archive"

    Write-InstallLog "Extracting FFmpeg binaries into tools\ffmpeg\bin..." "INFO"
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

    if (-not (Test-ExecutableWorking $localFfmpeg) -or -not (Test-ExecutableWorking $localFfprobe)) {
        throw "Extracted FFmpeg/FFprobe binaries failed execution validation."
    }
    Write-InstallLog "FFmpeg and FFprobe verified and ready." "OK"
}

# ==============================================================================
# Step 7: Node.js, npm & Production Frontend Build
# ==============================================================================
Write-InstallLog "Checking Node.js, npm, and production frontend..." "STEP"

$distIndex = Join-Path $FrontendDir "dist\index.html"
$nodeToolsDir = Join-Path $ToolsDir "node"
$localNode = Join-Path $nodeToolsDir "node.exe"
$localNpm = Join-Path $nodeToolsDir "npm.cmd"

$selectedNode = $null
$selectedNpm = $null

# Check local portable node
if (Test-Path $localNode) {
    try {
        $pinfo = New-Object System.Diagnostics.ProcessStartInfo
        $pinfo.FileName = $localNode
        $pinfo.Arguments = "-v"
        $pinfo.RedirectStandardOutput = $true
        $pinfo.UseShellExecute = $false
        $pinfo.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($pinfo)
        $proc.WaitForExit(3000) | Out-Null
        if ($proc.ExitCode -eq 0) {
            $selectedNode = $localNode
            $selectedNpm = $localNpm
            Write-InstallLog "Application-managed Node.js detected: $localNode ($($proc.StandardOutput.ReadToEnd().Trim()))" "OK"
        }
    } catch {}
}

# Check system node on PATH
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

# If missing, bootstrap portable Node.js LTS
if (-not $selectedNode) {
    Write-InstallLog "Node.js not detected. Bootstrapping official portable Node.js LTS..." "WARN"

    $nodeZipUrl = "https://nodejs.org/dist/v20.18.1/node-v20.18.1-win-x64.zip"
    $nodeZip = Join-Path $CacheDir "node-v20.18.1-win-x64.zip"

    Download-FileWithProgress -Url $nodeZipUrl -DestinationPath $nodeZip -Description "Portable Node.js LTS Archive"

    # Verify SHA256 checksum
    Write-InstallLog "Verifying Node.js archive checksum..." "INFO"
    $nodeHash = (Get-FileHash -Path $nodeZip -Algorithm SHA256).Hash.ToLower()
    if ($nodeHash -ne "56e5aacdeee7168871721b75819ccacf2367de8761b78eaceacdecd41e04ca03") {
        throw "Node.js zip checksum mismatch! Corrupted download."
    }
    Write-InstallLog "Node.js archive checksum verified." "OK"

    Write-InstallLog "Extracting Node.js into tools\node..." "INFO"
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
    } else {
        throw "Failed to extract portable Node.js."
    }
}

# Build production React frontend if needed
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
    Write-InstallLog "Building production React frontend bundle..." "STEP"
    Push-Location $FrontendDir
    try {
        # Check npm lockfile
        $hasLock = Test-Path (Join-Path $FrontendDir "package-lock.json")
        $npmInstallCmd = if ($hasLock) { "ci" } else { "install" }

        Write-InstallLog "Installing frontend npm dependencies (npm $npmInstallCmd)..." "INFO"
        & $selectedNpm $npmInstallCmd
        if ($LASTEXITCODE -ne 0) {
            Write-InstallLog "npm $npmInstallCmd failed. Falling back to npm install..." "WARN"
            & $selectedNpm install
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to install frontend dependencies with npm."
            }
        }

        Write-InstallLog "Compiling production frontend bundle (npm run build)..." "INFO"
        & $selectedNpm run build
        if ($LASTEXITCODE -ne 0) {
            throw "npm run build failed with exit code $LASTEXITCODE."
        }

        if (-not (Test-Path $distIndex) -or (Get-Item $distIndex).Length -lt 100) {
            throw "Production frontend build completed but frontend\dist\index.html was not generated."
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
# Step 8: Final System Verification & State Stamp
# ==============================================================================
Write-InstallLog "Performing final system verification..." "STEP"

# Verify backend health and imports via Python
$verifyScript = @"
import sys
from pathlib import Path

# Verify critical imports
import fastapi
import uvicorn
import faster_whisper
import ctranslate2
import soundfile

# Verify app components
sys.path.insert(0, r'$BackendDir')
from app.audio.metadata_extractor import find_ffmpeg, find_ffprobe
f_bin = find_ffmpeg()
p_bin = find_ffprobe()

from app.core.config import FRONTEND_DIST_DIR
dist_ok = (FRONTEND_DIST_DIR / 'index.html').exists()

print(f'VERIFIED|ffmpeg={f_bin}|ffprobe={p_bin}|dist={dist_ok}')
"@

$verifyFile = Join-Path $CacheDir "verify_install.py"
Set-Content -Path $verifyFile -Value $verifyScript -Encoding UTF8

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
Remove-Item $verifyFile -Force -ErrorAction SilentlyContinue

if ($proc.ExitCode -ne 0 -or $vOut -notmatch "VERIFIED") {
    Write-InstallLog "Final application verification failed: $vErr" "ERROR"
    exit 1
}

Write-InstallLog "Verification details: $vOut" "OK"

# Save installation stamp
$installState = @{
    version = "1.3.0"
    install_date = (Get-Date -Format "o")
    python_interpreter = $venvPyExe
    has_nvidia_gpu = $hasNvidiaGpu
    gpu_name = $gpuName
    ffmpeg_ready = $true
    frontend_ready = (Test-Path $distIndex)
    verified = $true
}
$stampPath = Join-Path $BackendDir "storage\.installed.json"
$installState | ConvertTo-Json -Depth 3 | Set-Content -Path $stampPath -Encoding UTF8

# ==============================================================================
# Completion Banner
# ==============================================================================
Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host "  Verbatim AI Installation Complete & Verified!" -ForegroundColor Green
Write-Host "  Tagline: Every Word Matters." -ForegroundColor White
Write-Host "========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  To launch the application, run:" -ForegroundColor Cyan
Write-Host "    --> 01_START_VERBATIM_AI.bat" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Or for CPU-safe mode on any laptop:" -ForegroundColor Cyan
Write-Host "    --> 02_CPU_SAFE_START.bat" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Operational Tiers:" -ForegroundColor Cyan
Write-Host "    - Base Engine: Ready (Fast Transcription & Hybrid Dual-Model Consensus)" -ForegroundColor White
Write-Host "    - Optional Tri-Model Arbiter (QwenCleo 4-bit):" -ForegroundColor White
Write-Host "      Run: scripts\setup_qwencleo.bat (Requires NVIDIA GPU >= 4GB VRAM, ~6.5 GB disk)" -ForegroundColor Gray
Write-Host ""
Write-Host "  Installation log saved to:" -ForegroundColor Gray
Write-Host "    $LogFile" -ForegroundColor Gray
Write-Host "========================================================" -ForegroundColor Green
Write-Host ""

exit 0
