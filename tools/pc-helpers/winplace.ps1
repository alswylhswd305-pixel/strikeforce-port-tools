param([int]$ProcId)
# Test windows: once the game window exists, push it to the BOTTOM of the z-order without
# activating it, so it never covers or takes focus from Saud's own game. PrintWindow captures
# still work for covered windows.
Add-Type @"
using System; using System.Runtime.InteropServices;
public class SfP { [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint f); }
"@
for($i=0;$i -lt 120;$i++){ $p=Get-Process -Id $ProcId -EA SilentlyContinue; if(-not $p){ exit }
  if($p.MainWindowHandle -ne [IntPtr]::Zero){ break }; Start-Sleep -Milliseconds 500 }
# repeat for a minute: the game may re-show its window during boot
for($k=0;$k -lt 12;$k++){ $p=Get-Process -Id $ProcId -EA SilentlyContinue; if(-not $p){ exit }
  [SfP]::SetWindowPos($p.MainWindowHandle,[IntPtr]1,0,0,0,0,0x0013) | Out-Null   # HWND_BOTTOM, NOSIZE|NOMOVE|NOACTIVATE
  Start-Sleep 5 }
