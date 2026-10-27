[CmdletBinding()]
param([switch]$Enable)
# Keeps the owned lab guests on a fixed, recorded Windows build: no automatic update scan,
# download, installation or restart. Use -Enable to restore Windows defaults for a deliberate update.
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -notin 'MRNG-CLIENT', 'MRNG-DC' -or -not (Test-Path C:\mrng-lab)) { throw 'Use an owned lab guest.' }
$wu = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate'
$au = Join-Path $wu 'AU'
if ($Enable) {
    Remove-Item $wu -Recurse -Force -ErrorAction SilentlyContinue
} else {
    New-Item $au -Force | Out-Null
    Set-ItemProperty $au NoAutoUpdate -Value 1 -Type DWord
    Set-ItemProperty $au NoAutoRebootWithLoggedOnUsers -Value 1 -Type DWord
    Set-ItemProperty $wu SetDisableUXWUAccess -Value 1 -Type DWord
    Set-ItemProperty $wu ExcludeWUDriversInQualityUpdate -Value 1 -Type DWord
}
$os = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
[pscustomobject]@{
    Computer = $env:COMPUTERNAME
    AutomaticUpdates = if ($Enable) { 'Windows default' } else { 'disabled by lab policy' }
    NoAutoUpdate = (Get-ItemProperty $au -ErrorAction SilentlyContinue).NoAutoUpdate
    Build = "$($os.CurrentBuild).$($os.UBR)"
} | ConvertTo-Json
