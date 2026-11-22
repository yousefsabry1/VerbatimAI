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
    [switch]$NonInteractive,
    [switch]$FunctionsOnly
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
$BackendLogsDir = Join-Path $BackendDir "storage\logs"
$ModelsDir = Join-Path $BackendDir "storage\models"

# Ensure essential directories exist
foreach ($dir in @($ToolsDir, $CacheDir, $LogsDir, $BackendLogsDir, $ModelsDir)) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogFile = Join-Path $LogsDir "install-$Timestamp.log"
$LatestLogFile = Join-Path $LogsDir "install.log"
$BackendLogFile = Join-Path $BackendLogsDir "install.log"

function Write-InstallLog {
    param(
        [string]$Message,
        [string]$Level = "INFO",
        [ConsoleColor]$Color = [ConsoleColor]::White
    )
    $timeStr = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logLine = "[$timeStr] [$Level] $Message"
    Add-Content -Path $LogFile -Value $logLine -Encoding UTF8
    Add-Content -Path $LatestLogFile -Value $logLine -Encoding UTF8
    Add-Content -Path $BackendLogFile -Value $logLine -Encoding UTF8
    
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

function Update-SessionPath {
    try {
        $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
        $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
        $combined = @($userPath, $machinePath) -join ";"
        $env:PATH = $combined
        Write-InstallLog "Refreshed session PATH from Windows Registry." "DEBUG"
    } catch {
        Write-InstallLog "Failed to refresh session PATH: $_" "WARN"
    }
}

function Download-FileWithProgress {
    param(
        [string]$Url,
        [string]$DestinationPath,
        [string]$Description = "Downloading file",
        [string]$ExpectedSha256 = "",
        [bool]$ValidateSignature = $false
    )
    Write-InstallLog "$Description from $Url..." "INFO"
    $destDir = Split-Path -Parent $DestinationPath
    if (-not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }

    # Ensure TLS 1.2 is enabled in current PowerShell session
    try {
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12
    } catch {
        try {
            [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]3072
        } catch {}
    }

    # Test for System.Net.Http availability
    $httpClientAvailable = $false
    try {
        Add-Type -AssemblyName System.Net.Http -ErrorAction Stop
        $httpClientAvailable = $true
    } catch {
        Write-InstallLog "System.Net.Http assembly not preloaded: $($_.Exception.Message). Using native WebClient engine." "DEBUG"
    }

    # Clean up any stale partial downloads for this destination
    Get-ChildItem -Path "$DestinationPath.downloading*" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    $tempDest = "$DestinationPath.downloading_$PID"
    if (Test-Path $tempDest) { Remove-Item $tempDest -Force -ErrorAction SilentlyContinue }

    $maxRetries = 3
    $attempt = 0
    $downloadSuccess = $false

    while ($attempt -lt $maxRetries -and -not $downloadSuccess) {
        $attempt++
        try {
            if ($httpClientAvailable) {
                # Engine 1: HttpClient with streaming chunk progress
                $handler = $null
                $client = $null
                $response = $null
                $stream = $null
                $fileStream = $null
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
                } finally {
                    if ($fileStream) { $fileStream.Flush(); $fileStream.Close(); $fileStream.Dispose() }
                    if ($stream) { $stream.Close(); $stream.Dispose() }
                    if ($response) { $response.Dispose() }
                    if ($client) { $client.Dispose() }
                    if ($handler) { $handler.Dispose() }
                }
            } else {
                # Engine 2: Native WebClient stream with progress
                $webClient = $null
                $stream = $null
                $fileStream = $null
                try {
                    $webClient = New-Object System.Net.WebClient
                    $webClient.Headers.Add("User-Agent", "VerbatimAI-Installer/1.4.0 (Windows NT)")

                    $stream = $webClient.OpenRead($Url)
                    $totalBytes = -1
                    if ($webClient.ResponseHeaders["Content-Length"]) {
                        [long]::TryParse($webClient.ResponseHeaders["Content-Length"], [ref]$totalBytes) | Out-Null
                    }

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
                } finally {
                    if ($fileStream) { $fileStream.Flush(); $fileStream.Close(); $fileStream.Dispose() }
                    if ($stream) { $stream.Close(); $stream.Dispose() }
                    if ($webClient) { $webClient.Dispose() }
                }
            }

            # Check that temp file exists and is not empty
            if (-not (Test-Path $tempDest) -or (Get-Item $tempDest).Length -eq 0) {
                throw "Downloaded file is empty or missing at $tempDest"
            }

            # Cryptographic checksum verification (if specified)
            if ($ExpectedSha256) {
                Write-InstallLog "Verifying cryptographic checksum for $Description..." "INFO"
                $actualHash = (Get-FileHash -Path $tempDest -Algorithm SHA256).Hash.ToLower()
                if ($actualHash -ne $ExpectedSha256.ToLower()) {
                    Remove-Item $tempDest -Force -ErrorAction SilentlyContinue
                    throw "Cryptographic SHA256 mismatch for $Description. Expected: $ExpectedSha256, Actual: $actualHash"
                }
                Write-InstallLog "Cryptographic SHA256 verified: $actualHash" "OK"
            }

            # Authenticode signature verification (if specified)
            if ($ValidateSignature) {
                Write-InstallLog "Verifying digital signature for $Description..." "INFO"
                $sig = Get-AuthenticodeSignature -FilePath $tempDest
                if ($sig.Status -ne "Valid") {
                    Remove-Item $tempDest -Force -ErrorAction SilentlyContinue
                    throw "Authenticode signature validation failed for $Description. Status: $($sig.StatusMessage) (Status=$($sig.Status))"
                }
                Write-InstallLog "Digital signature verified: $($sig.SignerCertificate.Subject)" "OK"
            }

            # Atomically finalize download
            if (Test-Path $DestinationPath) { Remove-Item $DestinationPath -Force }
            Move-Item -Path $tempDest -Destination $DestinationPath -Force
            $downloadSuccess = $true
            Write-InstallLog "Download verified and finalized: $DestinationPath" "OK"
        }
        catch {
            Write-InstallLog "Download attempt $attempt failed: $($_.Exception.Message)" "WARN"
            if (Test-Path $tempDest) { Remove-Item $tempDest -Force -ErrorAction SilentlyContinue }

            # Detect fatal non-transient errors
            $errMsg = $_.Exception.Message
            if ($errMsg -match "SHA256 mismatch" -or $errMsg -match "signature validation failed") {
                throw "Integrity check failed: $errMsg"
            }
            if ($errMsg -match "404" -or $errMsg -match "NotFound") {
                throw "Remote resource not found (404): $Url"
            }

            if ($attempt -lt $maxRetries) {
                Write-InstallLog "Retrying download in 5 seconds (attempt $($attempt + 1) of $maxRetries)..." "INFO"
                Start-Sleep -Seconds 5
            } else {
                throw "Failed to download $Url after $maxRetries attempts: $errMsg"
            }
        }
    }
}

function Test-ValidPythonInterpreter {
    param([string]$ExecutablePath)
    if (-not $ExecutablePath -or -not (Test-Path $ExecutablePath)) {
        return $null
    }
    # Reject 0-byte Microsoft Store execution alias stubs
    if ($ExecutablePath -like "*WindowsApps*") {
        try {
            $item = Get-Item $ExecutablePath -ErrorAction SilentlyContinue
            if ($item -and $item.Length -eq 0) {
                return $null
            }
        } catch {}
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
        $outStr = $proc.StandardOutput.ReadToEnd().Trim()
        $errStr = $proc.StandardError.ReadToEnd().Trim()

        if ($proc.ExitCode -eq 0 -and $outStr -notmatch "Microsoft Store" -and $errStr -notmatch "Microsoft Store" -and $outStr -notmatch "Python was not found") {
            $parts = $outStr.Split('.')
            if ($parts.Length -ge 2) {
                $major = [int]$parts[0]
                $minor = [int]$parts[1]
                if ($major -eq 3 -and $minor -ge 10 -and $minor -le 12) {
                    return @{
                        Path = (Resolve-Path $ExecutablePath).Path
                        Version = $outStr
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

function Find-SystemPython {
    param(
        [string]$BackendVirtualEnvPath = ""
    )

    # 1. Existing backend virtual environment
    if ($BackendVirtualEnvPath -and (Test-Path $BackendVirtualEnvPath)) {
        $valid = Test-ValidPythonInterpreter -ExecutablePath $BackendVirtualEnvPath
        if ($valid) { return $valid }
    }

    # 2. Python Launcher (py.exe) - check PATH and standard locations
    $pyLaunchers = @(
        (Get-Command "py.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
        "C:\Windows\py.exe",
        "$env:LOCALAPPDATA\Programs\Python\Launcher\py.exe"
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique

    foreach ($pyL in $pyLaunchers) {
        # Check py -0p output (lists all registered interpreters with paths)
        try {
            $pinfo = New-Object System.Diagnostics.ProcessStartInfo
            $pinfo.FileName = $pyL
            $pinfo.Arguments = "-0p"
            $pinfo.RedirectStandardOutput = $true
            $pinfo.UseShellExecute = $false
            $pinfo.CreateNoWindow = $true
            $proc = [System.Diagnostics.Process]::Start($pinfo)
            $proc.WaitForExit(4000) | Out-Null
            if ($proc.ExitCode -eq 0) {
                $lines = $proc.StandardOutput.ReadToEnd() -split "`r?`n"
                foreach ($line in $lines) {
                    if ($line -match '([A-Za-z]:\\[^\s]+\.exe)') {
                        $candPath = $matches[1]
                        $valid = Test-ValidPythonInterpreter -ExecutablePath $candPath
                        if ($valid) { return $valid }
                    }
                }
            }
        } catch {}

        # Direct py launcher version flags
        foreach ($arg in @("-3.11", "-3.10", "-3.12", "-3")) {
            try {
                $pinfo = New-Object System.Diagnostics.ProcessStartInfo
                $pinfo.FileName = $pyL
                $pinfo.Arguments = "$arg -c `"import sys; print(sys.executable)`""
                $pinfo.RedirectStandardOutput = $true
                $pinfo.UseShellExecute = $false
                $pinfo.CreateNoWindow = $true
                $proc = [System.Diagnostics.Process]::Start($pinfo)
                $proc.WaitForExit(4000) | Out-Null
                if ($proc.ExitCode -eq 0) {
                    $cand = $proc.StandardOutput.ReadToEnd().Trim()
                    $valid = Test-ValidPythonInterpreter -ExecutablePath $cand
                    if ($valid) { return $valid }
                }
            } catch {}
        }
    }

    # 3. python.exe on PATH
    $pathCommands = Get-Command "python.exe" -All -ErrorAction SilentlyContinue
    foreach ($cmd in $pathCommands) {
        if ($cmd.Source -and ($cmd.Source -notlike "*WindowsApps*")) {
            $valid = Test-ValidPythonInterpreter -ExecutablePath $cmd.Source
            if ($valid) { return $valid }
        }
    }

    # 4. Windows Registry PEP 514 keys (PythonCore)
    $regHives = @("HKCU:\Software\Python\PythonCore", "HKLM:\SOFTWARE\Python\PythonCore", "HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore")
    foreach ($hive in $regHives) {
        if (Test-Path $hive) {
            $verKeys = Get-ChildItem -Path $hive -ErrorAction SilentlyContinue
            foreach ($k in $verKeys) {
                $ipPath = Join-Path $k.PSPath "InstallPath"
                if (Test-Path $ipPath) {
                    $prop = Get-ItemProperty -Path $ipPath -ErrorAction SilentlyContinue
                    $candidates = @($prop.ExecutablePath, (Join-Path $prop.'(default)' "python.exe"))
                    foreach ($cand in $candidates) {
                        if ($cand -and (Test-Path $cand)) {
                            $valid = Test-ValidPythonInterpreter -ExecutablePath $cand
                            if ($valid) { return $valid }
                        }
                    }
                }
            }
        }
    }

    # 5. Windows Uninstall Registry Keys
    $uninstallHives = @("HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
    foreach ($uHive in $uninstallHives) {
        if (Test-Path $uHive) {
            $entries = Get-ChildItem -Path $uHive -ErrorAction SilentlyContinue
            foreach ($entry in $entries) {
                $dn = (Get-ItemProperty -Path $entry.PSPath -Name DisplayName -ErrorAction SilentlyContinue).DisplayName
                if ($dn -and ($dn -like "Python 3.11*" -or $dn -like "Python 3.10*" -or $dn -like "Python 3.12*")) {
                    $il = (Get-ItemProperty -Path $entry.PSPath -Name InstallLocation -ErrorAction SilentlyContinue).InstallLocation
                    if ($il) {
                        $cand = Join-Path $il "python.exe"
                        if (Test-Path $cand) {
                            $valid = Test-ValidPythonInterpreter -ExecutablePath $cand
                            if ($valid) { return $valid }
                        }
                    }
                }
            }
        }
    }

    # 6. Standard User, System, and Package Manager installation directories
    $commonLocations = @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:ProgramFiles\Python311\python.exe",
        "$env:ProgramFiles\Python310\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "${env:ProgramFiles(x86)}\Python311\python.exe",
        "${env:ProgramFiles(x86)}\Python310\python.exe",
        "${env:ProgramFiles(x86)}\Python312\python.exe",
        "C:\Python311\python.exe",
        "C:\Python310\python.exe",
        "C:\Python312\python.exe",
        "$env:ALLUSERSPROFILE\chocolatey\bin\python.exe",
        "$env:USERPROFILE\scoop\apps\python\current\python.exe"
    )
    foreach ($loc in $commonLocations) {
        if (Test-Path $loc) {
            $valid = Test-ValidPythonInterpreter -ExecutablePath $loc
            if ($valid) { return $valid }
        }
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

# Return early if dot-sourced or functions-only mode requested
if ($MyInvocation.InvocationName -eq '.' -or $FunctionsOnly) {
    return
}

# ==============================================================================
# Banner & Hardware Assessment
# ==============================================================================
$global:CurrentInstallStage = "Hardware Assessment & Resource Audit"
$global:StageFailureAction = "Ensure your system is a 64-bit Windows operating system with sufficient disk space."

try {
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
$global:CurrentInstallStage = "Stage 1/8: Initializing storage directories and configuration"
$global:StageFailureAction = "Check file and folder permissions in the VerbatimAI directory."
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
$global:CurrentInstallStage = "Stage 2/8: Establishing Python 3.11 runtime & virtual environment"
$global:StageFailureAction = "Ensure internet connectivity to python.org or install Python 3.11 from python.org manually."
Write-InstallLog "Stage 2/8: Establishing Python 3.11 runtime & virtual environment..." "STEP"

$venvDir = Join-Path $BackendDir ".venv"
$venvPyExe = Join-Path $venvDir "Scripts\python.exe"
$selectedPython = Find-SystemPython -BackendVirtualEnvPath $venvPyExe

if ($selectedPython) {
    Write-InstallLog "Compatible Python discovered: $($selectedPython.Path) (Python $($selectedPython.Version))" "OK"
} else {
    Write-InstallLog "No compatible Python installation found on system. Initiating automated Python 3.11 setup..." "WARN"

    # Step 2A: Attempt user-scope winget installation if winget is available
    $wingetCmd = Get-Command "winget.exe" -ErrorAction SilentlyContinue
    if ($wingetCmd) {
        Write-InstallLog "Attempting user-scope Python 3.11 installation via winget..." "INFO"
        try {
            $wingetArgs = "install --id Python.Python.3.11 -e --scope user --accept-source-agreements --accept-package-agreements --silent"
            $p = Start-Process -FilePath "winget.exe" -ArgumentList $wingetArgs -Wait -PassThru -NoNewWindow
            Write-InstallLog "winget invocation completed with exit code $($p.ExitCode)." "INFO"
        } catch {
            Write-InstallLog "winget invocation failed: $_" "WARN"
        }

        # Refresh session environment variables from Windows Registry
        Update-SessionPath

        # Crucial: Independently rediscover Python before downloading official installer!
        $selectedPython = Find-SystemPython -BackendVirtualEnvPath $venvPyExe
        if ($selectedPython) {
            Write-InstallLog "Python successfully discovered after winget setup: $($selectedPython.Path) (Python $($selectedPython.Version))" "OK"
        }
    }

    # Step 2B: If not found after winget, download and run official Python 3.11.9 installer
    if (-not $selectedPython) {
        Write-InstallLog "Bootstrapping official Python 3.11.9 64-bit installer from python.org..." "INFO"
        $pythonInstallerUrl = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
        $installerPath = Join-Path $CacheDir "python-3.11.9-amd64.exe"
        $officialPythonSha256 = "5ee42c4eee1e6b4464bb23722f90b45303f79442df63083f05322f1785f5fdde"

        # Check if valid cached installer already exists
        $needDownload = $true
        if (Test-Path $installerPath) {
            $cachedHash = (Get-FileHash -Path $installerPath -Algorithm SHA256).Hash.ToLower()
            if ($cachedHash -eq $officialPythonSha256.ToLower()) {
                Write-InstallLog "Verified existing cached Python installer: $installerPath" "OK"
                $needDownload = $false
            } else {
                Remove-Item $installerPath -Force -ErrorAction SilentlyContinue
            }
        }

        if ($needDownload) {
            Download-FileWithProgress `
                -Url $pythonInstallerUrl `
                -DestinationPath $installerPath `
                -Description "Official Python 3.11.9 Installer" `
                -ExpectedSha256 $officialPythonSha256 `
                -ValidateSignature $true
        }

        Write-InstallLog "Installing Python 3.11 to user profile (per-user, no admin prompt needed)..." "INFO"
        $installArgs = "/quiet InstallAllUsers=0 Include_pip=1 Include_launcher=1 PrependPath=1 SimpleInstall=1"
        $instProc = Start-Process -FilePath $installerPath -ArgumentList $installArgs -Wait -PassThru -NoNewWindow
        Write-InstallLog "Python installer completed with exit code $($instProc.ExitCode)." "INFO"

        # Refresh session environment variables from Windows Registry
        Update-SessionPath

        # Re-scan for installed Python
        $selectedPython = Find-SystemPython -BackendVirtualEnvPath $venvPyExe
    }

    if (-not $selectedPython) {
        throw "Automated Python 3.11 installation finished, but no functional Python 3.10-3.12 interpreter could be discovered on the system."
    }

    Write-InstallLog "Python verified and ready: $($selectedPython.Path) (Python $($selectedPython.Version))" "OK"
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
$global:CurrentInstallStage = "Stage 3/8: Installing Python libraries & runtime dependencies"
$global:StageFailureAction = "Check your internet connection and verify that pip can access PyPI (pypi.org)."
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
$global:CurrentInstallStage = "Stage 4/8: Checking FFmpeg and FFprobe audio engine"
$global:StageFailureAction = "Check your internet connection to download FFmpeg release archives from GitHub or gyan.dev."
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
$global:CurrentInstallStage = "Stage 5/8: Checking Node.js, npm, and production frontend"
$global:StageFailureAction = "Check internet connectivity to nodejs.org, or pre-install Node.js 18+ from nodejs.org."
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

    $nodeExpectedSha256 = "56e5aacdeee7168871721b75819ccacf2367de8761b78eaceacdecd41e04ca03"
    Download-FileWithProgress `
        -Url $nodeZipUrl `
        -DestinationPath $nodeZip `
        -Description "Portable Node.js LTS Archive" `
        -ExpectedSha256 $nodeExpectedSha256

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
$global:CurrentInstallStage = "Stage 6/8: Downloading Core Preset Models (Fast & Maximum Accuracy)"
$global:StageFailureAction = "Check internet connectivity to HuggingFace (huggingface.co) and ensure ~3 GB free disk space."
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
$global:CurrentInstallStage = "Stage 7/8: Configuring Maximum Accuracy Arbiter (QwenCleo 4-bit)"
$global:StageFailureAction = "Ensure compatible NVIDIA GPU with >= 4GB VRAM and ~6.5 GB free disk space."
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
$global:CurrentInstallStage = "Stage 8/8: Performing final end-to-end system verification"
$global:StageFailureAction = "Review the installation log for missing dependencies or failed validation assertions."
Write-InstallLog "Stage 8/8: Performing final end-to-end system verification..." "STEP"

$verifyScript = @"
import sys
import json
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
qwen_status = check_qwencleo_readiness(verify_runtime=True)

payload = {
    "status": "VERIFIED",
    "ffmpeg": bool(f_bin),
    "ffprobe": bool(p_bin),
    "dist": bool(dist_ok),
    "fast": bool(fast_ready),
    "turbo": bool(turbo_ready),
    "qwen_ready": bool(qwen_status.get("ready")),
    "qwen_status": qwen_status.get("status"),
    "qwen_reason": qwen_status.get("reason"),
    "qwen_runtime_verified": bool(qwen_status.get("runtime_verified")),
}

print(f'VERIFIED|ffmpeg={bool(f_bin)}|ffprobe={bool(p_bin)}|dist={dist_ok}|fast={fast_ready}|turbo={turbo_ready}|qwen_ready={qwen_status.get("ready")}|tier={qwen_status.get("status")}')
print('__VERIFIED_JSON__' + json.dumps(payload))
"@

$verifyFile = Join-Path $CacheDir "verify_install.py"
Set-Content -Path $verifyFile -Value $verifyScript -Encoding UTF8

$vOut = ""
$vErr = ""
try {
    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
    $pinfo.FileName = $venvPyExe
    $pinfo.Arguments = "`"$verifyFile`""
    $pinfo.RedirectStandardOutput = $true
    $pinfo.RedirectStandardError = $true
    $pinfo.UseShellExecute = $false
    $pinfo.CreateNoWindow = $true

    $proc = [System.Diagnostics.Process]::Start($pinfo)
    $proc.WaitForExit(35000) | Out-Null
    $vOut = $proc.StandardOutput.ReadToEnd().Trim()
    $vErr = $proc.StandardError.ReadToEnd().Trim()
} finally {
    Remove-Item $verifyFile -Force -ErrorAction SilentlyContinue
}

if ($proc.ExitCode -ne 0) {
    Write-InstallLog "Final application verification failed with exit code $($proc.ExitCode): $vErr" "ERROR"
    exit 1
}

$jsonMatch = [regex]::Match($vOut, '__VERIFIED_JSON__(.*)')
if (-not $jsonMatch.Success) {
    Write-InstallLog "Final verification output missing structured JSON payload: $vOut $vErr" "ERROR"
    exit 1
}

$vObj = $null
try {
    $vObj = $jsonMatch.Groups[1].Value | ConvertFrom-Json
} catch {
    Write-InstallLog "Failed to parse verification JSON payload: $_" "ERROR"
    exit 1
}

# 1. Assert mandatory media dependencies
if (-not $vObj.ffmpeg -or -not $vObj.ffprobe) {
    Write-InstallLog "Verification assertion failed: FFmpeg (found=$($vObj.ffmpeg)) or FFprobe (found=$($vObj.ffprobe)) is missing or non-executable." "ERROR"
    exit 1
}

# 2. Assert frontend production bundle unless explicitly skipped
if (-not $SkipFrontend -and -not $vObj.dist) {
    Write-InstallLog "Verification assertion failed: Frontend production build (dist/index.html) is missing. Build frontend or run with -SkipFrontend." "ERROR"
    exit 1
}

# 3. Assert core speech models unless explicitly skipped
if (-not $SkipModels) {
    if (-not $vObj.fast) {
        Write-InstallLog "Verification assertion failed: Fast speech model (codeswitched-medium) is not downloaded or incomplete." "ERROR"
        exit 1
    }
    if (-not $vObj.turbo) {
        Write-InstallLog "Verification assertion failed: Turbo speech model (large-v3-turbo) is not downloaded or incomplete." "ERROR"
        exit 1
    }
}

Write-InstallLog "Verification assertions passed." "OK"
Write-InstallLog "Verification details: ffmpeg=$($vObj.ffmpeg), ffprobe=$($vObj.ffprobe), dist=$($vObj.dist), fast=$($vObj.fast), turbo=$($vObj.turbo), qwen_ready=$($vObj.qwen_ready)" "INFO"

# Derive truthful installation state stamp from real verification results
$isPartial = [bool]($SkipFrontend -or $SkipModels -or (-not $vObj.dist) -or (-not $vObj.fast) -or (-not $vObj.turbo))

$maxTier = if ($vObj.qwen_ready) {
    "full_tri_model"
} elseif ($vObj.fast -and $vObj.turbo) {
    "dual_model_consensus"
} else {
    "needs_models"
}

$installState = @{
    version = "1.4.0"
    install_date = (Get-Date -Format "o")
    python_interpreter = $venvPyExe
    has_nvidia_gpu = $hasNvidiaGpu
    gpu_name = $gpuName
    ffmpeg_ready = [bool]($vObj.ffmpeg -and $vObj.ffprobe)
    frontend_ready = [bool]$vObj.dist
    fast_preset_ready = [bool]$vObj.fast
    turbo_preset_ready = [bool]$vObj.turbo
    qwencleo_ready = [bool]$vObj.qwen_ready
    qwencleo_status = $vObj.qwen_status
    qwencleo_reason = $vObj.qwen_reason
    maximum_accuracy_tier = $maxTier
    partial_install = $isPartial
    skip_frontend_flag = [bool]$SkipFrontend
    skip_models_flag = [bool]$SkipModels
    verified = [bool]($vObj.ffmpeg -and $vObj.ffprobe -and ($SkipFrontend -or $vObj.dist) -and ($SkipModels -or ($vObj.fast -and $vObj.turbo)))
}
$stampPath = Join-Path $BackendDir "storage\.installed.json"
$installState | ConvertTo-Json -Depth 3 | Set-Content -Path $stampPath -Encoding UTF8

# ==============================================================================
# Completion Banner
# ==============================================================================
Write-Host ""
if ($installState.partial_install) {
    Write-Host "========================================================" -ForegroundColor Yellow
    Write-Host "  Verbatim AI — Partial Installation Configured" -ForegroundColor Yellow
    Write-Host "  Tagline: Every Word Matters." -ForegroundColor White
    Write-Host "========================================================" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Note: Some components were skipped (-SkipFrontend or -SkipModels)." -ForegroundColor Yellow
} else {
    Write-Host "========================================================" -ForegroundColor Green
    Write-Host "  Verbatim AI — Unified Installation Complete!" -ForegroundColor Green
    Write-Host "  Tagline: Every Word Matters." -ForegroundColor White
    Write-Host "========================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  All required components and speech models are fully prepared!" -ForegroundColor Cyan
}
Write-Host ""
Write-Host "  Operational Status:" -ForegroundColor Yellow
if ($installState.fast_preset_ready) {
    Write-Host "    • Fast Transcription : READY (Specialized Whisper Medium)" -ForegroundColor Green
} else {
    Write-Host "    • Fast Transcription : SKIPPED (run 00_INSTALL.bat without -SkipModels to download)" -ForegroundColor Yellow
}

if ($installState.maximum_accuracy_tier -eq "full_tri_model") {
    Write-Host "    • Maximum Accuracy   : READY (Full Tri-Model Consensus on $gpuName)" -ForegroundColor Green
} elseif ($installState.maximum_accuracy_tier -eq "dual_model_consensus") {
    Write-Host "    • Maximum Accuracy   : READY (Dual-Model Consensus on $(if ($hasNvidiaGpu) {'GPU'} else {'CPU Safe Mode'}))" -ForegroundColor Cyan
    if ($vObj.qwen_status -ne "ready") {
        Write-Host "                           [QwenCleo: $($vObj.qwen_reason)]" -ForegroundColor Gray
    }
} else {
    Write-Host "    • Maximum Accuracy   : INCOMPLETE (speech models skipped or missing)" -ForegroundColor Yellow
}

if ($installState.frontend_ready) {
    Write-Host "    • Production Web GUI : READY (frontend\dist\index.html)" -ForegroundColor Green
} else {
    Write-Host "    • Production Web GUI : SKIPPED (run 00_INSTALL.bat without -SkipFrontend to build)" -ForegroundColor Yellow
}

if ($installState.ffmpeg_ready) {
    Write-Host "    • Audio Processing   : READY (FFmpeg & FFprobe verified)" -ForegroundColor Green
} else {
    Write-Host "    • Audio Processing   : FAILED (FFmpeg/FFprobe missing)" -ForegroundColor Red
}

Write-Host ""
Write-Host "  To launch Verbatim AI right now, run:" -ForegroundColor Cyan
Write-Host "    --> 01_START_VERBATIM_AI.bat" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Or for CPU-safe mode on any laptop:" -ForegroundColor Cyan
Write-Host "    --> 02_CPU_SAFE_START.bat" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Installation log saved to:" -ForegroundColor Gray
Write-Host "    $LogFile" -ForegroundColor Gray
Write-Host "========================================================" -ForegroundColor $(if ($installState.partial_install) {'Yellow'} else {'Green'})
Write-Host ""

    exit 0
}
catch {
    Write-Host ""
    Write-Host "========================================================" -ForegroundColor Red
    Write-Host "  Verbatim AI — Installation Failed!" -ForegroundColor Red
    Write-Host "========================================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Failing Stage : $global:CurrentInstallStage" -ForegroundColor Yellow
    Write-Host "  Error Details : $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  Log File Path : $LogFile" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Recommended Action:" -ForegroundColor Yellow
    Write-Host "    $global:StageFailureAction" -ForegroundColor White
    Write-Host ""
    Write-Host "  For support or reporting bugs, please open an issue at:" -ForegroundColor Gray
    Write-Host "    https://github.com/yousefsabry1/VerbatimAI/issues" -ForegroundColor Gray
    Write-Host "========================================================" -ForegroundColor Red
    Write-Host ""

    Write-InstallLog "FATAL ERROR during [$global:CurrentInstallStage]: $($_.Exception.ToString())" "ERROR"

    if (-not $NonInteractive) {
        Write-Host "Press Enter to exit installer..." -ForegroundColor Gray
        Read-Host | Out-Null
    }
    exit 1
}
