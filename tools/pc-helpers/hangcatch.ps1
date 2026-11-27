# hangcatch.ps1 -- DIAGNOSE-ONLY hang catcher. Watches one MyGameRecomp process; when its title
# (FPS/draws) stops changing for -stallSecs, takes 3 full dumps -gap s apart with per-thread CPU
# samples and a PrintWindow shot, then runs hangreport.py. Never stops, presses or fixes anything.
param([int]$procId,[string]$run,[int]$stallSecs=10,[int]$gap=4,[string]$map,[string]$watch="",[int]$maxMin=60)
$sf='%SF_LOCAL_PATH%'; cd $sf
$out="$sf\dumps\hangcatch_${procId}_$(Get-Date -Format HHmmss)"; mkdir $out -Force | out-null
$log="$out\hangcatch.log"; function L($m){ "$(Get-Date -Format HH:mm:ss) $m" | Tee-Object -Append $log }
L "watching pid $procId (stall=${stallSecs}s gap=${gap}s) run=$run"
$last=""; $since=Get-Date; $t0=Get-Date
while ($true) {
  $p=Get-Process -Id $procId -EA 0; if(-not $p){ L "process gone - no hang caught"; exit 0 }
  if(((Get-Date)-$t0).TotalMinutes -gt $maxMin){ L "max time reached - no hang caught"; exit 0 }
  $t=$p.MainWindowTitle -replace '^.*?\| ',''
  if($t -ne $last){ $last=$t; $since=Get-Date } elseif(((Get-Date)-$since).TotalSeconds -ge $stallSecs -and $t -match 'draws'){ break }
  Start-Sleep 1
}
L "STALL: title unchanged ${stallSecs}s: $($p.MainWindowTitle)"
powershell -NoProfile -File "$sf\shot.ps1" -ProcId $procId -Out "$out\window.png" | out-null
$cpu="$out\threads_cpu.txt"; $dumps=@()
foreach($k in 1..3){
  $p=Get-Process -Id $procId; $s1=@{}; foreach($th in $p.Threads){ $s1[$th.Id]=$th.TotalProcessorTime.TotalMilliseconds }
  Start-Sleep 2; $p.Refresh()
  ($p.Threads | % { "{0}:{1}" -f $_.Id,[int]($_.TotalProcessorTime.TotalMilliseconds-$s1[$_.Id]) }) -join ' ' | Add-Content $cpu
  $d="$out\dump$k.dmp"; powershell -NoProfile -File "$sf\livedump.ps1" -procId $procId -out $d -full 1 | % { L $_ }; $dumps+=$d
  L "title: $($p.MainWindowTitle)"
  if($k -lt 3){ Start-Sleep $gap }
}
if($run){ gc "$run\stderr.log" -Tail 3000 | Set-Content "$out\stderr_tail.txt" }
python "$sf\hangreport.py" --map $map --run $run --cpu $cpu --watch $watch --out "$out\report.md" @dumps 2>&1 | % { L $_ }
L "DONE report=$out\report.md (process left running; the operator closes it)"
