$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -notin 'MRNG-DC', 'MRNG-CLIENT' -or -not (Test-Path C:\mrng-lab\ready.txt)) {
    throw 'Shutdown is restricted to the owned, initialized lab guests.'
}
& "$env:SystemRoot\System32\shutdown.exe" /s /t 5 /d p:4:1
if ($LASTEXITCODE) { throw 'The guest rejected planned shutdown.' }
'Owned lab guest will shut down in five seconds.'
