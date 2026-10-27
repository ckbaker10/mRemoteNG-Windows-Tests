$ErrorActionPreference = 'Stop'
$files = Get-ChildItem (Split-Path $PSScriptRoot -Parent) -Recurse -File -Filter '*.ps1' |
    Where-Object FullName -NotMatch '[\\/]work[\\/]'
$failed = @()
foreach ($file in $files) {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
    if ($errors.Count) { $failed += $file.Name; $errors | ForEach-Object { Write-Output $_.Message } }
}
if ($failed.Count) { throw "PowerShell syntax failed: $($failed -join ', ')" }
"PowerShell syntax passed: $($files.Count) scripts."
