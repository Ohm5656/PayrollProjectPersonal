$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$candidates = @(
    (Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
    'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    'C:\Program Files\Inno Setup 6\ISCC.exe',
    'C:\Program Files (x86)\Inno Setup\ISCC.exe',
    'C:\Program Files\Inno Setup\ISCC.exe'
) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
if (!$candidates) {
    throw 'Inno Setup Compiler (ISCC.exe) is unavailable. Install it only with explicit approval, then rerun this script.'
}

$build = & (Join-Path $PSScriptRoot 'build_exe.ps1')
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$distribution = ($build | Select-Object -Last 1 | ConvertFrom-Json).distribution
$result = & (Join-Path $PSScriptRoot 'prepare_installer_staging.ps1') -DistributionPath $distribution
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$stage = ($result | Select-Object -Last 1 | ConvertFrom-Json).stage
$output = Join-Path $root 'artifacts'
New-Item -ItemType Directory -Force -Path $output | Out-Null
& $candidates "/DSourceDir=$stage" "/DOutputDir=$output" (Join-Path $PSScriptRoot 'installer\ntp_payroll.iss')
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& (Join-Path $PSScriptRoot 'verify_installer.ps1') (Join-Path $output 'NTP-Payroll-Assistant-Test-Candidate-Setup.exe')
