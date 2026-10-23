param(
    [Parameter(Mandatory=$true)][string]$InstallerPath,
    [switch]$RequireTrustedSignature
)
$ErrorActionPreference = 'Stop'
if (!(Test-Path -LiteralPath $InstallerPath -PathType Leaf)) { throw 'Installer not found' }
Get-Item -LiteralPath $InstallerPath | Select-Object FullName,Length,LastWriteTime
Get-FileHash -Algorithm SHA256 -LiteralPath $InstallerPath
& (Join-Path $PSScriptRoot 'verify_signatures.ps1') -ArtifactPath $InstallerPath -RequireTrustedSignature:$RequireTrustedSignature
if ($LASTEXITCODE) { exit $LASTEXITCODE }
