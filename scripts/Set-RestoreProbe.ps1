$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne 'MRNG-DC' -or -not (Test-Path C:\mrng-lab\ready.txt)) {
    throw 'Recovery probe is restricted to the owned MRNG-DC guest.'
}
Set-Content C:\mrng-lab\restore-probe.txt -Value 'Created after the before-forest checkpoint.'
[pscustomobject]@{ RecoveryProbeCreated = Test-Path C:\mrng-lab\restore-probe.txt } | ConvertTo-Json
