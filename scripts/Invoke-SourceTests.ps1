[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SourceArchive,
    [Parameter(Mandatory)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$ArchiveSha256,
    [Parameter(Mandatory)][ValidatePattern('^[a-fA-F0-9]{40}$')][string]$SourceCommit,
    [string]$RunsRoot = 'C:\mrng-lab\runs',
    [string]$TestFilter = 'FullyQualifiedName~mRemoteNGTests.Security|FullyQualifiedName~mRemoteNGTests.Config.AtomicFileTests|FullyQualifiedName~mRemoteNGTests.Config.ProtectedSettingsProviderTests|FullyQualifiedName~CredentialSerializers|FullyQualifiedName~CsvConnectionsSerializerMremotengFormatTests'
)
$ErrorActionPreference = 'Stop'
if ((Get-FileHash $SourceArchive -Algorithm SHA256).Hash -ne $ArchiveSha256) {
    throw 'Source archive hash mismatch.'
}
$run = Join-Path $RunsRoot ($SourceCommit.Substring(0,12) + '-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $run -Force | Out-Null
$source = Join-Path $run 'source'
Expand-Archive -LiteralPath $SourceArchive -DestinationPath $source
$project = Join-Path $source 'mRemoteNGTests\mRemoteNGTests.csproj'
$msbuild = 'C:\BuildTools\MSBuild\Current\Bin\MSBuild.exe'
$dotnet = 'C:\Program Files\dotnet\dotnet.exe'
$started = [DateTime]::UtcNow
$buildExit = $null
$testExit = $null
$status = 'failed'
$counters = $null
try {
    & $msbuild $project /restore /t:Build /p:Configuration=Debug /p:Platform=x64 /nologo "/bl:$run\build.binlog" *> (Join-Path $run 'build.log')
    $buildExit = $LASTEXITCODE
    if ($buildExit) { throw "Windows build failed: $buildExit; see build.log" }
    & $dotnet test $project --no-build --no-restore -p:Platform=x64 --configuration Debug `
        --filter $TestFilter --logger 'trx;LogFileName=tests.trx' --results-directory $run *> (Join-Path $run 'test.log')
    $testExit = $LASTEXITCODE
    if ($testExit) { throw "Windows tests failed: $testExit; see test.log" }
    [xml]$trx = Get-Content (Join-Path $run 'tests.trx') -Raw
    $counters = $trx.SelectSingleNode('//*[local-name()="Counters"]')
    if ($null -eq $counters -or [int]$counters.total -le 0 -or [int]$counters.executed -le 0 -or
        [int]$counters.failed -ne 0 -or [int]$counters.error -ne 0) {
        throw 'TRX does not prove a successful nonempty test run.'
    }
    $status = 'passed'
} finally {
    [pscustomobject]@{
        SourceCommit = $SourceCommit
        ArchiveSha256 = $ArchiveSha256.ToLowerInvariant()
        StartedUtc = $started.ToString('o')
        FinishedUtc = [DateTime]::UtcNow.ToString('o')
        BuildExitCode = $buildExit
        TestExitCode = $testExit
        Status = $status
        TestTotal = if ($counters) { [int]$counters.total } else { $null }
        TestExecuted = if ($counters) { [int]$counters.executed } else { $null }
        TestPassed = if ($counters) { [int]$counters.passed } else { $null }
        TestFailed = if ($counters) { [int]$counters.failed } else { $null }
        Filter = $TestFilter
        OS = [Environment]::OSVersion.Version.ToString()
        MSBuildVersion = (Get-Item $msbuild).VersionInfo.FileVersion
    } | ConvertTo-Json | Set-Content (Join-Path $run 'result.json') -Encoding UTF8
    Write-Output "Run artifacts: $run"
}
