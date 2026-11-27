param([int]$Minutes=25,[int]$ShotSec=8)
$t='%SF_LOCAL_PATH%'; $d="$t\sfauto\movie1786"; $o="$d\run.out"; $sh="$d\shots"
New-Item -ItemType Directory -Force $sh | Out-Null
function L($s){ "$(Get-Date -f HH:mm:ss) $s" | Add-Content $o }
$busy=Get-Process | ? { $_.ProcessName -match 'MyGameRecomp|rpcs3' -or $_.MainWindowTitle -like '*TEST-SALEM*' }
if($busy){ L "BUSY: $(($busy|%{"$($_.Id) $($_.ProcessName)"}) -join ' ; ') - not launching"; exit 1 }
$before=@(Get-Process MyGameRecomp -EA SilentlyContinue | % Id)
Start-Process cmd.exe -ArgumentList '/c',"`"$t\PLAY_Strikeforce_MOVIE1786_TEST.bat`"" -WindowStyle Hidden
$gp=$null; for($i=0;$i -lt 60 -and -not $gp;$i++){ Start-Sleep -m 500; $gp=Get-Process MyGameRecomp -EA SilentlyContinue | ? { $before -notcontains $_.Id } | Select -First 1 }
if(-not $gp){ L "no game pid"; exit 1 }
L "pid $($gp.Id) path $($gp.Path)"; Set-Content "$d\cur_pid.txt" $gp.Id
Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',"$t\sfauto\winplace.ps1",'-ProcId',$gp.Id -WindowStyle Hidden
$end=(Get-Date).AddMinutes($Minutes); $n=0
while((Get-Date) -lt $end){
  if(-not (Get-Process -Id $gp.Id -EA SilentlyContinue)){ L "proc gone"; break }
  if(Test-Path "$d\STOP_SHOTS"){ Start-Sleep 2; continue }
  $n++; $f="$sh\s{0:D4}_{1}.png" -f $n,(Get-Date -f HHmmss)
  $r = & powershell -NoProfile -ExecutionPolicy Bypass -File "$t\sfauto\shot.ps1" -ProcId $gp.Id -Out $f 2>&1
  if($n -le 2 -or $n % 20 -eq 0){ L "shot $n $r" }
  Start-Sleep $ShotSec }
L "loop end"
