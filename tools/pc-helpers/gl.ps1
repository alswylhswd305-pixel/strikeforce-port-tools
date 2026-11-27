param($keys,$name,$w=2)
$pf="$PSScriptRoot\padfile_gL.txt"
foreach($k in ($keys -split ',')){ if($k -match '^s(\d+)$'){Start-Sleep $matches[1]; continue}; $k=$k -replace ':',' '; Set-Content $pf $k -NoNewline; $t=0; while((gc $pf -Raw) -and $t -lt 40){Start-Sleep -m 100;$t++}; Start-Sleep -m 700 }
Start-Sleep $w
.\sfstep.ps1 -proc 8100 -wait 0.2 -name $name -padfile $pf
Copy-Item $env:TEMP\sfstep\$name.jpg $PSScriptRoot\_v.jpg -Force
$x=gc $env:TEMP\ximon_gL.log -ea SilentlyContinue | ? {$_ -match 'ACTIVE'}; "xinput ACTIVE lines: $(@($x).Count)"
