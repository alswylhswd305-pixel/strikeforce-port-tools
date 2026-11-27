param([int]$ProcId,[string]$Out)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public class W2 { [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
public struct RECT { public int L,T,R,B; } }
"@
$p=Get-Process -Id $ProcId; $h=$p.MainWindowHandle; $r=New-Object W2+RECT; [W2]::GetWindowRect($h,[ref]$r)|Out-Null
$w=$r.R-$r.L; $hh=$r.B-$r.T; $bmp=New-Object Drawing.Bitmap $w,$hh; $g=[Drawing.Graphics]::FromImage($bmp); $hdc=$g.GetHdc(); [W2]::PrintWindow($h,$hdc,2)|Out-Null; $g.ReleaseHdc($hdc); $g.Dispose(); $bmp.Save($Out)
$s=0;$n=0; for($x=0;$x -lt $w;$x+=16){for($y=0;$y -lt $hh;$y+=16){$c=$bmp.GetPixel($x,$y); $s+=$c.R+$c.G+$c.B; $n++}}; $bmp.Dispose(); "saved $Out ${w}x$hh meanRGB=$([math]::Round($s/$n/3,1))"
