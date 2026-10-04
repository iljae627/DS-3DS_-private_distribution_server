#Requires -RunAsAdministrator
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$configPath = Join-Path $env:USERPROFILE ".wslconfig"
$configBackupPath = Join-Path $PSScriptRoot "wslconfig-backup.json"
$icsParameters = "HKLM:\SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters"
$backupPath = Join-Path $PSScriptRoot "ics-dns-backup.json"
$desired = @"
[wsl2]
networkingMode=nat
dnsTunneling=true
firewall=true
"@

if (-not (Test-Path -LiteralPath $configBackupPath)) {
    $configExisted = Test-Path -LiteralPath $configPath
    @{
        Existed = $configExisted
        Content = if ($configExisted) { Get-Content -Raw -LiteralPath $configPath } else { $null }
    } | ConvertTo-Json | Set-Content -LiteralPath $configBackupPath -Encoding utf8
}
Set-Content -LiteralPath $configPath -Value $desired -Encoding ascii

$creatorId = "{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}"

$rules = @(
    @{ Name = "PokemonGen4-DNS-UDP"; Display = "Pokemon Gen4 DNS UDP"; Protocol = "UDP"; Port = 53 },
    @{ Name = "PokemonGen4-DNS-TCP"; Display = "Pokemon Gen4 DNS TCP"; Protocol = "TCP"; Port = 53 },
    @{ Name = "PokemonGen4-DLS-HTTP"; Display = "Pokemon Gen4 DLS HTTP"; Protocol = "TCP"; Port = 80 }
)

foreach ($rule in $rules) {
    $hyperVRule = Get-NetFirewallHyperVRule -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq $rule.Name } |
        Select-Object -First 1
    if (-not $hyperVRule) {
        New-NetFirewallHyperVRule `
            -Name $rule.Name `
            -DisplayName $rule.Display `
            -Direction Inbound `
            -VMCreatorId $creatorId `
            -Protocol $rule.Protocol `
            -LocalPorts $rule.Port | Out-Null
    }

    $windowsRule = Get-NetFirewallRule -Name $rule.Name -ErrorAction SilentlyContinue
    if ($windowsRule) {
        Enable-NetFirewallRule -Name $rule.Name
    } else {
        New-NetFirewallRule `
            -Name $rule.Name `
            -DisplayName $rule.Display `
            -Direction Inbound `
            -Action Allow `
            -Protocol $rule.Protocol `
            -LocalPort $rule.Port | Out-Null
    }
}

if (Test-Path -LiteralPath $backupPath) {
    $backup = Get-Content -Raw -LiteralPath $backupPath | ConvertFrom-Json
    if ($backup.EnableDNSExisted) {
        New-ItemProperty -LiteralPath $icsParameters -Name "EnableDNS" -PropertyType DWord -Value ([int]$backup.EnableDNSValue) -Force | Out-Null
    } else {
        Remove-ItemProperty -LiteralPath $icsParameters -Name "EnableDNS" -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $backupPath
}

wsl.exe --shutdown
Write-Host "WSL NAT 네트워크와 DNS/HTTP 인바운드 규칙을 준비했습니다." -ForegroundColor Green
Write-Host "Windows ICS DNS와 충돌하지 않도록 WSL을 별도 IP로 분리했습니다." -ForegroundColor Green
Write-Host "이제 start-server.ps1을 실행하세요." -ForegroundColor Yellow
Write-Host "원래 설정 복원: .\restore-wsl-network.ps1"

