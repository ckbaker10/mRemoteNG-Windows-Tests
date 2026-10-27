$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if ($env:COMPUTERNAME -ne 'MRNG-DC' -or -not (Test-Path C:\mrng-lab\ready.txt) -or
    (Get-ADDomain).DNSRoot -ne 'mrng.test') { throw 'Use the isolated mrng.test lab controller.' }
# Multihomed DC: publish only the private NIC, never the NAT management address.
$dnsSettings = Get-DnsServerSetting -All
$dnsSettings.ListeningIpAddress = @('192.168.77.10')
Set-DnsServerSetting -InputObject $dnsSettings
foreach ($zone in @('mrng.test', '_msdcs.mrng.test')) {
    Get-DnsServerResourceRecord -ZoneName $zone -RRType A | Where-Object {
        $_.RecordData.IPv4Address.IPAddressToString -eq '10.0.2.15'
    } | Remove-DnsServerResourceRecord -ZoneName $zone -Force
}
$zone = Get-DnsServerZone -Name 'mrng.test'
$ns = @(Get-DnsServerResourceRecord -ZoneName $zone.ZoneName -RRType NS | Where-Object HostName -eq '@')
if (-not ($ns | Where-Object { $_.RecordData.NameServer -eq 'mrng-dc.mrng.test.' })) {
    throw 'Unexpected domain nameserver record.'
}
$ou = 'OU=mRemoteNG-Lab,DC=mrng,DC=test'
if (-not (Get-ADOrganizationalUnit -Filter "DistinguishedName -eq '$ou'")) {
    New-ADOrganizationalUnit -Name 'mRemoteNG-Lab' -Path 'DC=mrng,DC=test' -ProtectedFromAccidentalDeletion $true | Out-Null
}
$name = 'mRemoteNG Lab Security Acceptance'
$gpo = Get-GPO -Name $name -ErrorAction SilentlyContinue
if ($gpo -and $gpo.Description -ne 'Owned mRemoteNG automated acceptance policy') { throw 'Refusing an unowned GPO.' }
if (-not $gpo) { $gpo = New-GPO -Name $name -Comment 'Owned mRemoteNG automated acceptance policy' }
$key = 'HKLM\SOFTWARE\Policies\mRemoteNG\Security'
foreach ($entry in @{
    RequireMasterPassword = 1; MinimumMasterPasswordLength = 16; AllowPersistentUnlock = 0
    RequireUppercase = 1; RequireLowercase = 1; RequireDigit = 1; RequireSpecialCharacter = 1
    RequireFullEncryption = 1; AllowPasswordExport = 0; AllowPlaintextExport = 0
    MinimumKdfIterations = 100000
}.GetEnumerator()) { Set-GPRegistryValue -Guid $gpo.Id -Key $key -ValueName $entry.Key -Type DWord -Value $entry.Value | Out-Null }
Set-GPRegistryValue -Guid $gpo.Id -Key $key -ValueName EncryptionEngine -Type String -Value AES | Out-Null
Set-GPRegistryValue -Guid $gpo.Id -Key $key -ValueName BlockCipherMode -Type String -Value GCM | Out-Null
if (-not ((Get-GPInheritance -Target $ou).GpoLinks | Where-Object GpoId -eq $gpo.Id)) {
    New-GPLink -Guid $gpo.Id -Target $ou -LinkEnabled Yes | Out-Null
}
$output = 'C:\mrng-lab\domain-gpo'
New-Item -ItemType Directory -Path $output -Force | Out-Null
Get-GPOReport -Guid $gpo.Id -ReportType Xml -Path (Join-Path $output 'policy.xml')
[pscustomobject]@{ Domain = 'mrng.test'; OrganizationalUnit = $ou; GpoId = $gpo.Id; Report = "$output\policy.xml" } |
    ConvertTo-Json | Tee-Object -FilePath (Join-Path $output 'result.json')
