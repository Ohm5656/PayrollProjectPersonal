param(
    [Parameter(Mandatory=$true)][string]$ArtifactPath,
    [switch]$RequireTrustedSignature
)

$ErrorActionPreference = 'Stop'

function Get-ShippedNativeBinary {
    param([System.IO.FileInfo]$Item)
    return $Item.Extension -in '.exe', '.dll', '.pyd'
}

$artifact = Get-Item -LiteralPath $ArtifactPath -ErrorAction Stop
if ($artifact.PSIsContainer) {
    $binaries = @(
        Get-ChildItem -LiteralPath $artifact.FullName -File -Recurse |
            Where-Object { Get-ShippedNativeBinary $_ } |
            Sort-Object FullName
    )
} elseif (Get-ShippedNativeBinary $artifact) {
    $binaries = @($artifact)
} else {
    throw 'ArtifactPath must be a shipped .exe, .dll, .pyd, or a directory containing them'
}

if ($binaries.Count -eq 0) {
    throw 'No shipped native binaries were found for signature verification'
}

$results = @(
    foreach ($binary in $binaries) {
        $signature = Get-AuthenticodeSignature -LiteralPath $binary.FullName
        $signer = $signature.SignerCertificate
        $timestamp = $signature.TimeStamperCertificate
        $trusted = ($signature.Status -eq 'Valid' -and $null -ne $signer -and $null -ne $timestamp)
        [pscustomobject]@{
            path = $binary.FullName
            bytes = $binary.Length
            sha256 = (Get-FileHash -LiteralPath $binary.FullName -Algorithm SHA256).Hash
            signature_status = $signature.Status.ToString()
            signature_type = $signature.SignatureType.ToString()
            signer_subject = if ($signer) { $signer.Subject } else { $null }
            signer_thumbprint = if ($signer) { $signer.Thumbprint } else { $null }
            timestamp_subject = if ($timestamp) { $timestamp.Subject } else { $null }
            timestamp_thumbprint = if ($timestamp) { $timestamp.Thumbprint } else { $null }
            trusted = $trusted
        }
    }
)

$evidence = [pscustomobject]@{
    artifact = $artifact.FullName
    require_trusted_signature = [bool]$RequireTrustedSignature
    all_trusted = [bool]($results | ForEach-Object { $_.trusted } | Where-Object { -not $_ } | Measure-Object).Count -eq 0
    files = $results
}
$evidence | ConvertTo-Json -Depth 4

if ($RequireTrustedSignature -and -not $evidence.all_trusted) {
    throw 'Trusted release verification failed: every shipped native binary must have a valid Authenticode signature and RFC 3161 timestamp'
}
