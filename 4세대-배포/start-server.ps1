[CmdletBinding()]
param(
    [string]$HotspotIp = "192.168.137.1"
)

$ErrorActionPreference = "Stop"
$projectPath = $PSScriptRoot

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

$python = Join-Path $projectPath ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "프로젝트 Python 환경을 찾지 못했습니다: $python"
}

foreach ($rule in @(
    @{ Name = "PokemonGen4-DLS-HTTP"; Display = "Pokemon Gen4 DLS HTTP"; Port = 80 },
    @{ Name = "PokemonGen4-DLS-HTTPS"; Display = "Pokemon Gen4 DLS HTTPS"; Port = 443 }
)) {
    if (-not (Get-NetFirewallRule -Name $rule.Name -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -Name $rule.Name -DisplayName $rule.Display `
            -Direction Inbound -Action Allow -Protocol TCP -LocalPort $rule.Port | Out-Null
    } else {
        Enable-NetFirewallRule -Name $rule.Name
    }
}

$bundle = Join-Path $projectPath "WII_NWC_1_CERT.p12"
$bundleHash = "3075D83C1AF02BEC6C45FEB370A5F6476D5BCCABEEC9AB2CFC89649562E0C11C"
if (-not (Test-Path -LiteralPath $bundle)) {
    Write-Host "DS HTTPS 인증서 묶음을 내려받습니다..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri "https://certs.larsenv.xyz/WII_NWC_1_CERT.p12" -OutFile $bundle
}
if ((Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash -ne $bundleHash) {
    throw "Wii NWC 인증서 묶음의 SHA-256 검증에 실패했습니다."
}

$chain = Join-Path $projectPath "certs\server-chain.crt"
$key = Join-Path $projectPath "certs\server.key"
if (-not (Test-Path -LiteralPath $chain) -or -not (Test-Path -LiteralPath $key)) {
    & $python .\prepare_ds_certificate.py --p12 $bundle --output .\certs
    if ($LASTEXITCODE -ne 0) { throw "DS HTTPS 인증서 생성에 실패했습니다." }
}

Write-Host "4세대 배포 서버를 시작합니다." -ForegroundColor Cyan
Write-Host "Windows 전용 모드 (WSL 미사용)" -ForegroundColor Green
Write-Host "DS 기본/보조 DNS: $HotspotIp" -ForegroundColor Yellow
Write-Host "로컬 DLS: HTTP 80 + DS SSLv3 HTTPS 443" -ForegroundColor Green
Write-Host "종료: Ctrl+C"

Push-Location $projectPath
try {
    & $python .\windows_server.py --hotspot-ip $HotspotIp --gift-dir ".\배포 목록" --log-file .\diagnostics.log
    if ($LASTEXITCODE -ne 0) {
        throw "Windows 배포 서버가 오류 코드 $LASTEXITCODE(으)로 종료됐습니다. diagnostics.log를 확인하세요."
    }
} finally {
    Pop-Location
}

