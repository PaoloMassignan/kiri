#Requires -Version 5.1
<#
.SYNOPSIS
    Kiri Gateway -- Windows uninstaller

.DESCRIPTION
    Removes everything the installer created:
      - Stops and removes the Docker stack
      - Deletes the Scheduled Task (KiriGateway)
      - Removes ANTHROPIC_BASE_URL from user environment
      - Removes the kiri.ps1 wrapper and its directory from PATH

    It does NOT delete the .kiri\ data directory (keys, index, audit log)
    so you can reinstall without losing configuration.
    Use -PurgeData to remove it too.

.PARAMETER PurgeData
    Also delete the .kiri\ directory inside the repo (keys, index, audit log).
    This cannot be undone.

.EXAMPLE
    .\uninstall.ps1
    .\uninstall.ps1 -PurgeData
#>

param(
    [switch]$PurgeData
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot    = Resolve-Path (Join-Path $PSScriptRoot ".." "..")
$KiriDir     = Join-Path $RepoRoot "kiri"
$KiriData    = Join-Path $KiriDir ".kiri"
$WrapperDir  = Join-Path $env:USERPROFILE ".kiri" "bin"
$WrapperPath = Join-Path $WrapperDir "kiri.ps1"

function Write-Step([string]$msg) { Write-Host ""; Write-Host "  --> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "      OK   $msg" -ForegroundColor Green }
function Write-Info([string]$msg) { Write-Host "      ...  $msg" -ForegroundColor DarkGray }
function Write-Warn([string]$msg) { Write-Host "      WARN $msg" -ForegroundColor Yellow }

Write-Host ""
Write-Host "  Kiri Gateway - Windows Uninstaller" -ForegroundColor White
Write-Host "  ====================================" -ForegroundColor DarkGray
Write-Host ""

# -- Stop Docker stack --------------------------------------------------------

Write-Step "Stopping Docker stack..."

if (Test-Path $KiriDir) {
    Push-Location $KiriDir
    try {
        docker compose down 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Stack stopped and containers removed"
        } else {
            Write-Warn "docker compose down returned an error -- stack may already be stopped"
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Info "Kiri directory not found -- skipping"
}

# -- Scheduled Task -----------------------------------------------------------

Write-Step "Removing Scheduled Task..."

if (Get-ScheduledTask -TaskName "KiriGateway" -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName "KiriGateway" -Confirm:$false
    Write-Ok "Scheduled Task 'KiriGateway' removed"
} else {
    Write-Info "Task not found -- skipping"
}

# -- Environment variables ----------------------------------------------------

Write-Step "Removing Kiri environment variables..."

$kirigDefault = "http://localhost:8765"

foreach ($varName in @("ANTHROPIC_BASE_URL", "OPENAI_BASE_URL", "OPENAI_API_BASE")) {
    $current = [System.Environment]::GetEnvironmentVariable($varName, "User")
    if ($current -eq $kirigDefault) {
        [System.Environment]::SetEnvironmentVariable($varName, $null, "User")
        Remove-Item "Env:\$varName" -ErrorAction SilentlyContinue
        Write-Ok "$varName removed"
    } elseif ($current) {
        Write-Warn "$varName is '$current' (not the Kiri default) -- leaving unchanged"
    } else {
        Write-Info "$varName not set -- skipping"
    }
}

# -- CLI wrapper --------------------------------------------------------------

Write-Step "Removing kiri CLI wrapper..."

if (Test-Path $WrapperPath) {
    Remove-Item $WrapperPath -Force
    Write-Ok "Removed $WrapperPath"
} else {
    Write-Info "Wrapper not found -- skipping"
}

$userPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -like "*$WrapperDir*") {
    $parts   = $userPath -split ";"
    $newPath = ($parts | Where-Object { $_ -ne $WrapperDir }) -join ";"
    [System.Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
    Write-Ok "Removed $WrapperDir from user PATH"
} else {
    Write-Info "PATH did not contain $WrapperDir -- skipping"
}

if ((Test-Path $WrapperDir) -and ((Get-ChildItem $WrapperDir).Count -eq 0)) {
    Remove-Item $WrapperDir -Force
}

# -- Data directory -----------------------------------------------------------

Write-Step "Data directory..."

if ($PurgeData) {
    if (Test-Path $KiriData) {
        Remove-Item $KiriData -Recurse -Force
        Write-Ok "Deleted $KiriData"
    } else {
        Write-Info "Not found -- skipping"
    }
} else {
    Write-Info "Preserved: $KiriData"
    Write-Info "Re-run with -PurgeData to delete keys, index, and audit log"
}

# -- Done ---------------------------------------------------------------------

Write-Host ""
Write-Host "  Kiri uninstalled." -ForegroundColor Green
Write-Host ""
if (-not $PurgeData) {
    Write-Host "  Data preserved at: $KiriData" -ForegroundColor DarkGray
}
Write-Host "  To reinstall: .\install\windows\install.ps1" -ForegroundColor DarkGray
Write-Host ""
