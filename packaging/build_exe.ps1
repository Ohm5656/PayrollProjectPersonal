$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
& $python -m PyInstaller --version
$dist = Join-Path $root 'dist'
$work = Join-Path $root 'build\pyinstaller'
& $python -m PyInstaller --noconfirm --clean --distpath $dist --workpath $work (Join-Path $PSScriptRoot 'ntp_payroll.spec')
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& (Join-Path $PSScriptRoot 'verify_exe.ps1') (Join-Path $dist 'NTP Payroll Assistant - Test Candidate\NTP Payroll Assistant - Test Candidate.exe')
