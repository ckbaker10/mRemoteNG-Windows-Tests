$ErrorActionPreference = 'Stop'
[pscustomobject]@{
    Computer = $env:COMPUTERNAME
    Version = [Environment]::OSVersion.Version.ToString()
    BootstrapReady = Test-Path C:\mrng-lab\ready.txt
    SecureBoot = Confirm-SecureBootUEFI
    TpmPresent = (Get-Tpm).TpmPresent
} | ConvertTo-Json
