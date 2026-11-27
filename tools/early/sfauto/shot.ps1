param([int]$ProcId,[string]$Out)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public class SfW { [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
public struct RECT { public int L,T,R,B; } }
"@
$p=Get-Process -Id $ProcId -ErrorAction SilentlyContinue
if(-not $p -or $p.MainWindowHandle -eq [IntPtr]::Zero){ "nowindow"; exit 1 }
$r=New-Object SfW+RECT; [SfW]::GetWindowRect($p.MainWindowHandle,[ref]$r)|Out-Null
[SfW]::SetForegroundWindow($p.MainWindowHandle)|Out-Null; Start-Sleep -Milliseconds 400
$w=$r.R-$r.L; $h=$r.B-$r.T; if($w -le 0){ "badrect"; exit 1 }
$b=New-Object Drawing.Bitmap $w,$h; $g=[Drawing.Graphics]::FromImage($b); $g.CopyFromScreen($r.L,$r.T,0,0,$b.Size); $g.Dispose()
$b.Save($Out,[Drawing.Imaging.ImageFormat]::Png); $b.Dispose(); "ok $($p.MainWindowTitle)"
