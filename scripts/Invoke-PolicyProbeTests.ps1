[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SourceRoot,
    [Parameter(Mandatory)][string]$HarnessRoot,
    [Parameter(Mandatory)][string]$OutputDirectory,
    [switch]$BuildOnly
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if ($env:COMPUTERNAME -ne 'MRNG-CLIENT' -or -not (Test-Path C:\mrng-lab\ready.txt)) {
    throw 'Policy tests are restricted to the owned client.'
}
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
$HarnessRoot = (Resolve-Path -LiteralPath $HarnessRoot).Path
if (-not $SourceRoot.StartsWith('C:\mrng-lab\runs\', [StringComparison]::OrdinalIgnoreCase) -or
    -not $HarnessRoot.StartsWith('C:\mrng-lab\transfer\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Use the extracted, pinned lab source and harness.'
}
New-Item -ItemType Directory -Path $OutputDirectory -ErrorAction Stop | Out-Null
$project = Join-Path $HarnessRoot 'probes\PolicyProbe\PolicyProbe.csproj'
$msbuild = 'C:\BuildTools\MSBuild\Current\Bin\MSBuild.exe'
$exitCode = & {
    $ErrorActionPreference = 'Continue'
    & $msbuild $project /restore /t:Build /p:Configuration=Debug /p:Platform=x64 "/p:MRemoteNGSource=$SourceRoot" `
        /nologo "/bl:$OutputDirectory\probe-build.binlog" *> (Join-Path $OutputDirectory 'probe-build.log')
    $LASTEXITCODE
}
if ($exitCode) { throw "Policy probe build failed: $exitCode; artifacts: $OutputDirectory" }
$dll = Join-Path $HarnessRoot 'probes\PolicyProbe\bin\x64\Debug\net10.0-windows10.0.26100.0\PolicyProbe.dll'
if (-not $BuildOnly) {
    & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass `
        -File (Join-Path $HarnessRoot 'scripts\Invoke-MachinePolicyMatrix.ps1') -ProbeDll $dll `
        -OutputFile (Join-Path $OutputDirectory 'machine-policy.json')
    if ($LASTEXITCODE) { throw 'Machine policy matrix process failed.' }
}
"Policy probe: $dll"
