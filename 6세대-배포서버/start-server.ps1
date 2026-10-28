param([string]$ServerIp = "", [string]$Select = "ask")
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ServerIp) { $ServerIp = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } | Sort-Object InterfaceMetric | Select-Object -First 1 -ExpandProperty IPAddress }
if (-not (Test-Path -LiteralPath (Join-Path $Root 'keys\aes_keys.txt'))) { throw "SD:/gm9/aes_keys.txt를 $Root\keys\aes_keys.txt 로 복사하세요." }
if (-not (Test-Path -LiteralPath (Join-Path $Root 'node_modules'))) { Push-Location $Root; try { npm install } finally { Pop-Location } }
# The certificate is local-only and regenerated so its SAN list always matches the server version.
python (Join-Path $Root 'make_certificate.py') | Out-Null
Write-Host "3DS 기본/보조 DNS에 입력할 주소: $ServerIp" -ForegroundColor Cyan
python (Join-Path $Root 'server.py') --ip $ServerIp --select $Select
