[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ProbeDll,
    [Parameter(Mandatory)][string]$OutputFile
)
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne 'MRNG-CLIENT' -or -not (Test-Path C:\mrng-lab\ready.txt)) {
    throw 'Machine-policy mutations are restricted to the owned MRNG-CLIENT lab guest.'
}
if (-not [Environment]::Is64BitProcess) { throw 'Use 64-bit PowerShell.' }
$machine = 'HKLM:\SOFTWARE\Policies\mRemoteNG\Security'
$user = 'HKCU:\SOFTWARE\Policies\mRemoteNG\Security'
$machineExisted = Test-Path $machine
$userExisted = Test-Path $user
foreach ($path in @($machine, $user)) {
    if (Test-Path $path) {
        $key = Get-Item $path
        if ($key.GetValueNames().Count -or $key.GetSubKeyNames().Count) {
            throw 'Existing policy values found; refusing to overwrite them.'
        }
    }
}
$ProbeDll = (Resolve-Path $ProbeDll).Path
$dotnet = 'C:\Program Files\dotnet\dotnet.exe'
$results = [Collections.Generic.List[object]]::new()
$machineCreated = $false
$userCreated = $false
function Invoke-Probe([string]$Name, [int]$ExpectedExit = 0) {
    $output = & $dotnet $ProbeDll
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne $ExpectedExit) { throw "$Name returned $exitCode, expected $ExpectedExit" }
    $result = $output | ConvertFrom-Json
    $results.Add([pscustomobject]@{ Name = $Name; ExitCode = $exitCode; Result = $result })
    return $result
}
try {
    $baseline = Invoke-Probe 'unmanaged'
    if ($baseline.RequireMasterPassword -or -not $baseline.SettingsRoundTrip) { throw 'Unmanaged baseline failed.' }
    New-Item $user -Force | Out-Null
    $userCreated = $true
    New-ItemProperty $user RequireMasterPassword -Value 1 -PropertyType DWord | Out-Null
    if ((Invoke-Probe 'user-policy-ignored').RequireMasterPassword) { throw 'HKCU unexpectedly overrides machine policy.' }
    New-Item $machine -Force | Out-Null
    $machineCreated = $true
    foreach ($entry in @{
        RequireMasterPassword = 1; MinimumMasterPasswordLength = 16;
        AllowPersistentUnlock = 0; RequireFullEncryption = 1
        RequireUppercase = 1; RequireLowercase = 1; RequireDigit = 1; RequireSpecialCharacter = 1
    }.GetEnumerator()) {
        New-ItemProperty $machine $entry.Key -Value $entry.Value -PropertyType DWord | Out-Null
    }
    New-ItemProperty $user AllowPersistentUnlock -Value 1 -PropertyType DWord | Out-Null
    $managed = Invoke-Probe 'managed-machine-policy'
    if (-not $managed.RequireMasterPassword -or $managed.AllowPersistentUnlock -or
        $managed.MinimumMasterPasswordLength -ne 16 -or -not $managed.RequireFullEncryption -or
        -not $managed.DefaultPasswordRejected -or -not $managed.PersonalPasswordAccepted -or
        -not $managed.InvalidComplexityRejected -or
        -not $managed.SettingsRoundTrip -or -not $managed.SettingsPlaintextAbsent) {
        throw 'Managed policy assertions failed.'
    }
    New-ItemProperty $machine RequireMasterPassword -Value '1' -PropertyType String -Force | Out-Null
    if (-not (Invoke-Probe 'wrong-registry-value-kind' 2).PolicyLoadFailed) { throw 'Invalid registry type accepted.' }
    New-ItemProperty $machine RequireMasterPassword -Value 2 -PropertyType DWord -Force | Out-Null
    if (-not (Invoke-Probe 'invalid-policy-value' 2).PolicyLoadFailed) { throw 'Invalid policy value accepted.' }
} finally {
    if ($machineCreated) {
        if ($machineExisted) {
            foreach ($name in @('RequireMasterPassword', 'MinimumMasterPasswordLength', 'AllowPersistentUnlock',
                    'RequireFullEncryption', 'RequireUppercase', 'RequireLowercase', 'RequireDigit', 'RequireSpecialCharacter')) {
                if ((Get-Item $machine).GetValueNames() -contains $name) { Remove-ItemProperty $machine $name }
            }
        } else { Remove-Item $machine -Recurse -Force }
    }
    if ($userCreated) {
        if ($userExisted) {
            foreach ($name in @('RequireMasterPassword', 'AllowPersistentUnlock')) {
                if ((Get-Item $user).GetValueNames() -contains $name) { Remove-ItemProperty $user $name }
            }
        } else { Remove-Item $user -Recurse -Force }
    }
    $results | ConvertTo-Json -Depth 8 | Set-Content $OutputFile -Encoding UTF8
}
'Machine-policy matrix passed; temporary test policies removed.'
