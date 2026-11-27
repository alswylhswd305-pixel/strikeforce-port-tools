# Plan B: run YOUR RPCS3 (portable) on YOUR disc copy, screenshot every 30 s, keep RPCS3.log for
# differential comparison against the recompiled build. Read-only towards RPCS3 settings.
param([int]$Secs=300,[string]$Tag="r4",
      [Parameter(Mandatory)][string]$Rpcs3Dir,          # folder with rpcs3.exe (portable)
      [Parameter(Mandatory)][string]$Eboot,             # <vfs>\dev_bdvd\PS3_GAME\USRDIR\EBOOT.BIN (your disc)
      [string]$OutDir=(Join-Path $PSScriptRoot '..\..\local-runs\rpcs3'))
New-Item -ItemType Directory -Force "$OutDir\screens","$OutDir\logs" | Out-Null
$p=Start-Process "$Rpcs3Dir\rpcs3.exe" -ArgumentList '--no-gui',"`"$Eboot`"" -WorkingDirectory $Rpcs3Dir -PassThru
for($t=30;$t -le $Secs;$t+=30){ Start-Sleep 30; if($p.HasExited){break}; $p.Refresh(); $ln=(Get-Item "$Rpcs3Dir\portable\log\RPCS3.log").Length
 $o=& "$PSScriptRoot\shotwin.ps1" $p.Id "$OutDir\screens\rpcs3_${Tag}_${t}s.png" 2>&1; "$t s len=$ln title=$($p.MainWindowTitle) $o" | Out-File -Append "$OutDir\logs\rpcs3_${Tag}_watch.txt" }
if(-not $p.HasExited){Stop-Process -Id $p.Id -Force}; Start-Sleep 3; Copy-Item "$Rpcs3Dir\portable\log\RPCS3.log" "$OutDir\logs\rpcs3_${Tag}.log"; "DONE" | Out-File -Append "$OutDir\logs\rpcs3_${Tag}_watch.txt"
