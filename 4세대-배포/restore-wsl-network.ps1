#Requires -RunAsAdministrator
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$icsParameters = "HKLM:\SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters"
$backupPath = Join-Path $PSScriptRoot "ics-dns-backup.json"
$configPath = Join-Path $env:USERPROFILE ".wslconfig"
$configBackupPath = Join-Path $PSScriptRoot "wslconfig-backup.json"

if (Test-Path -LiteralPath $backupPath) {
    $backup = Get-Content -Raw -LiteralPath $backupPath | ConvertFrom-Json
    if ($backup.EnableDNSExisted) {
        New-ItemProperty -LiteralPath $icsParameters -Name "EnableDNS" -PropertyType DWord -Value ([int]$backup.EnableDNSValue) -Force | Out-Null
    } else {
        Remove-ItemProperty -LiteralPath $icsParameters -Name "EnableDNS" -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $backupPath
}

if (Test-Path -LiteralPath $configBackupPath) {
    $configBackup = Get-Content -Raw -LiteralPath $configBackupPath | ConvertFrom-Json
    if ($configBackup.Existed) {
        Set-Content -LiteralPath $configPath -Value $configBackup.Content -Encoding utf8 -NoNewline
    } else {
        Remove-Item -LiteralPath $configPath -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $configBackupPath
}

foreach ($name in @("PokemonGen4-DNS-UDP", "PokemonGen4-DNS-TCP", "PokemonGen4-DLS-HTTP")) {
    Remove-NetFirewallHyperVRule -Name $name -ErrorAction SilentlyContinue
    Remove-NetFirewallRule -Name $name -ErrorAction SilentlyContinue
}

wsl.exe --shutdown
Write-Host "ICS DNS와 방화벽 설정을 원래대로 복원했습니다." -ForegroundColor Green
Write-Host "WSL을 다시 시작하면 복원이 완료됩니다." -ForegroundColor Yellow
