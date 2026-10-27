[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ProjectPath,
    [Parameter(Mandatory)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$status = 'failed'
$exitCode = $null
try {
    if (-not [Environment]::UserInteractive -or (Get-Process -Id $PID).SessionId -eq 0) {
        throw 'The dialog tests require an interactive user session.'
    }
    $dotnet = 'C:\Program Files\dotnet\dotnet.exe'
    $exitCode = & {
        $ErrorActionPreference = 'Continue'
        & $dotnet test $ProjectPath --no-build --no-restore -p:Platform=x64 --configuration Debug `
            --filter 'FullyQualifiedName~mRemoteNGTests.UI.Forms.PasswordFormTests' `
            --logger 'trx;LogFileName=interactive.trx' --results-directory $OutputDirectory *> (Join-Path $OutputDirectory 'interactive.log')
        $LASTEXITCODE
    }
    if ($exitCode) { throw "Interactive NUnit run failed: $exitCode" }
    [xml]$trx = Get-Content (Join-Path $OutputDirectory 'interactive.trx') -Raw
    $counters = $trx.SelectSingleNode('//*[local-name()="Counters"]')
    if ($null -eq $counters -or [int]$counters.executed -le 0 -or
        [int]$counters.failed -ne 0 -or [int]$counters.error -ne 0) { throw 'Interactive TRX validation failed.' }
    $status = 'passed'
} finally {
    [pscustomobject]@{
        Status = $status; ExitCode = $exitCode
        SessionId = (Get-Process -Id $PID).SessionId
        FinishedUtc = [DateTime]::UtcNow.ToString('o')
    } | ConvertTo-Json | Set-Content (Join-Path $OutputDirectory 'interactive-result.json') -Encoding UTF8
}
