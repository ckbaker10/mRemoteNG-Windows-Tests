$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if ($env:COMPUTERNAME -ne 'MRNG-DC' -or -not (Test-Path C:\mrng-lab\ready.txt)) {
    throw 'Domain-role provisioning is restricted to the owned MRNG-DC guest.'
}
$computer = Get-CimInstance Win32_ComputerSystem
if ($computer.PartOfDomain -and $computer.Domain -ne 'mrng.test') {
    throw 'A foreign domain is present; refusing to change this guest.'
}
$names = @('AD-Domain-Services', 'DNS', 'GPMC')
$missing = Get-WindowsFeature -Name $names | Where-Object { -not $_.Installed }
$restart = 'No'
if ($missing) {
    $result = Install-WindowsFeature -Name $missing.Name -IncludeManagementTools
    if (-not $result.Success) { throw 'Lab domain-role installation failed.' }
    $restart = $result.RestartNeeded.ToString()
}
[pscustomobject]@{
    Computer = $env:COMPUTERNAME
    Installed = @((Get-WindowsFeature -Name $names | Where-Object Installed).Name)
    RestartNeeded = $restart
    DomainCreated = $false
} | ConvertTo-Json
