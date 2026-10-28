[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Run,
    [Parameter(Mandatory)][string]$SourceArchive,
    [Parameter(Mandatory)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$ArchiveSha256,
    [Parameter(Mandatory)][ValidatePattern('^[a-fA-F0-9]{40}$')][string]$SourceCommit
)
# Full, unfiltered mRemoteNGTests run inside the interactive desktop session.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$result = [ordered]@{ SourceCommit = $SourceCommit; ArchiveSha256 = $ArchiveSha256.ToLowerInvariant()
    StartedUtc = [DateTime]::UtcNow.ToString('o'); SessionId = (Get-Process -Id $PID).SessionId
    Interactive = [Environment]::UserInteractive; Status = 'failed' }
function Save { $result.FinishedUtc = [DateTime]::UtcNow.ToString('o')
    $result | ConvertTo-Json | Set-Content (Join-Path $Run 'result.json') -Encoding UTF8 }
try {
    if ($result.SessionId -eq 0) { throw 'Requires an interactive desktop session.' }
    $policyKey = 'HKLM:\SOFTWARE\Policies\mRemoteNG\Security'
    $result.MachinePolicyValues = if (Test-Path $policyKey) { @((Get-Item $policyKey).GetValueNames() | Sort-Object) } else { @() }
    if ((Get-FileHash $SourceArchive -Algorithm SHA256).Hash -ne $ArchiveSha256) { throw 'Source archive hash mismatch.' }
    $source = Join-Path $Run 'source'
    Expand-Archive -LiteralPath $SourceArchive -DestinationPath $source
    $project = Join-Path $source 'mRemoteNGTests\mRemoteNGTests.csproj'
    $msbuild = 'C:\BuildTools\MSBuild\Current\Bin\MSBuild.exe'
    $dotnet = 'C:\Program Files\dotnet\dotnet.exe'
    $result.MSBuild = (Get-Item $msbuild).VersionInfo.FileVersion
    $result.DotnetSdk = (& $dotnet --version)
    $result.OS = [Environment]::OSVersion.Version.ToString()
    $nt = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
    $result.OSBuild = "$($nt.CurrentBuild).$($nt.UBR)"
    $result.OSEdition = $nt.EditionID
    $result.AutomaticUpdatesDisabled = [bool](Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU' -ErrorAction SilentlyContinue).NoAutoUpdate
    $result.BuildCommand = "MSBuild.exe mRemoteNGTests\mRemoteNGTests.csproj /restore /t:Build /p:Configuration=Debug /p:Platform=x64 /nologo /bl"
    & $msbuild $project /restore /t:Build /p:Configuration=Debug /p:Platform=x64 /nologo "/bl:$Run\build.binlog" *> (Join-Path $Run 'build.log')
    $result.BuildExitCode = $LASTEXITCODE
    Save
    if ($result.BuildExitCode) { throw 'Build failed.' }
    $ErrorActionPreference = 'Continue'
    & $dotnet test $project --no-build --no-restore -p:Platform=x64 --configuration Debug --list-tests *> (Join-Path $Run 'list.log')
    $result.ListExitCode = $LASTEXITCODE
    $result.TestCommand = "dotnet test mRemoteNGTests\mRemoteNGTests.csproj --no-build --no-restore -p:Platform=x64 --configuration Debug --logger trx;LogFileName=tests.trx --blame-hang-timeout 10m"
    & $dotnet test $project --no-build --no-restore -p:Platform=x64 --configuration Debug `
        --logger 'trx;LogFileName=tests.trx' --results-directory $Run --blame-hang-timeout 10m *> (Join-Path $Run 'test.log')
    $result.TestExitCode = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    [xml]$trx = Get-Content (Join-Path $Run 'tests.trx') -Raw
    $c = $trx.SelectSingleNode('//*[local-name()="Counters"]')
    foreach ($n in 'total','executed','passed','failed','error','timeout','aborted','inconclusive','notExecuted','notRunnable') { $result["Trx_$n"] = [int]$c.GetAttribute($n) }
    $result.Status = if ($result.TestExitCode -eq 0 -and $result.Trx_failed -eq 0 -and $result.Trx_error -eq 0 -and $result.Trx_executed -gt 0) { 'passed' } else { 'failed' }
} catch {
    $result.Error = $_.ToString()
} finally { Save }
