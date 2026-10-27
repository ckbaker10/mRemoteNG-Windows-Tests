$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$path = 'C:\mrng-lab\vs_BuildTools.exe'
$file = Get-Item -LiteralPath $path
$signature = Get-AuthenticodeSignature -LiteralPath $path
$stream = [IO.File]::OpenRead($path)
try { $magic = '{0:X2}{1:X2}' -f $stream.ReadByte(), $stream.ReadByte() } finally { $stream.Dispose() }
[pscustomobject]@{
    Bytes = $file.Length
    Header = $magic
    Sha256 = (Get-FileHash $path -Algorithm SHA256).Hash
    SignatureStatus = $signature.Status.ToString()
    SignatureMessage = $signature.StatusMessage
    SignerSubject = $signature.SignerCertificate.Subject
    SignerThumbprint = $signature.SignerCertificate.Thumbprint
} | ConvertTo-Json
