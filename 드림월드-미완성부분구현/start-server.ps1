$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    Write-Host '[setup] Creating a local Python environment...'
    python -m venv (Join-Path $PSScriptRoot '.venv')
}

Write-Host '[setup] Checking Python packages...'
& $Python -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt') -r (Join-Path $PSScriptRoot 'game_sync_server\requirements.txt')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python (Join-Path $PSScriptRoot 'doctor.py')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python (Join-Path $PSScriptRoot 'launch.py') @args
exit $LASTEXITCODE
