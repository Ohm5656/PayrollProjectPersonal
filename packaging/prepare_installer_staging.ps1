param([Parameter(Mandatory=$true)][string]$DistributionPath)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
& $python -m app.packaging_safety --project-root $root --distribution-path $DistributionPath
if ($LASTEXITCODE) { exit $LASTEXITCODE }
