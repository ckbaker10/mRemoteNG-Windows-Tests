[CmdletBinding()]
param([Parameter(Mandatory)][bool]$Enabled)
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne 'MRNG-DC' -or -not (Test-Path C:\mrng-lab\ready.txt) -or
    (Get-ADDomain).DNSRoot -ne 'mrng.test') { throw 'Use the owned domain controller.' }
$gpo = Get-GPO -Name 'mRemoteNG Lab Security Acceptance'
if ($gpo.Description -ne 'Owned mRemoteNG automated acceptance policy') { throw 'Refusing an unowned policy.' }
$target = 'OU=mRemoteNG-Lab,DC=mrng,DC=test'
$state = if ($Enabled) { 'Yes' } else { 'No' }
Set-GPLink -Guid $gpo.Id -Target $target -LinkEnabled $state | Out-Null
$link = (Get-GPInheritance -Target $target).GpoLinks | Where-Object GpoId -eq $gpo.Id
if ($null -eq $link -or [bool]$link.Enabled -ne $Enabled) { throw 'GPO link state did not match the request.' }
[pscustomobject]@{ GpoId = $gpo.Id; Enabled = $Enabled; Target = $target } | ConvertTo-Json
