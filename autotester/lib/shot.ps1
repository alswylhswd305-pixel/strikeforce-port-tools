param([int]$ProcId,[string]$Out,[IntPtr]$Hwnd=[IntPtr]::Zero)
# Window capture with PrintWindow(PW_RENDERFULLCONTENT): works for windows that are covered by other
# game instances or not in the foreground (the old CopyFromScreen grabbed whatever was on top, so
# parallel runs all saved the same screen). No SetForegroundWindow, so it never steals focus.
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public class SfW { [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
public struct RECT { public int L,T,R,B; } }
"@
$h=$Hwnd; $title=""
if($h -eq [IntPtr]::Zero){ $p=Get-Process -Id $ProcId -ErrorAction SilentlyContinue
  if(-not $p -or $p.MainWindowHandle -eq [IntPtr]::Zero){ "nowindow"; exit 1 }; $h=$p.MainWindowHandle; $title=$p.MainWindowTitle }
function Grab($w,$hh,$flags,$path){ $b=New-Object Drawing.Bitmap $w,$hh; $g=[Drawing.Graphics]::FromImage($b); $dc=$g.GetHdc()
  $ok=[SfW]::PrintWindow($h,$dc,$flags); $g.ReleaseHdc($dc); $g.Dispose(); $b.Save($path,[Drawing.Imaging.ImageFormat]::Png); $b.Dispose(); $ok }
$r=New-Object SfW+RECT; [SfW]::GetWindowRect($h,[ref]$r)|Out-Null
$w=$r.R-$r.L; $hh=$r.B-$r.T; if($w -le 0){ "badrect"; exit 1 }
$ok1=Grab $w $hh 2 $Out
$cr=New-Object SfW+RECT; [SfW]::GetClientRect($h,[ref]$cr)|Out-Null
$cw=$cr.R-$cr.L; $ch=$cr.B-$cr.T
if($cw -gt 0 -and $ch -gt 0){ $ok2=Grab $cw $ch 3 ($Out -replace '\.png$','_client.png') }
"ok $title"
