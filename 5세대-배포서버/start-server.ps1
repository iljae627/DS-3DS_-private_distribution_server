[CmdletBinding()]
param(
    [string]$HotspotIp = "192.168.137.1"
)

$ErrorActionPreference = "Stop"
$projectPath = $PSScriptRoot
$sharedPath = Join-Path $projectPath "..\4세대-배포"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Windows 핫스팟 DNS를 설정하려면 관리자 PowerShell에서 실행해야 합니다."
}

$hotspotAddress = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -eq $HotspotIp } |
    Select-Object -First 1
if (-not $hotspotAddress) {
    throw "Windows 모바일 핫스팟 주소 $HotspotIp을 찾지 못했습니다. 먼저 핫스팟을 켜세요."
}

$python = Join-Path $sharedPath ".venv\Scripts\python.exe"
$chain = Join-Path $sharedPath "certs\server-chain.crt"
$key = Join-Path $sharedPath "certs\server.key"
foreach ($required in @($python, $chain, $key)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "4세대 서버의 공통 실행 파일을 찾지 못했습니다: $required" }
}

foreach ($rule in @(
    @{ Name = "PokemonGen5-DLS-HTTP"; Display = "Pokemon Gen5 DLS HTTP"; Port = 80 },
    @{ Name = "PokemonGen5-DLS-HTTPS"; Display = "Pokemon Gen5 DLS HTTPS"; Port = 443 }
)) {
    if (-not (Get-NetFirewallRule -Name $rule.Name -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -Name $rule.Name -DisplayName $rule.Display `
            -Direction Inbound -Action Allow -Protocol TCP -LocalPort $rule.Port | Out-Null
    } else {
        Enable-NetFirewallRule -Name $rule.Name
    }
}

Write-Host "5세대 배포 서버를 시작합니다." -ForegroundColor Cyan
Write-Host "DS 기본/보조 DNS: $HotspotIp" -ForegroundColor Yellow
Write-Host "배포파일 폴더의 PGF를 자동으로 검색합니다." -ForegroundColor Green
Write-Host "종료: Ctrl+C"

Push-Location $projectPath
try {
    & $python .\windows_server.py --hotspot-ip $HotspotIp --gift-dir ".\배포파일" `
        --cert-chain $chain --private-key $key --log-file .\diagnostics.log
    if ($LASTEXITCODE -ne 0) {
        throw "5세대 배포 서버가 오류 코드 $LASTEXITCODE(으)로 종료됐습니다. diagnostics.log를 확인하세요."
    }
} finally {
    Pop-Location
}

