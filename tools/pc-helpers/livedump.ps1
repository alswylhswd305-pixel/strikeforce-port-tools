param([int]$procId,[string]$out,[int]$full=0)
Add-Type -TypeDefinition @"
using System; using System.Runtime.InteropServices;
public static class MD { [DllImport("dbghelp.dll",SetLastError=true)] public static extern bool MiniDumpWriteDump(IntPtr h,int pid,Microsoft.Win32.SafeHandles.SafeFileHandle f,int t,IntPtr e,IntPtr u,IntPtr c); }
"@
$p=Get-Process -Id $procId
$fs=[IO.File]::Create($out)
$t= if($full){0x2 -bor 0x4 -bor 0x800 -bor 0x1000} else {0x1 -bor 0x4 -bor 0x40 -bor 0x800 -bor 0x1000}
$ok=[MD]::MiniDumpWriteDump($p.Handle,$procId,$fs.SafeFileHandle,$t,[IntPtr]::Zero,[IntPtr]::Zero,[IntPtr]::Zero)
$fs.Close(); "dump $procId ok=$ok size=$((gi $out).Length)"
