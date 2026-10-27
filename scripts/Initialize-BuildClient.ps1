[CmdletBinding()]
param([string]$LabRoot = 'C:\mrng-lab')
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory $LabRoot -Force | Out-Null
$installer = Join-Path $LabRoot 'vs_BuildTools.exe'
Invoke-WebRequest 'https://aka.ms/vs/18/release/vs_BuildTools.exe' -OutFile $installer
$signature = Get-AuthenticodeSignature $installer
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
    throw 'Build Tools bootstrapper has no valid Microsoft signature.'
}
Get-FileHash $installer -Algorithm SHA256 | Format-List
$arguments = @('--quiet', '--wait', '--norestart', '--nocache',
    '--installPath', 'C:\BuildTools',
    '--add', 'Microsoft.VisualStudio.Workload.ManagedDesktopBuildTools',
    '--add', 'Microsoft.VisualStudio.Component.Windows11SDK.26100',
    '--includeRecommended')
$process = Start-Process $installer -ArgumentList $arguments -Wait -PassThru
if ($process.ExitCode -notin 0, 3010) { throw "Build Tools installation failed: $($process.ExitCode)" }
$msbuild = 'C:\BuildTools\MSBuild\Current\Bin\MSBuild.exe'
if (-not (Test-Path $msbuild)) { throw 'Windows MSBuild is missing.' }
& $msbuild -version -nologo
if ($LASTEXITCODE) { throw 'MSBuild version check failed.' }
& 'C:\Program Files\dotnet\dotnet.exe' --list-sdks
if ($LASTEXITCODE) { throw '.NET SDK check failed.' }
[pscustomobject]@{
    FinishedUtc = [DateTime]::UtcNow.ToString('o')
    InstallerSha256 = (Get-FileHash $installer -Algorithm SHA256).Hash
    InstallerExitCode = $process.ExitCode
    RebootRequired = $process.ExitCode -eq 3010
} | ConvertTo-Json | Set-Content (Join-Path $LabRoot 'build-tools.json') -Encoding UTF8
