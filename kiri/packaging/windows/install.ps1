# Kiri Windows Service installer — run as Administrator
#
# Usage:
#   .\install.ps1                        # install with defaults
#   .\install.ps1 -Uninstall             # remove service and kiri user
#   .\install.ps1 -Port 9000             # custom port
param(
    [switch]$Uninstall,
    [int]$Port = 8765,
    [string]$KiriExe = "C:\Program Files\Kiri\kiri.exe",
    [string]$DataDir = "C:\ProgramData\Kiri"
)

$ServiceName = "Kiri"
$ServiceUser = "NT SERVICE\Kiri"

if ($Uninstall) {
    Stop-Service $ServiceName -ErrorAction SilentlyContinue
    sc.exe delete $ServiceName | Out-Null
    Write-Host "Kiri service removed." -ForegroundColor Green
    exit 0
}

# Create data directory
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
New-Item -ItemType Directory -Force -Path "$DataDir\models" | Out-Null
New-Item -ItemType Directory -Force -Path "$DataDir\keys" | Out-Null

# Prompt for upstream key and store with restricted ACL
$key = Read-Host "Enter upstream Anthropic key (sk-ant-...)" -AsSecureString
$bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($key)
$plain = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
$plain | Out-File "$DataDir\upstream.key" -Encoding ascii -NoNewline

# Restrict upstream.key to SYSTEM + Administrators only
$acl = Get-Acl "$DataDir\upstream.key"
$acl.SetAccessRuleProtection($true, $false)
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    "BUILTIN\Administrators", "FullControl", "Allow"
)
$acl.AddAccessRule($rule)
Set-Acl "$DataDir\upstream.key" $acl

# Register Windows Service
$params = @{
    Name        = $ServiceName
    BinaryPathName = "`"$KiriExe`" serve --port $Port --data-dir `"$DataDir`""
    DisplayName = "Kiri AI Gateway"
    StartupType = "Automatic"
    Description = "Intercepts LLM calls and prevents proprietary source code from leaving the network."
}
New-Service @params | Out-Null
Start-Service $ServiceName

Write-Host "Kiri installed and running on port $Port." -ForegroundColor Green
Write-Host "Run 'kiri key create' to generate a developer key." -ForegroundColor Cyan
