[CmdletBinding()]
param([Parameter(Mandatory)][bool]$ExpectManaged)
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne 'MRNG-CLIENT' -or -not (Test-Path C:\mrng-lab\ready.txt)) { throw 'Use the owned client.' }
$exitCode = & {
    $ErrorActionPreference = 'Continue'
    & gpupdate.exe /target:computer /force /wait:120 2>&1 | ForEach-Object { Write-Host $_ }
    $LASTEXITCODE
}
if ($exitCode) { throw 'Computer policy refresh failed.' }
$key = 'HKLM:\SOFTWARE\Policies\mRemoteNG\Security'
$values = if (Test-Path $key) { @((Get-Item $key).GetValueNames()) } else { @() }
if ($ExpectManaged) {
    if ((Get-ItemPropertyValue $key RequireMasterPassword) -ne 1) { throw 'Managed policy was not applied.' }
} elseif ($values.Count) {
    throw 'Baseline tests require the owned application GPO to be absent.'
}
[pscustomobject]@{ Managed = $ExpectManaged; PolicyValues = $values.Count } | ConvertTo-Json
