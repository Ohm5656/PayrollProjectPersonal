param([Parameter(Mandatory=$true)][string]$ExePath)
$ErrorActionPreference = 'Stop'
if (!(Test-Path -LiteralPath $ExePath -PathType Leaf)) { throw 'EXE not found' }
Get-FileHash -Algorithm SHA256 -LiteralPath $ExePath
