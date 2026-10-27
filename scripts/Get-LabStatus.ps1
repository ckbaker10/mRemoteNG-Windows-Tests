$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$windows = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
[pscustomobject]@{
    Computer = $env:COMPUTERNAME
    Version = [Environment]::OSVersion.Version.ToString()
    Build = "$($windows.CurrentBuildNumber).$($windows.UBR)"
    Edition = $windows.EditionID
    DisplayVersion = $windows.DisplayVersion
    BootstrapReady = Test-Path C:\mrng-lab\ready.txt
    SecureBoot = Confirm-SecureBootUEFI
    TpmPresent = (Get-Tpm).TpmPresent
} | ConvertTo-Json
