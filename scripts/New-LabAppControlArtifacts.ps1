[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SourceRoot,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{40}$')][string]$SourceCommit,
    [Parameter(Mandatory)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if ($env:COMPUTERNAME -ne 'MRNG-CLIENT' -or -not (Test-Path C:\mrng-lab\ready.txt)) { throw 'Use the owned lab client.' }
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
if (-not $SourceRoot.StartsWith('C:\mrng-lab\runs\', [StringComparison]::OrdinalIgnoreCase) -or
    -not $OutputDirectory.StartsWith('C:\mrng-lab\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Use owned lab directories.' }
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Use a new artifact directory.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
Import-Module ConfigCI -ErrorAction Stop
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$tools = Join-Path $SourceRoot 'tools\enterprise'
$release = Join-Path $SourceRoot 'mRemoteNG\bin\x64\Debug'
if (-not (Test-Path (Join-Path $release 'mRemoteNG.exe'))) { throw 'Build the pinned application first.' }
$manifest = Join-Path $OutputDirectory 'release-manifest.json'
& (Join-Path $tools 'New-ReleaseManifest.ps1') -ReleaseDirectory $release -SourceCommit $SourceCommit -OutputPath $manifest | Out-Null
$destination = Join-Path $env:ProgramFiles ('mRemoteNG-Lab\' + $SourceCommit.Substring(0,12) + '-' + [Guid]::NewGuid().ToString('N'))
& (Join-Path $tools 'Install-ApprovedRelease.ps1') -ReleaseDirectory $release -ManifestPath $manifest -Destination $destination | Out-Null
$example = Join-Path $env:SystemRoot 'schemas\CodeIntegrity\ExamplePolicies\DefaultWindows_Enforced.xml'
$exampleHash = (Get-FileHash $example -Algorithm SHA256).Hash
if ($exampleHash -ne 'B0B91E0DA5E3D59C48D0EF787CA05088E04DBC5073EFBE601F189321CAB668C0') {
    throw 'The Windows base template differs from the reviewed lab input.'
}
$base = Join-Path $OutputDirectory 'lab-windows-audit.xml'
Copy-Item -LiteralPath $example -Destination $base
Set-CIPolicyIdInfo -FilePath $base -ResetPolicyID -PolicyName ('mRemoteNG lab audit ' + $SourceCommit.Substring(0,12)) | Out-Null
foreach ($option in @(0, 3, 6, 9, 10, 16, 17, 19)) { Set-RuleOption -FilePath $base -Option $option }
Set-CIPolicyVersion -FilePath $base -Version '10.0.0.0'
$baseHash = (Get-FileHash $base -Algorithm SHA256).Hash
$supplement = & (Join-Path $tools 'New-ApprovedAppControlPolicy.ps1') -ReleaseDirectory $destination `
    -ManifestPath $manifest -BasePolicyPath $base -ApprovedBasePolicySha256 $baseHash -OutputDirectory (Join-Path $OutputDirectory 'supplement')
[xml]$baseXml = Get-Content $base
$baseId = $baseXml.SiPolicy.PolicyID
$baseBinary = Join-Path $OutputDirectory ($baseId + '.cip')
ConvertFrom-CIPolicy -XmlFilePath $base -BinaryFilePath $baseBinary
$record = [pscustomobject]@{
    Status = 'generated'; SourceCommit = $SourceCommit; SourceRoot = $SourceRoot
    ReleaseDirectory = $destination; Manifest = $manifest
    ManifestSha256 = (Get-FileHash $manifest -Algorithm SHA256).Hash
    WindowsTemplateSha256 = $exampleHash
    BasePolicyId = $baseId; BasePolicyXml = $base; BasePolicyBinary = $baseBinary; BasePolicySha256 = $baseHash
    SupplementalPolicyBinary = @($supplement)[-1]
    DeploymentState = 'Generated lab artifacts only; no policy installed'
}
$record | ConvertTo-Json -Depth 6 | Tee-Object -FilePath (Join-Path $OutputDirectory 'artifacts.json')
