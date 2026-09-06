param(
    [ValidateSet('start', 'stop')]
    [string]$Action = 'start'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir = Join-Path $projectRoot 'logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$etlPath = Join-Path $logDir 'ds_capture.etl'
$pcapPath = Join-Path $logDir 'ds_capture.pcapng'

if ($Action -eq 'start') {
    pktmon filter remove | Out-Null
    pktmon filter add DS-DNS -p 53 | Out-Null
    pktmon filter add DS-HTTP -p 80 | Out-Null
    pktmon start --capture --pkt-size 0 --file-name $etlPath
    Write-Host '캡처 중입니다. 끝낼 때: .\capture_packets.ps1 stop'
} else {
    pktmon stop
    pktmon etl2pcap $etlPath --out $pcapPath
    Write-Host "저장됨: $pcapPath"
}
