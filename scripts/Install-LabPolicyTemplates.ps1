[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SourceArchive,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{64}$')][string]$ArchiveSha256,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{40}$')][string]$SourceCommit,
    [ValidatePattern('^http://10\.0\.2\.2:55987/[A-Za-z0-9._-]+\.zip$')][string]$ArchiveUrl
)
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne 'MRNG-DC' -or -not (Test-Path C:\mrng-lab\ready.txt) -or
    (Get-ADDomain).DNSRoot -ne 'mrng.test') { throw 'Use the owned isolated domain controller.' }
if (-not (Test-Path -LiteralPath $SourceArchive) -and $ArchiveUrl) {
    New-Item -ItemType Directory -Path (Split-Path $SourceArchive -Parent) -Force | Out-Null
    Invoke-WebRequest -UseBasicParsing $ArchiveUrl -OutFile $SourceArchive
}
if ((Get-FileHash -LiteralPath $SourceArchive -Algorithm SHA256).Hash -ne $ArchiveSha256) { throw 'Source archive mismatch.' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$store = Join-Path $env:SystemRoot 'SYSVOL\sysvol\mrng.test\Policies\PolicyDefinitions'
$zip = [IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $SourceArchive).Path)
$files = [Collections.Generic.List[object]]::new()
try {
    foreach ($name in @('mRemoteNG.Security.admx', 'en-US/mRemoteNG.Security.adml', 'de-DE/mRemoteNG.Security.adml')) {
        $entry = $zip.GetEntry('policies/' + $name)
        if ($null -eq $entry) { throw "Missing pinned policy template: $name" }
        $reader = [IO.StreamReader]::new($entry.Open(), [Text.Encoding]::UTF8)
        try { $content = $reader.ReadToEnd() } finally { $reader.Dispose() }
        [xml]$document = $content
        if ($document.DocumentElement.LocalName -notin @('policyDefinitions', 'policyDefinitionResources')) {
            throw 'Unexpected policy template root.'
        }
        $target = Join-Path $store $name.Replace('/', '\')
        New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes($content)
        if (Test-Path -LiteralPath $target) {
            if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($target)) -ne [Convert]::ToBase64String($bytes)) {
                throw 'Refusing to replace an existing different policy template.'
            }
        } else {
            $stream = [IO.File]::Open($target, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
            try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
        }
        $files.Add([pscustomobject]@{ File = $name; Sha256 = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() })
    }
} finally { $zip.Dispose() }
$result = [pscustomobject]@{ Status = 'installed'; SourceCommit = $SourceCommit; ArchiveSha256 = $ArchiveSha256; CentralStore = $store; Files = $files }
$result | ConvertTo-Json -Depth 6 | Tee-Object -FilePath C:\mrng-lab\policy-templates.json
