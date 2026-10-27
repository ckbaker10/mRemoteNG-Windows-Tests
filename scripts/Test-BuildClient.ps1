$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$record = Get-Content C:\mrng-lab\build-tools.json -Raw | ConvertFrom-Json
if ($record.InstallerExitCode -notin 0, 3010) { throw 'No successful installer completion is recorded.' }
$installer = 'C:\mrng-lab\vs_BuildTools.exe'
$signature = Get-AuthenticodeSignature $installer
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation' -or
    (Get-FileHash $installer -Algorithm SHA256).Hash -ne $record.InstallerSha256) { throw 'Installer provenance check failed.' }
$msbuild = 'C:\BuildTools\MSBuild\Current\Bin\MSBuild.exe'
if (-not (Test-Path $msbuild)) { throw 'Windows MSBuild is missing.' }
& $msbuild -version -nologo
if ($LASTEXITCODE) { throw 'MSBuild verification failed.' }
$sdks = & 'C:\Program Files\dotnet\dotnet.exe' --list-sdks
if (-not ($sdks | Where-Object { $_ -match '^10\.' })) { throw '.NET 10 SDK is missing.' }
$sdks
