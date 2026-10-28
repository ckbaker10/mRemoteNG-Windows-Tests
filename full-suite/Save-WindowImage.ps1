[CmdletBinding()]
param([Parameter(Mandatory)][string]$Title, [Parameter(Mandatory)][string]$OutFile)
# Captures one window's own rendering (works while the session is locked); no pixels are modified.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class WinCap {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("user32", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindow(string c, string t);
  [DllImport("user32")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
}
'@
$handle = [IntPtr]::Zero
$deadline = [DateTime]::UtcNow.AddSeconds(60)
while ($handle -eq [IntPtr]::Zero -and [DateTime]::UtcNow -lt $deadline) {
    $window = Get-Process | Where-Object MainWindowTitle -eq $Title | Select-Object -First 1
    if ($window) { Start-Sleep -Seconds 2; $handle = $window.MainWindowHandle } else { Start-Sleep -Milliseconds 500 }
}
if ($handle -eq [IntPtr]::Zero) { throw 'Result window not found.' }
$rect = New-Object WinCap+RECT
[void][WinCap]::GetWindowRect($handle, [ref]$rect)
$bitmap = New-Object Drawing.Bitmap ($rect.R - $rect.L), ($rect.B - $rect.T)
$graphics = [Drawing.Graphics]::FromImage($bitmap)
$dc = $graphics.GetHdc()
$ok = [WinCap]::PrintWindow($handle, $dc, 2)
$graphics.ReleaseHdc($dc); $graphics.Dispose()
if (-not $ok) { throw 'PrintWindow failed.' }
$bitmap.Save($OutFile, [Drawing.Imaging.ImageFormat]::Png); $bitmap.Dispose()
