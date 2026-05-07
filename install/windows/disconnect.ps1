#Requires -Version 5.1
<#
.SYNOPSIS
    Kiri Gateway -- team developer disconnector

.DESCRIPTION
    Removes the environment variables set by connect.ps1.
    Does not touch Docker, Scheduled Tasks, or the kiri CLI wrapper.

    Use this when you were connected to a shared team gateway via connect.ps1.
    If you ran the full install.ps1 (local Docker), use uninstall.ps1 instead.

.EXAMPLE
    .\disconnect.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step([string]$msg) { Write-Host ""; Write-Host "  --> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "      OK   $msg" -ForegroundColor Green }
function Write-Info([string]$msg) { Write-Host "      ...  $msg" -ForegroundColor DarkGray }

Write-Host ""
Write-Host "  Kiri Gateway - Disconnect from team gateway" -ForegroundColor White
Write-Host "  =============================================" -ForegroundColor DarkGray
Write-Host ""

# -- Environment variables ----------------------------------------------------

Write-Step "Removing Kiri environment variables..."

$removed = 0
foreach ($varName in @("ANTHROPIC_BASE_URL", "OPENAI_BASE_URL", "OPENAI_API_BASE")) {
    $current = [System.Environment]::GetEnvironmentVariable($varName, "User")
    if ($current) {
        Write-Info "Removing $varName (was: $current)"
        [System.Environment]::SetEnvironmentVariable($varName, $null, "User")
        [System.Environment]::SetEnvironmentVariable($varName, $null, "Process")
        Remove-Item "Env:\$varName" -ErrorAction SilentlyContinue
        Write-Ok "$varName removed"
        $removed++
    } else {
        Write-Info "$varName not set -- skipping"
    }
}

if ($removed -eq 0) {
    Write-Host ""
    Write-Host "  Nothing to remove -- no Kiri env vars were set." -ForegroundColor DarkGray
    Write-Host ""
    exit 0
}

# -- Done ---------------------------------------------------------------------

Write-Host ""
Write-Host "  Disconnected." -ForegroundColor Green
Write-Host ""
Write-Host "  Restart open terminals for the change to take effect." -ForegroundColor DarkGray
Write-Host "  To reconnect: .\install\windows\connect.ps1" -ForegroundColor DarkGray
Write-Host ""
