$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne 'MRNG-DC' -or -not (Test-Path C:\mrng-lab\ready.txt)) {
    throw 'Recovery probe is restricted to the owned MRNG-DC guest.'
}
if (Test-Path C:\mrng-lab\restore-probe.txt) { throw 'The post-checkpoint marker was not rolled back.' }
[pscustomobject]@{ RecoveryRollbackVerified = $true; SecureBoot = Confirm-SecureBootUEFI; TpmPresent = (Get-Tpm).TpmPresent } | ConvertTo-Json
