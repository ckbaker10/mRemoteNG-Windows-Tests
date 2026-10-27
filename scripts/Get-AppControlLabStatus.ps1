$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if ($env:COMPUTERNAME -ne 'MRNG-CLIENT' -or -not (Test-Path C:\mrng-lab\ready.txt)) { throw 'Use the owned client.' }
$tool = Join-Path $env:SystemRoot 'System32\CiTool.exe'
if (-not (Test-Path -LiteralPath $tool)) { throw 'CiTool is unavailable.' }
Import-Module ConfigCI -ErrorAction Stop
$raw = & $tool -lp -json
if ($LASTEXITCODE) { throw 'Cannot enumerate installed App Control policies.' }
$policies = $raw | ConvertFrom-Json
[pscustomobject]@{
    Computer = $env:COMPUTERNAME
    OSBuild = [Environment]::OSVersion.Version.ToString()
    SecureBoot = Confirm-SecureBootUEFI
    TpmPresent = (Get-Tpm).TpmPresent
    PowerShellVersion = $PSVersionTable.PSVersion.ToString()
    ConfigCIModule = (Get-Module ConfigCI).Path
    WindowsBasePolicy = Join-Path $env:SystemRoot 'schemas\CodeIntegrity\ExamplePolicies\DefaultWindows_Enforced.xml'
    Policies = $policies
} | ConvertTo-Json -Depth 12
