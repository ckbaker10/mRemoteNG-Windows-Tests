$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if ($env:COMPUTERNAME -notin @('MRNG-CLIENT', 'MRNG-DC') -or -not (Test-Path C:\mrng-lab\ready.txt)) {
    throw 'Clock synchronization is restricted to owned lab guests.'
}
$inputData = [Console]::In.ReadToEnd() | ConvertFrom-Json
$target = [DateTimeOffset]::ParseExact($inputData.utc, 'o', [Globalization.CultureInfo]::InvariantCulture)
if ([Math]::Abs(($target.UtcDateTime - [DateTime]::UtcNow).TotalDays) -gt 2) { throw 'Unexpected host/guest date difference.' }
$before = [DateTime]::UtcNow
# QEMU's RTC is UTC. Windows must interpret it consistently after a cold start.
Set-TimeZone -Id 'UTC'
Set-Date -Date $target.UtcDateTime | Out-Null
[pscustomobject]@{
    BeforeUtc = $before.ToString('o'); AfterUtc = [DateTime]::UtcNow.ToString('o'); TimeZone = (Get-TimeZone).Id
} | ConvertTo-Json
