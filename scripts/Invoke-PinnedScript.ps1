[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ScriptPath,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{64}$')][string]$ScriptSha256,
    [Parameter(Mandatory)][object]$Parameters
)
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -notin @('MRNG-CLIENT', 'MRNG-DC') -or -not (Test-Path C:\mrng-lab\ready.txt)) {
    throw 'Pinned script execution is restricted to owned lab guests.'
}
$ScriptPath = (Resolve-Path -LiteralPath $ScriptPath).Path
if (-not ($ScriptPath.StartsWith('C:\mrng-lab\runs\', [StringComparison]::OrdinalIgnoreCase) -or
          $ScriptPath.StartsWith('C:\mrng-lab\transfer\', [StringComparison]::OrdinalIgnoreCase))) {
    throw 'Use an extracted, pinned lab script.'
}
if ((Get-FileHash -LiteralPath $ScriptPath -Algorithm SHA256).Hash -ne $ScriptSha256) { throw 'Script hash mismatch.' }
$arguments = @{}
foreach ($property in $Parameters.PSObject.Properties) { $arguments[$property.Name] = $property.Value }
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& $ScriptPath @arguments
if (-not $?) { throw 'Pinned script execution failed.' }
