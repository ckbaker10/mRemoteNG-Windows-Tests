[CmdletBinding()]
param([Parameter(Mandatory)][string]$Run, [Parameter(Mandatory)][string]$Branch, [Parameter(Mandatory)][string]$Environment,
      [Parameter(Mandatory)][string]$Title)
# Shows the recorded guest result unmodified in the interactive desktop for the screenshot.
$ErrorActionPreference = 'Stop'
$r = Get-Content (Join-Path $Run 'result.json') -Raw | ConvertFrom-Json
$Host.UI.RawUI.WindowTitle = $Title
try { $Host.UI.RawUI.BufferSize = New-Object Management.Automation.Host.Size 120, 300; $Host.UI.RawUI.WindowSize = New-Object Management.Automation.Host.Size 120, 30 } catch { }
Clear-Host
"mRemoteNG full mRemoteNGTests run (no filter)"
"=============================================="
"Branch        : $Branch"
"Commit        : $($r.SourceCommit)"
"Archive SHA256: $($r.ArchiveSha256)"
"Environment   : $Environment"
"Machine policy: " + $(if ($r.MachinePolicyValues.Count) { ($r.MachinePolicyValues -join ', ') } else { 'none (HKLM\SOFTWARE\Policies\mRemoteNG\Security absent)' })
"Host          : $env:COMPUTERNAME, Windows $($r.OSEdition) build $($r.OSBuild), session $($r.SessionId)"
"Auto updates  : " + $(if ($r.AutomaticUpdatesDisabled) { 'disabled by lab policy' } else { 'Windows default' })
"Tools         : MSBuild $($r.MSBuild), .NET SDK $($r.DotnetSdk)"
"Started (UTC) : $($r.StartedUtc)"
"Finished (UTC): $($r.FinishedUtc)"
""
"Build exit    : $($r.BuildExitCode)"
"Test exit     : $($r.TestExitCode)"
"Total         : $($r.Trx_total)"
"Passed        : $($r.Trx_passed)"
"Failed        : $($r.Trx_failed)"
"Errors        : $($r.Trx_error)   Timeouts: $($r.Trx_timeout)   Aborted: $($r.Trx_aborted)   Not executed: $($r.Trx_notExecuted)"
""
"Result folder : $Run"
