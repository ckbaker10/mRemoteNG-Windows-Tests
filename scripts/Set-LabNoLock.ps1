[CmdletBinding()]
param(
    [string]$UserName = 'LabAdmin',
    # Reads the lab-only password from stdin and stores it as the LSA DefaultPassword secret.
    [switch]$EnableAutoLogon
)
# Keeps the owned lab desktop signed in and unlocked for real desktop screenshots:
# no sleep, hibernation or display timeout, no sign-in on wake, no secure screen saver.
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -notin 'MRNG-CLIENT', 'MRNG-DC' -or -not (Test-Path C:\mrng-lab)) { throw 'Use an owned lab guest.' }

foreach ($setting in 'monitor-timeout', 'standby-timeout', 'hibernate-timeout') {
    foreach ($source in 'ac', 'dc') { & powercfg.exe /change "$setting-$source" 0 | Out-Null }
}
& powercfg.exe /hibernate off | Out-Null
# "Require sign-in on wake": CONSOLELOCK 0 = never.
& powercfg.exe /setacvalueindex SCHEME_CURRENT SUB_NONE CONSOLELOCK 0 | Out-Null
& powercfg.exe /setdcvalueindex SCHEME_CURRENT SUB_NONE CONSOLELOCK 0 | Out-Null
& powercfg.exe /setactive SCHEME_CURRENT | Out-Null
$wake = 'HKLM:\SOFTWARE\Policies\Microsoft\Power\PowerSettings\0e796bdb-100d-47d6-a2d5-f7d2daa51f51'
New-Item $wake -Force | Out-Null
Set-ItemProperty $wake ACSettingIndex -Value 0 -Type DWord
Set-ItemProperty $wake DCSettingIndex -Value 0 -Type DWord

$account = Get-CimInstance Win32_UserAccount -Filter "LocalAccount=True and Name='$UserName'"
if (-not $account) { throw "Local lab account $UserName not found." }
$hives = @("Registry::HKEY_USERS\$($account.SID)") + $(if ($env:USERNAME -eq $UserName) { 'HKCU:' } else { @() })
foreach ($hive in $hives | Select-Object -Unique) {
    if (-not (Test-Path "$hive\Control Panel\Desktop")) { continue }
    Set-ItemProperty "$hive\Control Panel\Desktop" ScreenSaveActive -Value '0'
    Set-ItemProperty "$hive\Control Panel\Desktop" ScreenSaverIsSecure -Value '0'
}

$winlogon = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
if ($EnableAutoLogon) {
    $password = [Console]::In.ReadToEnd().TrimEnd("`r", "`n")
    if (-not $password) { throw 'No password received on stdin.' }
    Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class LabLsa {
  [StructLayout(LayoutKind.Sequential)] struct U { public ushort L, M; public IntPtr B; }
  [StructLayout(LayoutKind.Sequential)] struct A { public int Len; public IntPtr R, N; public uint At; public IntPtr S, Q; }
  [DllImport("advapi32")] static extern uint LsaOpenPolicy(IntPtr s, ref A a, uint access, out IntPtr h);
  [DllImport("advapi32")] static extern uint LsaStorePrivateData(IntPtr h, ref U key, ref U data);
  [DllImport("advapi32")] static extern uint LsaClose(IntPtr h);
  [DllImport("advapi32")] static extern uint LsaNtStatusToWinError(uint s);
  static U Make(string v) { var u = new U(); u.B = Marshal.StringToHGlobalUni(v); u.L = (ushort)(v.Length * 2); u.M = (ushort)(u.L + 2); return u; }
  public static void Store(string name, string value) {
    var a = new A(); a.Len = Marshal.SizeOf(a); IntPtr h;
    uint s = LsaOpenPolicy(IntPtr.Zero, ref a, 0x00000020, out h); // POLICY_CREATE_SECRET
    if (s != 0) throw new System.ComponentModel.Win32Exception((int)LsaNtStatusToWinError(s));
    var k = Make(name); var d = Make(value);
    try { s = LsaStorePrivateData(h, ref k, ref d); if (s != 0) throw new System.ComponentModel.Win32Exception((int)LsaNtStatusToWinError(s)); }
    finally { Marshal.ZeroFreeGlobalAllocUnicode(d.B); Marshal.FreeHGlobal(k.B); LsaClose(h); }
  }
}
'@
    [LabLsa]::Store('DefaultPassword', $password)
    $password = $null
    Set-ItemProperty $winlogon AutoAdminLogon -Value '1'
    Set-ItemProperty $winlogon DefaultUserName -Value $UserName
    Set-ItemProperty $winlogon DefaultDomainName -Value $env:COMPUTERNAME
    Remove-ItemProperty $winlogon -Name DefaultPassword, AutoLogonCount -ErrorAction SilentlyContinue
}

[pscustomobject]@{
    Computer = $env:COMPUTERNAME
    StandbyAc = ((powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE | Select-String 'Current AC') -replace '.*:\s*', '')
    SignInOnWakeAc = (Get-ItemProperty $wake).ACSettingIndex
    AutoAdminLogon = (Get-ItemProperty $winlogon).AutoAdminLogon
    PlaintextPasswordInRegistry = [bool](Get-ItemProperty $winlogon).DefaultPassword
} | ConvertTo-Json
