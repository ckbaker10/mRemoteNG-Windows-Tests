[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('Environment', 'Source', 'Interactive', 'Registry', 'Domain', 'Rekey')][string]$Stage,
    [string]$ResultPath
)
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne 'MRNG-CLIENT' -or -not [Environment]::UserInteractive -or
    (Get-Process -Id $PID).SessionId -eq 0) { throw 'Evidence display requires the owned client desktop.' }
if (Get-Process LogonUI -ErrorAction SilentlyContinue | Where-Object SessionId -eq (Get-Process -Id $PID).SessionId) {
    throw 'Unlock the lab desktop before recording evidence.'
}
$host.UI.RawUI.WindowTitle = 'mRemoteNG lab evidence - ' + $Stage
Clear-Host
Write-Host ('mRemoteNG lab evidence: ' + $Stage) -ForegroundColor Cyan
Write-Host ('Computer: ' + $env:COMPUTERNAME + '   UTC: ' + [DateTime]::UtcNow.ToString('o'))
if ($Stage -eq 'Environment') {
    $windows = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
    [pscustomobject]@{
        Edition = $windows.EditionID; Version = $windows.DisplayVersion
        Build = $windows.CurrentBuild + '.' + $windows.UBR
        SecureBoot = Confirm-SecureBootUEFI; TpmPresent = (Get-Tpm).TpmPresent
        MSBuild = (Get-Item C:\BuildTools\MSBuild\Current\Bin\MSBuild.exe).VersionInfo.FileVersion
        DotnetSdk = (& 'C:\Program Files\dotnet\dotnet.exe' --version)
    } | Format-List | Out-Host
    return
}
$ResultPath = (Resolve-Path -LiteralPath $ResultPath).Path
if (-not $ResultPath.StartsWith('C:\mrng-lab\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Use a lab result file.' }
Write-Host ('Recorded artifact: ' + $ResultPath)
Write-Host ('SHA-256: ' + (Get-FileHash -LiteralPath $ResultPath -Algorithm SHA256).Hash)
if ($Stage -eq 'Source' -or $Stage -eq 'Rekey') {
    $result = Get-Content -LiteralPath $ResultPath -Raw | ConvertFrom-Json
    if ($result.Status -ne 'passed' -or $result.BuildExitCode -ne 0 -or $result.TestPassed -le 0) { throw 'The recorded build/test result did not pass.' }
    $result | Select-Object SourceCommit, Status, BuildExitCode, TestExitCode, TestTotal, TestPassed, TestFailed, MSBuildVersion |
        Format-List | Out-Host
} elseif ($Stage -eq 'Interactive') {
    [xml]$trx = Get-Content -LiteralPath $ResultPath -Raw
    $counter = $trx.SelectSingleNode('//*[local-name()="Counters"]')
    if ([int]$counter.passed -le 0 -or [int]$counter.failed -ne 0) { throw 'The interactive result did not pass.' }
    [pscustomobject]@{ Tests = $counter.total; Passed = $counter.passed; Failed = $counter.failed; Executed = $counter.executed } |
        Format-List | Out-Host
} elseif ($Stage -eq 'Registry') {
    $result = Get-Content -LiteralPath $ResultPath -Raw | ConvertFrom-Json
    if ($result.Count -ne 5) { throw 'Expected five registry cases.' }
    $result | Select-Object Name, ExitCode | Format-Table -AutoSize | Out-Host
    Write-Host 'Invalid type/value cases must exit with code 2.'
} elseif ($Stage -eq 'Domain') {
    $result = Get-Content -LiteralPath $ResultPath -Raw | ConvertFrom-Json
    if ($result.Status -ne 'completed' -or $result.Probe.IsAdministrator -or -not $result.MachinePolicyWriteBlocked) {
        throw 'The standard-user result did not pass.'
    }
    $result.Probe | Select-Object IsAdministrator, RequireMasterPassword, MinimumMasterPasswordLength,
        AllowPersistentUnlock, PersistentUnlockBlocked, RequireFullEncryption, AllowPasswordExport,
        AllowPlaintextExport, InvalidComplexityRejected, EncryptionEngine, BlockCipherMode, MinimumKdfIterations, SettingsRoundTrip,
        SettingsPlaintextAbsent | Format-List | Out-Host
    Write-Host ('Machine policy write blocked: ' + $result.MachinePolicyWriteBlocked) -ForegroundColor Green
}
