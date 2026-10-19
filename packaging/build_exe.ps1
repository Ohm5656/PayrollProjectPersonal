param([string]$OutputRoot)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (!$OutputRoot) {
    $OutputRoot = Join-Path $root (Join-Path 'dist' ('build-' + [guid]::NewGuid().ToString('N')))
}
if (Test-Path -LiteralPath $OutputRoot) { throw 'Refusing to overwrite an existing EXE output directory' }
& $python -m PyInstaller --version
$work = Join-Path $root 'build\pyinstaller'
& $python -m PyInstaller --noconfirm --clean --distpath $OutputRoot --workpath $work (Join-Path $PSScriptRoot 'ntp_payroll.spec')
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$distribution = Join-Path $OutputRoot 'NTP Payroll Assistant - Test Candidate'
$exe = Join-Path $distribution 'NTP Payroll Assistant - Test Candidate.exe'
& (Join-Path $PSScriptRoot 'verify_exe.ps1') $exe
if ($LASTEXITCODE) { exit $LASTEXITCODE }
[pscustomobject]@{ distribution = $distribution; exe = $exe } | ConvertTo-Json -Compress
