param(
    [Parameter(Mandatory=$true)][string]$ExePath,
    [switch]$RequireTrustedSignature
)
$ErrorActionPreference = 'Stop'
if (!(Test-Path -LiteralPath $ExePath -PathType Leaf)) { throw 'EXE not found' }
Get-FileHash -Algorithm SHA256 -LiteralPath $ExePath
& (Join-Path $PSScriptRoot 'verify_signatures.ps1') -ArtifactPath $ExePath -RequireTrustedSignature:$RequireTrustedSignature
if ($LASTEXITCODE) { exit $LASTEXITCODE }
