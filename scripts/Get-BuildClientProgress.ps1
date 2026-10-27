$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$dotnet = 'C:\Program Files\dotnet\dotnet.exe'
$sdks = @()
if (Test-Path $dotnet) { $sdks = @(& $dotnet --list-sdks) }
[pscustomobject]@{
    MSBuildPresent = Test-Path 'C:\BuildTools\MSBuild\Current\Bin\MSBuild.exe'
    SdkVersions = $sdks
    CompletedInstallRecord = Test-Path 'C:\mrng-lab\build-tools.json'
    SetupProcesses = @(Get-Process -Name vs_BuildTools, vs_installer, setup -ErrorAction SilentlyContinue | Select-Object ProcessName, Id)
} | ConvertTo-Json -Depth 4
