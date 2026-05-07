#Requires -Version 5.1
<#
.SYNOPSIS
    Kiri Gateway -- Windows installer

.DESCRIPTION
    Installs Kiri as a background service on Windows.

    What this script does:
      1. Verifies Docker Desktop is installed and running
      2. Stores your LLM provider key(s) as Docker secrets (never in git or logs)
      3. Builds the Docker image and starts the full stack (Kiri + Ollama)
      4. Asks which tools you use (Claude Code, Cursor, both) and sets the
         right environment variables in your user registry
      5. Creates a Scheduled Task so the stack restarts automatically at login
      6. Installs a kiri.ps1 wrapper on your PATH

    After installation your chosen tools route automatically through the gateway.

.PARAMETER AnthropicKey
    Anthropic API key (sk-ant-...). Prompted if omitted.

.PARAMETER OpenAIKey
    OpenAI API key (sk-...). Only prompted when you select Cursor/OpenAI tools.
    Skip with Enter if you only use Claude models via Cursor.

.PARAMETER SkipBuild
    Skip docker compose build (image already built).

.EXAMPLE
    .\install.ps1
    .\install.ps1 -AnthropicKey sk-ant-xxx
    .\install.ps1 -AnthropicKey sk-ant-xxx -OpenAIKey sk-xxx
    .\install.ps1 -SkipBuild

.NOTES
    No elevated prompt required.
    Docker Desktop must be installed: https://www.docker.com/products/docker-desktop/
#>

param(
    [string]$AnthropicKey = "",
    [string]$OpenAIKey    = "",
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

function Set-UserEnv([string]$Name, [string]$Value) {
    [System.Environment]::SetEnvironmentVariable($Name, $Value, "User")
    [System.Environment]::SetEnvironmentVariable($Name, $Value, "Process")
}

function Remove-UserEnv([string]$Name) {
    [System.Environment]::SetEnvironmentVariable($Name, $null, "User")
    [System.Environment]::SetEnvironmentVariable($Name, $null, "Process")
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
            Write-Info "still waiting... ${elapsed}s (model download can take 5-30 min on first run)"
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
    Fail "Docker not found. Install Docker Desktop: https://www.docker.com/products/docker-desktop/"
}
Write-Ok "docker CLI found"

if (-not (Test-DockerRunning)) {
    Fail "Docker daemon is not responding. Open Docker Desktop, wait for it to start, then re-run."
}
Write-Ok "Docker daemon is running"

# -- Step 2: Tool selection ---------------------------------------------------

Write-Step "Which tools do you want to route through Kiri?"
Write-Host ""
Write-Host "  [1] Claude Code                       (sets ANTHROPIC_BASE_URL)" -ForegroundColor White
Write-Host "  [2] Cursor / Windsurf / OpenAI tools  (sets OPENAI_BASE_URL)" -ForegroundColor White
Write-Host "  [3] Both" -ForegroundColor White
Write-Host "  [4] None -- I will configure my tools manually" -ForegroundColor DarkGray
Write-Host ""
$toolChoice = Read-Host "  Choice [1-4, default: 1]"
if ($toolChoice -eq "" -or $toolChoice -notmatch "^[1-4]$") { $toolChoice = "1" }

$configureClaude = $toolChoice -in "1","3"
$configureOpenAI = $toolChoice -in "2","3"

Write-Host ""
switch ($toolChoice) {
    "1" { Write-Ok "Claude Code selected" }
    "2" { Write-Ok "Cursor / OpenAI-compatible tools selected" }
    "3" { Write-Ok "Claude Code + Cursor / OpenAI-compatible tools selected" }
    "4" { Write-Ok "Manual configuration -- env vars will not be set" }
}

# -- Step 3: Upstream keys ----------------------------------------------------

Write-Step "Storing upstream API key(s)..."

New-Item -ItemType Directory -Path $KiriData -Force | Out-Null

# Anthropic key -- required when using Claude Code or when skipping manual setup
$AnthropicKeyFile = Join-Path $KiriData "upstream.key"
if (Test-Path $AnthropicKeyFile) {
    Write-Ok "Anthropic key already stored -- skipping (delete $AnthropicKeyFile to replace)"
} elseif ($configureClaude -or $toolChoice -eq "4") {
    # Always ask for Anthropic key unless user chose OpenAI-only
    if ($AnthropicKey -eq "") {
        Write-Host ""
        Write-Host "      Your key is stored only inside the Docker container as a secret." -ForegroundColor Yellow
        Write-Host "      It never appears in logs, env dumps, or docker inspect output." -ForegroundColor Yellow
        Write-Host ""
        $AnthropicKey = Read-Host "      Anthropic API key (sk-ant-...)"
        Write-Host ""
    }
    if (-not $AnthropicKey.StartsWith("sk-ant-")) {
        Fail "Expected an Anthropic key (sk-ant-...). Re-run with the correct key."
    }
    [System.IO.File]::WriteAllText($AnthropicKeyFile, $AnthropicKey)
    Write-Ok "Anthropic key stored at $AnthropicKeyFile"
}

# OpenAI key -- optional, only for OpenAI-compatible upstream calls
$OpenAIKeyFile = Join-Path $KiriData "openai.key"
if ($configureOpenAI) {
    if (Test-Path $OpenAIKeyFile) {
        Write-Ok "OpenAI key already stored -- skipping (delete $OpenAIKeyFile to replace)"
    } else {
        if ($OpenAIKey -eq "") {
            Write-Host ""
            Write-Host "      OpenAI upstream key -- needed only if you use GPT models via Cursor." -ForegroundColor Yellow
            Write-Host "      Press Enter to skip if you only use Claude models." -ForegroundColor Yellow
            Write-Host ""
            $OpenAIKey = Read-Host "      OpenAI API key (sk-..., or Enter to skip)"
            Write-Host ""
        }
        if ($OpenAIKey -ne "") {
            [System.IO.File]::WriteAllText($OpenAIKeyFile, $OpenAIKey)
            Write-Ok "OpenAI key stored at $OpenAIKeyFile"
        } else {
            Write-Info "No OpenAI key stored -- GPT model calls via Cursor will use the Anthropic key fallback"
        }
    }
}

# -- Step 4: Update docker-compose for openai_key secret if needed -----------

if ($configureOpenAI -and (Test-Path $OpenAIKeyFile)) {
    # Patch docker-compose.yml to add openai_key secret if not already present
    $composePath = Join-Path $KiriDir "docker-compose.yml"
    $composeText = Get-Content $composePath -Raw
    if ($composeText -notmatch "openai_key") {
        $patchedText = $composeText -replace `
            "(secrets:\s*\n  anthropic_key:\s*\n    file: \.kiri/upstream\.key)", `
            "`$1`n  openai_key:`n    file: .kiri/openai.key"
        Set-Content -Path $composePath -Value $patchedText -Encoding UTF8
        Write-Ok "docker-compose.yml updated with openai_key secret"
    } else {
        Write-Ok "docker-compose.yml already has openai_key secret"
    }
}

# -- Step 5: Build ------------------------------------------------------------

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

# -- Step 6: Start stack ------------------------------------------------------

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

# -- Step 7: Health check -----------------------------------------------------

Write-Step "Waiting for gateway health (up to 10 min for model download)..."

if (-not (Wait-ForGateway -TimeoutSeconds 600)) {
    Write-Warn "Gateway did not become healthy within 10 minutes."
    Write-Warn "The model may still be downloading. Check:"
    Write-Host ""
    Write-Host "      docker compose --project-directory `"$KiriDir`" logs ollama-pull -f" -ForegroundColor DarkGray
    Write-Host ""
    Write-Warn "Re-run this installer once the model is ready."
    exit 1
}
Write-Ok "Gateway healthy at http://localhost:8765"

# -- Step 8: Developer key ----------------------------------------------------

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
Write-Ok "Key: $KiriKey"

# -- Step 9: Environment variables --------------------------------------------

Write-Step "Setting environment variables..."

if ($configureClaude) {
    Set-UserEnv "ANTHROPIC_BASE_URL" "http://localhost:8765"
    Write-Ok "ANTHROPIC_BASE_URL=http://localhost:8765"
}

if ($configureOpenAI) {
    Set-UserEnv "OPENAI_BASE_URL"  "http://localhost:8765"
    Set-UserEnv "OPENAI_API_BASE"  "http://localhost:8765"   # older SDK / LangChain
    Write-Ok "OPENAI_BASE_URL=http://localhost:8765"
    Write-Ok "OPENAI_API_BASE=http://localhost:8765 (older SDK / LangChain compat)"
}

if (-not $configureClaude -and -not $configureOpenAI) {
    Write-Info "No env vars set (manual configuration chosen)"
}

Write-Info "New processes pick these up automatically. Restart open terminals."

# -- Step 10: Scheduled Task --------------------------------------------------

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

$trigger  = New-ScheduledTaskTrigger -AtLogon -User $env:USERNAME
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

# -- Step 11: CLI wrapper -----------------------------------------------------

Write-Step "Installing kiri CLI wrapper..."

New-Item -ItemType Directory -Path $WrapperDir -Force | Out-Null

$wrapperContent = @"
# kiri.ps1 -- generated by Kiri installer. Do not edit manually.
`$kiriDir = "$KiriDir"
`$running = docker compose --project-directory "``$kiriDir" ps --services --filter status=running 2>`$null |
    Select-String "^kiri`$"
if (-not `$running) {
    Write-Error "Kiri gateway is not running. Start it with: docker compose --project-directory '``$kiriDir' up -d"
    exit 1
}
docker compose --project-directory "``$kiriDir" exec kiri kiri @args
"@

Set-Content -Path $WrapperPath -Value $wrapperContent -Encoding UTF8

$userPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*$WrapperDir*") {
    Set-UserEnv "PATH" "$WrapperDir;$userPath"
    Write-Ok "Added $WrapperDir to PATH"
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

# Tool-specific next steps
Write-Host "  Next steps:" -ForegroundColor Yellow
Write-Host ""

if ($configureClaude) {
    Write-Host "  Claude Code" -ForegroundColor Cyan
    Write-Host "  -----------" -ForegroundColor DarkGray
    Write-Host "  Set ANTHROPIC_API_KEY to your Kiri key (not the Anthropic key):" -ForegroundColor White
    Write-Host "  [Environment]::SetEnvironmentVariable('ANTHROPIC_API_KEY','$KiriKey','User')" -ForegroundColor DarkGray
    Write-Host ""
}

if ($configureOpenAI) {
    Write-Host "  Cursor / Windsurf" -ForegroundColor Cyan
    Write-Host "  -----------------" -ForegroundColor DarkGray
    Write-Host "  1. Open Settings" -ForegroundColor White
    Write-Host "  2. Search for 'OpenAI API Key' or 'Model provider'" -ForegroundColor White
    Write-Host "  3. Set API Key to: $KiriKey" -ForegroundColor White
    Write-Host "  4. Set Base URL to: http://localhost:8765" -ForegroundColor White
    Write-Host ""
    Write-Host "  OPENAI_BASE_URL and OPENAI_API_BASE are already set in your registry." -ForegroundColor DarkGray
    Write-Host "  Restart Cursor / Windsurf to pick them up." -ForegroundColor DarkGray
    Write-Host ""
}

if (-not $configureClaude -and -not $configureOpenAI) {
    Write-Host "  You chose manual configuration. Point your tool at:" -ForegroundColor White
    Write-Host "  Base URL : http://localhost:8765" -ForegroundColor DarkGray
    Write-Host "  API key  : $KiriKey" -ForegroundColor DarkGray
    Write-Host ""
}

Write-Host "  Common commands:" -ForegroundColor DarkGray
Write-Host "     kiri add @MyClass       -- protect a symbol" -ForegroundColor DarkGray
Write-Host "     kiri status             -- show what is protected" -ForegroundColor DarkGray
Write-Host "     kiri log --tail 20      -- recent decisions" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  To uninstall: .\install\windows\uninstall.ps1" -ForegroundColor DarkGray
Write-Host ""
