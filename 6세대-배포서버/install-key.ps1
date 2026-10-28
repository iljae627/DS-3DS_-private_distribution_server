$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Add-Type -AssemblyName System.Windows.Forms
$Dialog = New-Object System.Windows.Forms.OpenFileDialog
$Dialog.Title = "GodMode9에서 생성한 aes_keys.txt 선택"
$Dialog.Filter = "AES keys (aes_keys.txt)|aes_keys.txt|Text files (*.txt)|*.txt"
if ($Dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
    Write-Host "취소했습니다."
    exit 1
}
$Text = Get-Content -LiteralPath $Dialog.FileName -Raw
if ($Text -notmatch '(?im)^\s*slot0x38KeyN\s*=\s*[0-9a-f]{32}\s*$') {
    throw "선택한 파일에 유효한 slot0x38KeyN 항목이 없습니다."
}
$KeyDir = Join-Path $Root 'keys'
New-Item -ItemType Directory -Path $KeyDir -Force | Out-Null
Copy-Item -LiteralPath $Dialog.FileName -Destination (Join-Path $KeyDir 'aes_keys.txt') -Force
Write-Host "키 파일을 비공개 로컬 폴더에 설치했습니다." -ForegroundColor Green
