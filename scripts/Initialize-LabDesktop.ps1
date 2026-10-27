$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if ($env:COMPUTERNAME -ne 'MRNG-CLIENT' -or -not (Test-Path C:\mrng-lab\ready.txt)) { throw 'Use the owned client.' }
Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server' fDenyTSConnections -Value 0
Set-Service TermService -StartupType Automatic
Start-Service TermService
$name = 'mRemoteNG-Lab-RDP-Management'
if (-not (Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name $name -DisplayName 'mRemoteNG lab RDP management' -Direction Inbound `
        -Action Allow -Protocol TCP -LocalPort 3389 -RemoteAddress 10.0.2.2 -Profile Any | Out-Null
}
$deadline = [DateTime]::UtcNow.AddSeconds(30)
do {
    $setting = Get-CimInstance -Namespace root\cimv2\TerminalServices -ClassName Win32_TSGeneralSetting `
        -Filter "TerminalName='RDP-tcp'"
    $certificate = Get-ChildItem 'Cert:\LocalMachine\Remote Desktop' -ErrorAction SilentlyContinue |
        Where-Object Thumbprint -eq $setting.SSLCertificateSHA1Hash
    if ($certificate) { break }
    Start-Sleep -Seconds 1
} while ([DateTime]::UtcNow -lt $deadline)
if (-not $certificate) { throw 'No RDP listener certificate is available for pinning.' }
$hash = [Security.Cryptography.SHA256]::Create()
try { $fingerprint = [BitConverter]::ToString($hash.ComputeHash($certificate.RawData)).Replace('-', '').ToLowerInvariant() }
finally { $hash.Dispose() }
[pscustomobject]@{ Computer = $env:COMPUTERNAME; RdpCertificateSha256 = $fingerprint; Service = (Get-Service TermService).Status.ToString() } | ConvertTo-Json
