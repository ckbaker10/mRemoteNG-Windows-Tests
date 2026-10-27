$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Path C:\mrng-lab -Force | Out-Null
Start-Transcript -Path C:\mrng-lab\bootstrap.log -Append
Get-NetConnectionProfile | Set-NetConnectionProfile -NetworkCategory Private
Enable-PSRemoting -Force -SkipNetworkProfileCheck
Set-Item WSMan:\localhost\Service\AllowUnencrypted -Value $false
New-ItemProperty -Path HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System `
    -Name LocalAccountTokenFilterPolicy -Value 1 -PropertyType DWord -Force | Out-Null
New-NetFirewallRule -DisplayName 'mRemoteNG lab WinRM' -Direction Inbound `
    -Action Allow -Protocol TCP -LocalPort 5985 -Profile Any | Out-Null
# The temporary setup medium is detached after management connectivity is verified.
# Remove cached setup answers containing the lab-only temporary account password.
Remove-Item C:\Windows\Panther\unattend.xml,C:\Windows\Panther\Unattend\unattend.xml `
    -ErrorAction SilentlyContinue
# Keep the lab desktop signed in and unlocked so evidence screenshots show the real desktop.
try { & (Join-Path $PSScriptRoot 'Set-LabNoLock.ps1') } catch { Write-Warning "No-lock desktop settings failed: $_" }
# Keep the guest on its recorded Windows build during acceptance runs.
try { & (Join-Path $PSScriptRoot 'Set-LabUpdatePolicy.ps1') } catch { Write-Warning "Update policy failed: $_" }
Set-Content C:\mrng-lab\ready.txt -Value 'WinRM ready'
Stop-Transcript
