$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
& $python -m PyInstaller --version
& $python -m PyInstaller --noconfirm --clean (Join-Path $PSScriptRoot 'ntp_payroll.spec')
if ($LASTEXITCODE) { exit $LASTEXITCODE }
