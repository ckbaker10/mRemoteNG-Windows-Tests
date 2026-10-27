$ErrorActionPreference = 'Stop'
$winlogon = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
Remove-ItemProperty $winlogon -Name DefaultPassword -ErrorAction SilentlyContinue
Set-ItemProperty $winlogon -Name AutoAdminLogon -Value '0'
Remove-ItemProperty $winlogon -Name AutoLogonCount -ErrorAction SilentlyContinue
$answers = @(
    'C:\Windows\Panther\unattend.xml',
    'C:\Windows\Panther\Unattend\unattend.xml',
    'C:\Windows\System32\Sysprep\unattend.xml'
)
foreach ($answer in $answers) { Remove-Item $answer -Force -ErrorAction SilentlyContinue }
if (Get-ItemProperty $winlogon -Name DefaultPassword -ErrorAction SilentlyContinue) {
    throw 'Setup password cleanup failed.'
}
'Cached setup answers and automatic logon password removed. Detach the seed ISO on the host.'
