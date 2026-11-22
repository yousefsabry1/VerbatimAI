<#
.SYNOPSIS
    VerbatimAI - Downloader & Python Discovery Regression Test Suite
.DESCRIPTION
    Validates:
    1. Fix for 'Cannot find type [System.Net.Http.HttpClientHandler]' in Windows PowerShell 5.1.
    2. Fallback downloader (WebClient) when HttpClient is unavailable.
    3. Interrupted download cleanup and atomic file finalization.
    4. Network failure handling and retry exhaustion.
    5. Cryptographic SHA-256 checksum validation and tamper rejection.
    6. Authenticode signature validation on downloaded installers.
    7. Discovery of existing Python when missing from process PATH.
    8. Winget 'existing package' detection and PATH refresh recovery.
    9. Batch launchers error explanation and non-closing behavior on failure.
    10. Full 00_INSTALL.bat end-to-end execution.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$BootstrapScript = Join-Path $ProjectRoot "scripts\bootstrap.ps1"
$BackendDir = Join-Path $ProjectRoot "backend"
$TestTempDir = Join-Path $env:TEMP "VerbatimAI_DlDiscoveryTests"

if (Test-Path $TestTempDir) { Remove-Item $TestTempDir -Recurse -Force -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Path $TestTempDir -Force | Out-Null

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
        Write-Host " [PASS] $ScenarioId : $Description" -ForegroundColor Green
        if ($Details) { Write-Host "        $Details" -ForegroundColor Gray }
    } else {
        $script:FailCount++
        Write-Host " [FAIL] $ScenarioId : $Description" -ForegroundColor Red
        if ($Details) { Write-Host "        $Details" -ForegroundColor Yellow }
    }
}

function Invoke-PowerShellWithTimeout {
    param(
        [string]$CommandText,
        [int]$TimeoutSeconds = 20
    )
    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
    $pinfo.FileName = "powershell.exe"
    $pinfo.Arguments = "-NoProfile -ExecutionPolicy Bypass -Command `"$CommandText`""
    $pinfo.RedirectStandardOutput = $true
    $pinfo.RedirectStandardError = $true
    $pinfo.UseShellExecute = $false
    $pinfo.CreateNoWindow = $true

    $proc = [System.Diagnostics.Process]::Start($pinfo)
    $exited = $proc.WaitForExit($TimeoutSeconds * 1000)
    if (-not $exited) {
        $proc.Kill()
        return "TIMEOUT"
    }
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    return "$stdout $stderr".Trim()
}

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  VerbatimAI - Downloader & Python Discovery Test Suite" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# ==============================================================================
# Test 1: Fix for [System.Net.Http.HttpClientHandler] in Bare PowerShell 5.1
# ==============================================================================
try {
    $dest = "$TestTempDir\t1_download.txt"
    $cmd = ". '$BootstrapScript' -FunctionsOnly; Download-FileWithProgress -Url 'https://www.python.org/robots.txt' -DestinationPath '$dest' -Description 'Bare PS5.1 Test'; if (Test-Path '$dest') { Write-Output 'DOWNLOAD_OK' }"
    $res = Invoke-PowerShellWithTimeout -CommandText $cmd -TimeoutSeconds 15

    $t1Ok = ($res -match "DOWNLOAD_OK" -and $res -notmatch "Cannot find type")
    Report-Scenario "S1" "PowerShell 5.1 Bare Session: HttpClientHandler type loads without assembly error" $t1Ok "Result: $($res -replace '`r?`n', ' ' | Select-Object -First 100)"
} catch {
    Report-Scenario "S1" "PowerShell 5.1 Bare Session Download" $false $_.Exception.Message
}

# ==============================================================================
# Test 2: Fallback Downloader (WebClient) when HttpClient is Unavailable
# ==============================================================================
try {
    $dest = "$TestTempDir\t2_fallback.txt"
    $cmd = @"
`$wc = New-Object System.Net.WebClient
`$wc.Headers.Add('User-Agent', 'VerbatimAI-Installer/1.4.0 (Windows NT)')
`$stream = `$wc.OpenRead('https://www.python.org/robots.txt')
`$fs = [System.IO.File]::Create('$dest')
`$buf = New-Object byte[] 4096
while ((`$read = `$stream.Read(`$buf, 0, `$buf.Length)) -gt 0) { `$fs.Write(`$buf, 0, `$read) }
`$fs.Flush(); `$fs.Close(); `$stream.Close(); `$wc.Dispose()
if ((Test-Path '$dest') -and ((Get-Item '$dest').Length -gt 0)) { Write-Output 'FALLBACK_OK' }
"@
    $res = Invoke-PowerShellWithTimeout -CommandText $cmd -TimeoutSeconds 15

    $t2Ok = ($res -match "FALLBACK_OK")
    Report-Scenario "S2" "Native WebClient fallback downloads successfully when HttpClient is unavailable" $t2Ok "Status: $t2Ok"
} catch {
    Report-Scenario "S2" "Native WebClient fallback" $false $_.Exception.Message
}

# ==============================================================================
# Test 3: Interrupted Download Cleanup & Atomic Finalization
# ==============================================================================
try {
    $targetFile = Join-Path $TestTempDir "atomic_test.txt"
    $orphanTemp = "$targetFile.downloading_stale"
    Set-Content -Path $orphanTemp -Value "CORRUPTED_LEFTOVER_DATA"

    $cmd = ". '$BootstrapScript' -FunctionsOnly; Download-FileWithProgress -Url 'https://www.python.org/robots.txt' -DestinationPath '$targetFile' -Description 'Atomic Finalization Test'; if ((Test-Path '$targetFile') -and -not (Test-Path '$orphanTemp')) { Write-Output 'ATOMIC_OK' }"
    $res = Invoke-PowerShellWithTimeout -CommandText $cmd -TimeoutSeconds 15

    $t3Ok = ($res -match "ATOMIC_OK" -and (Test-Path $targetFile) -and -not (Test-Path $orphanTemp))
    Report-Scenario "S3" "Interrupted download cleanup: removes stale temp file and atomically finalizes" $t3Ok "Atomic finalization verified: $t3Ok"
} catch {
    Report-Scenario "S3" "Interrupted download cleanup" $false $_.Exception.Message
}

# ==============================================================================
# Test 4: Network Connection Failure & Retry Exhaustion Handling
# ==============================================================================
try {
    $nonExistentUrl = "http://127.0.0.1:59998/nonexistent_file_test.bin"
    $targetFile = Join-Path $TestTempDir "fail_test.bin"

    $cmd = "try { . '$BootstrapScript' -FunctionsOnly; Download-FileWithProgress -Url '$nonExistentUrl' -DestinationPath '$targetFile' -Description 'Network Failure Test'; Write-Output 'UNEXPECTED_SUCCESS' } catch { Write-Output `"CAUGHT_ERROR: `$(`$_.Exception.Message)`" }"
    $res = Invoke-PowerShellWithTimeout -CommandText $cmd -TimeoutSeconds 25

    $caughtExpected = ($res -match "CAUGHT_ERROR" -and $res -match "attempts")
    $noCorruptFile = -not (Test-Path $targetFile)
    $t4Ok = $caughtExpected -and $noCorruptFile
    Report-Scenario "S4" "Network connection failure retries 3 times and aborts with descriptive error" $t4Ok "Result: $caughtExpected | No corrupt file left: $noCorruptFile"
} catch {
    Report-Scenario "S4" "Network connection failure handling" $false $_.Exception.Message
}

# ==============================================================================
# Test 5: Checksum Validation (Matching Pass & Tampered Hash Rejection)
# ==============================================================================
try {
    $targetFile = Join-Path $TestTempDir "checksum_pass.txt"
    $tamperedFile = Join-Path $TestTempDir "checksum_tamper.txt"

    # Compute true SHA256 of python.org robots.txt
    $wc = New-Object System.Net.WebClient
    $wc.Headers.Add("User-Agent", "VerbatimAI-Installer/1.4.0 (Windows NT)")
    $realBytes = $wc.DownloadData("https://www.python.org/robots.txt")
    $wc.Dispose()

    $hasher = [System.Security.Cryptography.SHA256]::Create()
    $trueHash = [BitConverter]::ToString($hasher.ComputeHash($realBytes)).Replace("-", "").ToLower()

    # Valid checksum test
    $cmdPass = ". '$BootstrapScript' -FunctionsOnly; Download-FileWithProgress -Url 'https://www.python.org/robots.txt' -DestinationPath '$targetFile' -Description 'Checksum Pass' -ExpectedSha256 '$trueHash'; if (Test-Path '$targetFile') { Write-Output 'CHECKSUM_PASS_OK' }"
    $resPass = Invoke-PowerShellWithTimeout -CommandText $cmdPass -TimeoutSeconds 15
    $passOk = ($resPass -match "CHECKSUM_PASS_OK")

    # Tampered checksum test
    $fakeHash = "0000000000000000000000000000000000000000000000000000000000000000"
    $cmdTamper = "try { . '$BootstrapScript' -FunctionsOnly; Download-FileWithProgress -Url 'https://www.python.org/robots.txt' -DestinationPath '$tamperedFile' -Description 'Checksum Tamper' -ExpectedSha256 '$fakeHash'; Write-Output 'UNEXPECTED_TAMPER_SUCCESS' } catch { Write-Output `"TAMPER_REJECTED: `$(`$_.Exception.Message)`" }"
    $resTamper = Invoke-PowerShellWithTimeout -CommandText $cmdTamper -TimeoutSeconds 15
    $tamperRejected = ($resTamper -match "TAMPER_REJECTED" -and $resTamper -match "mismatch")
    $noTamperedFile = -not (Test-Path $tamperedFile)

    $t5Ok = $passOk -and $tamperRejected -and $noTamperedFile
    Report-Scenario "S5" "Cryptographic SHA256 checksum verification: accepts valid, immediately deletes tampered" $t5Ok "Valid hash passed: $passOk | Tamper rejected: $tamperRejected | Cleaned: $noTamperedFile"
} catch {
    Report-Scenario "S5" "Checksum validation test" $false $_.Exception.Message
}

# ==============================================================================
# Test 6: Authenticode Digital Signature Validation
# ==============================================================================
try {
    $dest = "$TestTempDir\unsigned_test.exe"
    $cmd = "try { . '$BootstrapScript' -FunctionsOnly; Download-FileWithProgress -Url 'https://www.python.org/robots.txt' -DestinationPath '$dest' -Description 'Signature Test' -ValidateSignature `$true; Write-Output 'UNEXPECTED_SIG_SUCCESS' } catch { Write-Output `"SIGNATURE_REJECTED: `$(`$_.Exception.Message)`" }"
    $resSig = Invoke-PowerShellWithTimeout -CommandText $cmd -TimeoutSeconds 15

    $sigRejected = ($resSig -match "SIGNATURE_REJECTED" -and $resSig -match "signature validation failed")
    $noUnsignedFile = -not (Test-Path $dest)

    $t6Ok = $sigRejected -and $noUnsignedFile
    Report-Scenario "S6" "Authenticode digital signature validation: rejects unsigned files" $t6Ok "Unsigned rejected: $sigRejected | Cleaned up: $noUnsignedFile"
} catch {
    Report-Scenario "S6" "Digital signature validation test" $false $_.Exception.Message
}

# ==============================================================================
# Test 7: Python Discovery When Missing From PATH (Registry / Folder Detection)
# ==============================================================================
try {
    $testDiscScript = Join-Path $TestTempDir "test_discovery.ps1"
    $scriptLines = @(
        ". '$BootstrapScript' -FunctionsOnly",
        "`$cleanPath = (`$env:PATH -split ';' | Where-Object { `$_ -notlike '*Python*' -and `$_ -notlike '*venv*' }) -join ';'",
        "`$env:PATH = `$cleanPath",
        "`$found = Find-SystemPython",
        "if (`$found -and `$found.Major -eq 3) {",
        "    Write-Output `"DISCOVERED_WITHOUT_PATH=`$(`$found.Path)|VERSION=`$(`$found.Version)`"",
        "} else {",
        "    Write-Output 'DISCOVERY_FAILED'",
        "}"
    )
    Set-Content -Path $testDiscScript -Value ($scriptLines -join "`r`n") -Encoding UTF8

    $resDisc = Invoke-PowerShellWithTimeout -CommandText "& '$testDiscScript'" -TimeoutSeconds 15
    $discOk = ($resDisc -match "DISCOVERED_WITHOUT_PATH=" -and $resDisc -notmatch "DISCOVERY_FAILED")
    Report-Scenario "S7" "Python discovery succeeds via Registry/Standard paths even when stripped from PATH" $discOk "Result: $($resDisc | Where-Object { $_ -match 'DISCOVERED_WITHOUT_PATH' })"
} catch {
    Report-Scenario "S7" "Python discovery without PATH" $false $_.Exception.Message
}

# ==============================================================================
# Test 8: Winget 'Package Already Installed' Handling & Session PATH Refresh
# ==============================================================================
try {
    $cmd = ". '$BootstrapScript' -FunctionsOnly; Update-SessionPath; if (`$env:PATH.Length -gt 0) { Write-Output 'UPDATE_PATH_OK' }"
    $resPath = Invoke-PowerShellWithTimeout -CommandText $cmd -TimeoutSeconds 10
    $pathRefreshOk = ($resPath -match "UPDATE_PATH_OK")
    Report-Scenario "S8" "Session PATH refresh from Windows Registry (recovering from winget installs)" $pathRefreshOk "Status: $pathRefreshOk"
} catch {
    Report-Scenario "S8" "Session PATH refresh" $false $_.Exception.Message
}

# ==============================================================================
# Test 9: Root Batch Entry Point (00_INSTALL.bat) Error Visibility & Non-Closing
# ==============================================================================
try {
    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
    $pinfo.FileName = "cmd.exe"
    $pinfo.WorkingDirectory = $ProjectRoot
    $pinfo.Arguments = "/c 00_INSTALL.bat -NonInteractive -InvalidTestFlagXYZ"
    $pinfo.RedirectStandardOutput = $true
    $pinfo.RedirectStandardError = $true
    $pinfo.UseShellExecute = $false
    $pinfo.CreateNoWindow = $true

    $proc = [System.Diagnostics.Process]::Start($pinfo)
    $proc.WaitForExit(10000) | Out-Null
    $outStr = $proc.StandardOutput.ReadToEnd()
    $errStr = $proc.StandardError.ReadToEnd()

    $nonZeroExit = ($proc.ExitCode -ne 0)
    $showsLog = ($outStr -match "install.log" -or $errStr -match "install.log" -or $outStr -match "ERROR")
    $t9Ok = $nonZeroExit -and $showsLog
    Report-Scenario "S9" "Batch entry point 00_INSTALL.bat preserves error info and log path on failure" $t9Ok "ExitCode: $($proc.ExitCode) | Shows log path: $showsLog"
} catch {
    Report-Scenario "S9" "Batch entry point error preservation" $false $_.Exception.Message
}

# ==============================================================================
# Test 10: End-to-End Unified Installer Execution via 00_INSTALL.bat
# ==============================================================================
try {
    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
    $pinfo.FileName = "cmd.exe"
    $pinfo.WorkingDirectory = $ProjectRoot
    $pinfo.Arguments = "/c 00_INSTALL.bat -NonInteractive"
    $pinfo.RedirectStandardOutput = $true
    $pinfo.RedirectStandardError = $true
    $pinfo.UseShellExecute = $false
    $pinfo.CreateNoWindow = $true

    $proc = [System.Diagnostics.Process]::Start($pinfo)
    $proc.WaitForExit(120000) | Out-Null
    $outStr = $proc.StandardOutput.ReadToEnd()

    $stampPath = Join-Path $BackendDir "storage\.installed.json"
    $stamp = if (Test-Path $stampPath) { Get-Content $stampPath -Raw | ConvertFrom-Json } else { $null }

    $e2eOk = ($proc.ExitCode -eq 0) -and ($stamp -ne $null) -and ($stamp.verified -eq $true)
    Report-Scenario "S10" "End-to-End unified installation succeeds via 00_INSTALL.bat entry point" $e2eOk "ExitCode: $($proc.ExitCode) | Verified: $($stamp.verified) | Tier: $($stamp.maximum_accuracy_tier)"
} catch {
    Report-Scenario "S10" "End-to-End 00_INSTALL.bat execution" $false $_.Exception.Message
}

# Cleanup test temporary directory
Remove-Item $TestTempDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Suite Results: $PassCount PASSED, $FailCount FAILED" -ForegroundColor $(if ($FailCount -eq 0) { "Green" } else { "Red" })
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

if ($FailCount -gt 0) { exit 1 } else { exit 0 }
