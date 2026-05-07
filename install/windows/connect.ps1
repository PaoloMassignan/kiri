#Requires -Version 5.1
<#
.SYNOPSIS
    Kiri Gateway -- team developer connector

.DESCRIPTION
    Configures your machine to route LLM traffic through a shared Kiri gateway
    that your team admin has already set up.

    What this script does:
      1. Asks for the gateway URL and your personal kr- key
      2. Verifies the gateway is reachable
      3. Asks which tools you use and sets the right environment variables

    No Docker required. No admin rights required.

.PARAMETER GatewayUrl
    URL of the shared gateway, e.g. http://kiri.internal:8765

.PARAMETER KiriKey
    Your personal kr- key (issued by your team admin).

.EXAMPLE
    .\connect.ps1
    .\connect.ps1 -GatewayUrl http://kiri.internal:8765 -KiriKey kr-abc...
#>

param(
    [string]$GatewayUrl = "",
    [string]$KiriKey    = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# --------------------------------------------------------------------------- #
# Output helpers
# --------------------------------------------------------------------------- #

function Write-Banner {
    Write-Host ""
    Write-Host "  Kiri Gateway - Connect to team gateway" -ForegroundColor White
    Write-Host "  =======================================" -ForegroundColor DarkGray
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

function Set-UserEnv([string]$Name, [string]$Value) {
    [System.Environment]::SetEnvironmentVariable($Name, $Value, "User")
    [System.Environment]::SetEnvironmentVariable($Name, $Value, "Process")
}

# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

Write-Banner

# -- Step 1: Gateway URL ------------------------------------------------------

Write-Step "Gateway URL..."

if ($GatewayUrl -eq "") {
    Write-Host "      Your admin should have given you the gateway address." -ForegroundColor Yellow
    Write-Host ""
    $GatewayUrl = Read-Host "      Gateway URL (e.g. http://kiri.internal:8765)"
    Write-Host ""
}

$GatewayUrl = $GatewayUrl.TrimEnd("/")

if ($GatewayUrl -notmatch "^https?://") {
    Fail "URL must start with http:// or https://  Got: '$GatewayUrl'"
}

Write-Ok "Gateway: $GatewayUrl"

# -- Step 2: Kiri key ---------------------------------------------------------

Write-Step "Your Kiri key..."

if ($KiriKey -eq "") {
    Write-Host "      Your admin issues personal kr- keys. Ask them if you don't have one." -ForegroundColor Yellow
    Write-Host ""
    $KiriKey = Read-Host "      Kiri key (kr-...)"
    Write-Host ""
}

if (-not $KiriKey.StartsWith("kr-")) {
    Fail "Expected a Kiri key starting with kr-  Got: '$KiriKey'"
}

Write-Ok "Key: $KiriKey"

# -- Step 3: Verify connectivity ----------------------------------------------

Write-Step "Verifying gateway connectivity..."

try {
    $r = Invoke-WebRequest "$GatewayUrl/health" `
             -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
    if ($r.StatusCode -eq 200) {
        Write-Ok "Gateway responded: HTTP $($r.StatusCode)"
    } else {
        Write-Warn "Gateway returned HTTP $($r.StatusCode) -- check the URL and try again"
        exit 1
    }
} catch {
    Fail "Could not reach $GatewayUrl/health -- is the gateway running? Error: $_"
}

# -- Step 4: Tool selection ---------------------------------------------------

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

# -- Step 5: Environment variables --------------------------------------------

Write-Step "Setting environment variables..."

if ($configureClaude) {
    Set-UserEnv "ANTHROPIC_BASE_URL" $GatewayUrl
    Write-Ok "ANTHROPIC_BASE_URL=$GatewayUrl"
}

if ($configureOpenAI) {
    Set-UserEnv "OPENAI_BASE_URL" $GatewayUrl
    Set-UserEnv "OPENAI_API_BASE" $GatewayUrl    # older SDK / LangChain
    Write-Ok "OPENAI_BASE_URL=$GatewayUrl"
    Write-Ok "OPENAI_API_BASE=$GatewayUrl (older SDK / LangChain compat)"
}

if (-not $configureClaude -and -not $configureOpenAI) {
    Write-Info "No env vars set (manual configuration chosen)"
}

Write-Info "New processes pick these up automatically. Restart open terminals."

# --------------------------------------------------------------------------- #
# Done
# --------------------------------------------------------------------------- #

Write-Host ""
Write-Host "  =======================================" -ForegroundColor Green
Write-Host "  Connected to Kiri gateway!" -ForegroundColor Green
Write-Host "  =======================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Gateway :  $GatewayUrl" -ForegroundColor White
Write-Host "  Your key:  $KiriKey"    -ForegroundColor White
Write-Host ""

Write-Host "  Next steps:" -ForegroundColor Yellow
Write-Host ""

if ($configureClaude) {
    Write-Host "  Claude Code" -ForegroundColor Cyan
    Write-Host "  -----------" -ForegroundColor DarkGray
    Write-Host "  Set ANTHROPIC_API_KEY to your Kiri key:" -ForegroundColor White
    Write-Host "  [Environment]::SetEnvironmentVariable('ANTHROPIC_API_KEY','$KiriKey','User')" -ForegroundColor DarkGray
    Write-Host ""
}

if ($configureOpenAI) {
    Write-Host "  Cursor / Windsurf" -ForegroundColor Cyan
    Write-Host "  -----------------" -ForegroundColor DarkGray
    Write-Host "  1. Open Settings" -ForegroundColor White
    Write-Host "  2. Search for 'OpenAI API Key' or 'Model provider'" -ForegroundColor White
    Write-Host "  3. Set API Key to: $KiriKey" -ForegroundColor White
    Write-Host "  4. Set Base URL to: $GatewayUrl" -ForegroundColor White
    Write-Host ""
    Write-Host "  OPENAI_BASE_URL and OPENAI_API_BASE are already set in your registry." -ForegroundColor DarkGray
    Write-Host "  Restart Cursor / Windsurf to pick them up." -ForegroundColor DarkGray
    Write-Host ""
}

if (-not $configureClaude -and -not $configureOpenAI) {
    Write-Host "  Point your tool at:" -ForegroundColor White
    Write-Host "  Base URL : $GatewayUrl" -ForegroundColor DarkGray
    Write-Host "  API key  : $KiriKey" -ForegroundColor DarkGray
    Write-Host ""
}

Write-Host "  To disconnect: .\install\windows\uninstall.ps1" -ForegroundColor DarkGray
Write-Host ""
