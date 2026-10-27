[CmdletBinding()]
param([Parameter(Mandatory)][string]$ProjectPath)
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne 'MRNG-CLIENT' -or -not (Test-Path C:\mrng-lab\ready.txt)) {
    throw 'Interactive test launch is restricted to the owned MRNG-CLIENT guest.'
}
$ProjectPath = (Get-Item -LiteralPath $ProjectPath).FullName
if (-not $ProjectPath.StartsWith('C:\mrng-lab\runs\', [StringComparison]::OrdinalIgnoreCase) -or
    [IO.Path]::GetFileName($ProjectPath) -ne 'mRemoteNGTests.csproj') { throw 'Use an extracted lab test project.' }
$output = Join-Path (Split-Path (Split-Path $ProjectPath -Parent) -Parent) ('interactive-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $output | Out-Null
$task = 'mRemoteNG-Lab-UI-' + [Guid]::NewGuid().ToString('N')
$runner = Join-Path $PSScriptRoot 'Run-InteractiveUnitTests.ps1'
$arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -ProjectPath "{1}" -OutputDirectory "{2}"' -f $runner, $ProjectPath, $output
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument $arguments
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$registered = $false
try {
    Register-ScheduledTask -TaskName $task -Action $action -Principal $principal -Settings $settings | Out-Null
    $registered = $true
    Start-ScheduledTask -TaskName $task
    $deadline = [DateTime]::UtcNow.AddMinutes(5)
    $resultPath = Join-Path $output 'interactive-result.json'
    while ([DateTime]::UtcNow -lt $deadline) {
        if ((Test-Path $resultPath) -and (Get-ScheduledTask -TaskName $task).State -ne 'Running') { break }
        Start-Sleep -Seconds 1
    }
    if (-not (Test-Path $resultPath) -or (Get-ScheduledTask -TaskName $task).State -eq 'Running') {
        throw 'Interactive test deadline reached. Check the logged-on desktop session.'
    }
    $result = Get-Content $resultPath -Raw | ConvertFrom-Json
    if ($result.Status -ne 'passed') { throw "Interactive tests failed; artifacts: $output" }
    "Interactive test artifacts: $output"
} finally {
    if ($registered) {
        if ((Get-ScheduledTask -TaskName $task).State -eq 'Running') { Stop-ScheduledTask -TaskName $task }
        Unregister-ScheduledTask -TaskName $task -Confirm:$false
    }
}
