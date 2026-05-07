#Requires -Version 5.1
<#
.SYNOPSIS
    Kiri Gateway -- Windows installer

.DESCRIPTION
    Installs Kiri as a background service on Windows.

    What this script does:
      1. Verifies Docker Desktop is installed and running
      2. Stores your Anthropic API key as a Docker secret (never in git, never in logs)
      3. Builds the Docker image and starts the full stack (Kiri + Ollama)
         Note: first run downloads the Ollama model (~2 GB) -- allow 5-30 min
      4. Sets ANTHROPIC_BASE_URL=http://localhost:8765 in your user environment
      5. Creates a Scheduled Task so the stack restarts automatically at login
      6. Installs a kiri.ps1 wrapper on your PATH so you can run kiri commands
         from any terminal without Python or extra tools on the host

    After installation Claude Code, Cursor, and Copilot route automatically
    through the gateway. You will not notice any difference unless a protected
    symbol is detected.

.PARAMETER AnthropicKey
    Your Anthropic API key (sk-ant-...). If omitted you will be prompted.
    The key is written only to .kiri\upstream.key inside the repo and mounted
    into the Docker container as a secret -- never exposed in logs or env output.

.PARAMETER SkipBuild
    Skip docker compose build (use when the image is already built).

.EXAMPLE
    .\install.ps1
    .\install.ps1 -AnthropicKey sk-ant-xxxxxxx
    .\install.ps1 -SkipBuild

.NOTES
    Run from PowerShell. Docker Desktop must be installed first:
    https://www.docker.com/products/docker-desktop/
#>

param(
    [string]$AnthropicKey = "",
    [switch]$SkipBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

$RepoRoot    = Resolve-Path (Join-Path $PSScriptRoot ".." "..")
$KiriDir     = Join-Path $RepoRoot "kiri"
$KiriData    = Join-Path $KiriDir ".kiri"
$WrapperDir  = Join-Path $env:USERPROFILE ".kiri" "bin"
$WrapperPath = Join-Path $WrapperDir "kiri.ps1"

# --------------------------------------------------------------------------- #
# Output helpers
# --------------------------------------------------------------------------- #

function Write-Banner {
    Write-Host ""
    Write-Host "  Kiri Gateway - Windows Installer" -ForegroundColor White
    Write-Host "  ==================================" -ForegroundColor DarkGray
    Write-Host ""
}

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "  --> $msg" -ForegroundColor Cyan
}

function Write-Ok([string]$msg)   { Write-Host "      OK   $msg" -ForegroundColor Green }
function Write-Info([string]$msg) { Write-Host "      ...  $msg" -ForegroundColor DarkGray }
function Write-Warn([string]$msg) { Write-Host "      WARN $msg" -ForegroundColor Yellow }

function Fail([string]$msg) {
    Write-Host ""
    Write-Host "  ERROR: $msg" -ForegroundColor Red
    Write-Host ""
    exit 1
}

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

function Test-DockerRunning {
    try {
        docker ps 2>&1 | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Wait-ForGateway([int]$TimeoutSeconds = 600) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $attempt  = 0
    while ((Get-Date) -lt $deadline) {
        $attempt++
        try {
            $r = Invoke-WebRequest "http://localhost:8765/health" `
                     -UseBasicParsing -TimeoutSec 3 -ErrorAction SilentlyContinue
            if ($r.StatusCode -eq 200) { return $true }
        } catch { }
        if ($attempt % 5 -eq 0) {
            $elapsed = [int]((Get-Date) - ($deadline.AddSeconds(-$TimeoutSeconds))).TotalSeconds
            Write-Info "still waiting... ${elapsed}s elapsed (model download can take 5-30 min on first run)"
        }
        Start-Sleep -Seconds 3
    }
    return $false
}

# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

Write-Banner

# -- Step 1: Docker -----------------------------------------------------------

Write-Step "Checking Docker Desktop..."

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "Docker not found. Install Docker Desktop from https://www.docker.com/products/docker-desktop/ then re-run."
}
Write-Ok "docker CLI found"

if (-not (Test-DockerRunning)) {
    Fail "Docker daemon is not responding. Open Docker Desktop, wait for it to start, then re-run."
}
Write-Ok "Docker daemon is running"

# -- Step 2: Anthropic key ----------------------------------------------------

Write-Step "Storing Anthropic API key..."

$UpstreamKeyFile = Join-Path $KiriData "upstream.key"
New-Item -ItemType Directory -Path $KiriData -Force | Out-Null

if (Test-Path $UpstreamKeyFile) {
    Write-Ok "Key file already present -- skipping (delete $UpstreamKeyFile to replace)"
} else {
    if ($AnthropicKey -eq "") {
        Write-Host ""
        Write-Host "      Your Anthropic key is stored only inside the Docker container" -ForegroundColor Yellow
        Write-Host "      as a secret. It never appears in logs, env dumps, or" -ForegroundColor Yellow
        Write-Host "      docker inspect output." -ForegroundColor Yellow
        Write-Host ""
        $AnthropicKey = Read-Host "      Anthropic API key (sk-ant-...)"
        Write-Host ""
    }
    if (-not $AnthropicKey.StartsWith("sk-ant-")) {
        Fail "Key does not look like an Anthropic key (expected sk-ant-...). Re-run with the correct key."
    }
    # Write without trailing newline -- Docker secrets are strict about trailing whitespace
    [System.IO.File]::WriteAllText($UpstreamKeyFile, $AnthropicKey)
    Write-Ok "Key stored at $UpstreamKeyFile"
}

# -- Step 3: Build ------------------------------------------------------------

if (-not $SkipBuild) {
    Write-Step "Building Docker image (first run: ~3-5 min)..."
    Push-Location $KiriDir
    try {
        docker compose build
        if ($LASTEXITCODE -ne 0) { Fail "docker compose build failed. See output above." }
    } finally {
        Pop-Location
    }
    Write-Ok "Image built"
} else {
    Write-Step "Skipping build (-SkipBuild)"
    Write-Ok "Using existing image"
}

# -- Step 4: Start stack ------------------------------------------------------

Write-Step "Starting Kiri stack..."
Write-Info "First run downloads the Ollama model (~2 GB) -- this can take 5-30 minutes."

Push-Location $KiriDir
try {
    docker compose up -d
    if ($LASTEXITCODE -ne 0) { Fail "docker compose up -d failed. See output above." }
} finally {
    Pop-Location
}
Write-Ok "Stack started"

# -- Step 5: Health check -----------------------------------------------------

Write-Step "Waiting for gateway health (up to 10 min for model download)..."

if (-not (Wait-ForGateway -TimeoutSeconds 600)) {
    Write-Warn "Gateway did not become healthy within 10 minutes."
    Write-Warn "The model may still be downloading. Check progress with:"
    Write-Host ""
    Write-Host "      docker compose --project-directory `"$KiriDir`" logs ollama-pull -f" -ForegroundColor DarkGray
    Write-Host ""
    Write-Warn "Re-run this installer once the model is ready."
    exit 1
}
Write-Ok "Gateway healthy at http://localhost:8765"

# -- Step 6: Developer key ----------------------------------------------------

Write-Step "Generating your Kiri developer key..."

Push-Location $KiriDir
try {
    $rawOutput = docker compose exec kiri kiri key create 2>&1
    $KiriKey   = ($rawOutput | Select-Object -Last 1).ToString().Trim()
} finally {
    Pop-Location
}

if (-not $KiriKey.StartsWith("kr-")) {
    Fail "Key creation failed. Output: $rawOutput"
}
Write-Ok "Key created: $KiriKey"

# -- Step 7: Environment variable ---------------------------------------------

Write-Step "Setting ANTHROPIC_BASE_URL in user environment..."

[System.Environment]::SetEnvironmentVariable(
    "ANTHROPIC_BASE_URL", "http://localhost:8765", "User"
)
$env:ANTHROPIC_BASE_URL = "http://localhost:8765"
Write-Ok "ANTHROPIC_BASE_URL=http://localhost:8765 written to user registry"
Write-Info "New processes will pick this up automatically. Restart open terminals."

# -- Step 8: Scheduled Task ---------------------------------------------------

Write-Step "Configuring autostart at login (Scheduled Task)..."

$TaskName = "KiriGateway"
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Info "Removed existing task -- re-creating"
}

$action = New-ScheduledTaskAction `
    -Execute          "docker.exe" `
    -Argument         "compose --project-directory `"$KiriDir`" up -d" `
    -WorkingDirectory $KiriDir

$trigger = New-ScheduledTaskTrigger -AtLogon -User $env:USERNAME

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal `
    -UserId    $env:USERNAME `
    -LogonType Interactive `
    -RunLevel  Highest

Register-ScheduledTask `
    -TaskName    $TaskName `
    -Action      $action `
    -Trigger     $trigger `
    -Settings    $settings `
    -Principal   $principal `
    -Description "Starts the Kiri gateway Docker stack at user login" `
    -Force | Out-Null

Write-Ok "Scheduled Task '$TaskName' created -- auto-starts at next login"

# -- Step 9: CLI wrapper ------------------------------------------------------

Write-Step "Installing kiri CLI wrapper..."

New-Item -ItemType Directory -Path $WrapperDir -Force | Out-Null

# The wrapper delegates all kiri commands into the running container.
# Variables prefixed with backtick-dollar are literal in the output file;
# $KiriDir is expanded now (installer bakes the repo path in).
$wrapperContent = @"
# kiri.ps1 -- generated by the Kiri installer. Do not edit manually.
`$kiriDir = "$KiriDir"
`$compose = "compose --project-directory ``"``$kiriDir``""
`$running = docker compose --project-directory "``$kiriDir" ps --services --filter status=running 2>`$null |
    Select-String "^kiri`$"
if (-not `$running) {
    Write-Error "Kiri gateway is not running. Start it with: docker compose --project-directory '``$kiriDir' up -d"
    exit 1
}
docker compose --project-directory "``$kiriDir" exec kiri kiri @args
"@

Set-Content -Path $WrapperPath -Value $wrapperContent -Encoding UTF8

# Add wrapper dir to user PATH if missing
$userPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*$WrapperDir*") {
    [System.Environment]::SetEnvironmentVariable("PATH", "$WrapperDir;$userPath", "User")
    $env:PATH = "$WrapperDir;$env:PATH"
    Write-Ok "Added $WrapperDir to user PATH"
} else {
    Write-Ok "PATH already contains $WrapperDir"
}
Write-Ok "kiri wrapper installed at $WrapperPath"

# --------------------------------------------------------------------------- #
# Done
# --------------------------------------------------------------------------- #

Write-Host ""
Write-Host "  ==================================" -ForegroundColor Green
Write-Host "  Kiri installed successfully!" -ForegroundColor Green
Write-Host "  ==================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Gateway :  http://localhost:8765" -ForegroundColor White
Write-Host "  Your key:  $KiriKey"             -ForegroundColor White
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  1. Set ANTHROPIC_API_KEY to your Kiri key (not the Anthropic key):" -ForegroundColor Yellow
Write-Host "     Open a new terminal and run:" -ForegroundColor DarkGray
Write-Host "     [Environment]::SetEnvironmentVariable('ANTHROPIC_API_KEY','$KiriKey','User')" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  2. Restart open terminals to pick up ANTHROPIC_BASE_URL." -ForegroundColor Yellow
Write-Host ""
Write-Host "  3. Add your first protection:" -ForegroundColor Yellow
Write-Host "     kiri add @MyClass" -ForegroundColor DarkGray
Write-Host "     kiri add src\engine\core.py" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Useful commands:" -ForegroundColor DarkGray
Write-Host "     kiri status                    -- what is protected" -ForegroundColor DarkGray
Write-Host "     kiri inspect ""explain MyClass"" -- test a prompt" -ForegroundColor DarkGray
Write-Host "     kiri log --tail 20             -- recent decisions" -ForegroundColor DarkGray
Write-Host ""
