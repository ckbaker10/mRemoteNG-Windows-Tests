$ErrorActionPreference = 'Stop'
$inputObject = [Console]::In.ReadToEnd() | ConvertFrom-Json
if (-not $inputObject.Value.StartsWith('synthetic-ä-', [StringComparison]::Ordinal)) {
    throw 'Synthetic stdin validation failed.'
}
[pscustomobject]@{ InputValidated = $true } | ConvertTo-Json
