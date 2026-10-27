[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ProbeDll,
    [Parameter(Mandatory)][Guid]$GpoId,
    [Parameter(Mandatory)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if ($env:COMPUTERNAME -ne 'MRNG-CLIENT' -or -not (Test-Path C:\mrng-lab\ready.txt)) { throw 'Use the owned client.' }
Import-Module Microsoft.PowerShell.LocalAccounts -ErrorAction Stop
Import-Module ScheduledTasks -ErrorAction Stop
$system = Get-CimInstance Win32_ComputerSystem
if (-not $system.PartOfDomain -or $system.Domain -ne 'mrng.test' -or -not (Test-ComputerSecureChannel)) {
    throw 'The owned client must have a working mrng.test domain membership.'
}
$ProbeDll = (Resolve-Path -LiteralPath $ProbeDll).Path
if (-not $ProbeDll.StartsWith('C:\mrng-lab\transfer\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Use the pinned lab probe.' }
New-Item -ItemType Directory -Path $OutputDirectory -ErrorAction Stop | Out-Null
$refreshExit = & {
    $ErrorActionPreference = 'Continue'
    & gpupdate.exe /target:computer /force /wait:120 *> (Join-Path $OutputDirectory 'gpupdate.log')
    $LASTEXITCODE
}
if ($refreshExit) { throw 'Computer GPO refresh failed.' }
& gpresult.exe /scope computer /x (Join-Path $OutputDirectory 'gpresult.xml') /f *> (Join-Path $OutputDirectory 'gpresult.log')
if ($LASTEXITCODE) { throw 'Cannot capture computer resultant policy.' }
$rsop = Get-Content (Join-Path $OutputDirectory 'gpresult.xml') -Raw
if ($rsop -notmatch [regex]::Escape($GpoId.ToString())) { throw 'The expected domain GPO is absent from resultant policy.' }
$dotnet = 'C:\Program Files\dotnet\dotnet.exe'
function Assert-ManagedResult($Result) {
    if (-not $Result.RequireMasterPassword -or $Result.MinimumMasterPasswordLength -ne 16 -or
        $Result.AllowPersistentUnlock -or -not $Result.PersistentUnlockBlocked -or
        -not $Result.RequireFullEncryption -or $Result.AllowPasswordExport -or $Result.AllowPlaintextExport -or
        $Result.EncryptionEngine -ne 'AES' -or $Result.BlockCipherMode -ne 'GCM' -or $Result.MinimumKdfIterations -ne 100000 -or
        -not $Result.DefaultPasswordRejected -or -not $Result.PersonalPasswordAccepted -or
        -not $Result.InvalidComplexityRejected -or -not $Result.SettingsRoundTrip -or -not $Result.SettingsPlaintextAbsent) {
        throw 'Domain-managed product behavior did not match the lab GPO.'
    }
}
$adminOutput = & $dotnet $ProbeDll
if ($LASTEXITCODE) { throw 'Administrative policy probe failed.' }
$admin = $adminOutput | ConvertFrom-Json
if (-not $admin.IsAdministrator) { throw 'Expected an administrative probe token.' }
Assert-ManagedResult $admin
$adminOutput | Set-Content (Join-Path $OutputDirectory 'admin.json') -Encoding UTF8
$name = 'mrngprobe'
if (Get-LocalUser -Name $name -ErrorAction SilentlyContinue) { throw 'Refusing to overwrite an existing test account.' }
$task = 'mRemoteNG-Lab-Standard-' + [Guid]::NewGuid().ToString('N')
$created = $false
$registered = $false
$batchGranted = $false
$phase = 'create-user'
try {
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] 48
    $random.GetBytes($bytes)
    $password = ConvertTo-SecureString ([Convert]::ToBase64String($bytes) + 'aA1!') -AsPlainText -Force
    $user = New-LocalUser -Name $name -Password $password -Description 'Owned temporary mRemoteNG acceptance probe'
    $created = $true
    [Array]::Clear($bytes, 0, $bytes.Length)
    $random.Dispose()
    $phase = 'group-membership'
    $users = Get-LocalGroup -SID 'S-1-5-32-545'
    Add-LocalGroupMember -Group $users -Member $user
    [MrngLabUserRights]::SetBatchLogon($user.SID.Value, $true)
    $batchGranted = $true
    $phase = 'output-permissions'
    $standardOutput = Join-Path $OutputDirectory 'standard'
    New-Item -ItemType Directory -Path $standardOutput | Out-Null
    $acl = Get-Acl $standardOutput
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($user.SID, 'Modify', 'ContainerInherit,ObjectInherit', 'None', 'Allow'))
    Set-Acl -LiteralPath $standardOutput -AclObject $acl
    $worker = Join-Path $OutputDirectory 'standard-worker.ps1'
    $escapedProbe = $ProbeDll.Replace("'", "''")
    $escapedOutput = $standardOutput.Replace("'", "''")
    @"
`$ErrorActionPreference = 'Stop'
try {
    `$output = & 'C:\Program Files\dotnet\dotnet.exe' '$escapedProbe'
    if (`$LASTEXITCODE) { throw 'Standard policy probe process failed.' }
    `$probe = `$output | ConvertFrom-Json
    `$writeBlocked = `$false
    try { Set-ItemProperty 'HKLM:\SOFTWARE\Policies\mRemoteNG\Security' AllowPersistentUnlock -Value 1 -ErrorAction Stop }
    catch [System.UnauthorizedAccessException] { `$writeBlocked = `$true }
    catch [System.Security.SecurityException] { `$writeBlocked = `$true }
    [pscustomobject]@{ Status = 'completed'; MachinePolicyWriteBlocked = `$writeBlocked; Probe = `$probe } |
        ConvertTo-Json -Depth 8 | Set-Content '$escapedOutput\result.json' -Encoding UTF8
} catch {
    [pscustomobject]@{ Status = 'failed'; ErrorType = `$_.Exception.GetType().FullName } |
        ConvertTo-Json | Set-Content '$escapedOutput\result.json' -Encoding UTF8
    exit 1
}
"@ | Set-Content -LiteralPath $worker -Encoding UTF8
    $phase = 'register-task'
    # Cross-account S4U registration requires the account password, even though
    # S4U execution does not persist it. Use the explicit COM logon type (2).
    $scheduler = New-Object -ComObject Schedule.Service
    $scheduler.Connect()
    $definition = $scheduler.NewTask(0)
    $definition.Principal.UserId = "$env:COMPUTERNAME\$name"
    $definition.Principal.LogonType = 2
    $definition.Principal.RunLevel = 0
    $definition.Settings.ExecutionTimeLimit = 'PT2M'
    $action = $definition.Actions.Create(0)
    $action.Path = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $action.Arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f $worker
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($password)
    try {
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        $registeredTask = $scheduler.GetFolder('\').RegisterTaskDefinition($task, $definition, 6,
            "$env:COMPUTERNAME\$name", $plain, 2, $null)
        $registered = $true
        if ($registeredTask.Definition.Principal.LogonType -ne 2) { throw 'The task must use nonpersistent S4U logon.' }
    } finally {
        $plain = $null
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $password.Dispose()
    }
    $phase = 'start-task'
    Start-ScheduledTask -TaskName $task
    $deadline = [DateTime]::UtcNow.AddMinutes(2)
    $resultFile = Join-Path $standardOutput 'result.json'
    do {
        if ((Test-Path $resultFile) -and (Get-ScheduledTask -TaskName $task).State -ne 'Running') { break }
        Start-Sleep -Seconds 1
    } while ([DateTime]::UtcNow -lt $deadline)
    if (-not (Test-Path $resultFile)) { throw 'Standard-user task produced no result.' }
    $standard = Get-Content $resultFile -Raw | ConvertFrom-Json
    $phase = 'validate-standard-result'
    if ($standard.Status -ne 'completed' -or -not $standard.MachinePolicyWriteBlocked -or $standard.Probe.IsAdministrator) {
        throw 'Standard-user isolation checks failed.'
    }
    Assert-ManagedResult $standard.Probe
    [pscustomobject]@{
        Status = 'passed'; GpoId = $GpoId; SecureChannelVerified = $true; StandardUserVerified = $true
        ProbeSha256 = (Get-FileHash -LiteralPath $ProbeDll -Algorithm SHA256).Hash.ToLowerInvariant()
    } |
        ConvertTo-Json | Set-Content (Join-Path $OutputDirectory 'result.json') -Encoding UTF8
    "Domain GPO and standard-user checks passed; artifacts: $OutputDirectory"
} finally {
    if ($registered) {
        $info = Get-ScheduledTaskInfo -TaskName $task
        [pscustomobject]@{
            LastTaskResult = $info.LastTaskResult
            LastRunTime = $info.LastRunTime.ToString('o')
            State = (Get-ScheduledTask -TaskName $task).State.ToString()
        } | ConvertTo-Json | Set-Content (Join-Path $OutputDirectory 'task-info.json') -Encoding UTF8
    }
    [pscustomobject]@{ Phase = $phase; AccountCreated = $created; TaskRegistered = $registered } |
        ConvertTo-Json | Set-Content (Join-Path $OutputDirectory 'isolation-progress.json') -Encoding UTF8
    if ($registered) {
        if ((Get-ScheduledTask -TaskName $task).State -eq 'Running') { Stop-ScheduledTask -TaskName $task }
        Unregister-ScheduledTask -TaskName $task -Confirm:$false
    }
    if ($created) {
        try {
            if ($batchGranted) { [MrngLabUserRights]::SetBatchLogon($user.SID.Value, $false) }
        } finally { Remove-LocalUser -Name $name }
    }
}
