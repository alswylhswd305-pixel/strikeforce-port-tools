param([int]$proc,[string]$out,[int]$every=30)
# Soak sampler: private bytes, working set, handles, threads, GPU dedicated/shared bytes every $every s.
"time,elapsed_s,private_mb,ws_mb,handles,threads,gpu_ded_mb,gpu_shared_mb" | Set-Content $out
$t0=Get-Date
while ($p = Get-Process -Id $proc -EA SilentlyContinue) {
  $ded=$null;$sh=$null
  try { $c=Get-Counter "\GPU Process Memory(pid_$($proc)_*)\Dedicated Usage","\GPU Process Memory(pid_$($proc)_*)\Shared Usage" -EA Stop
        $ded=($c.CounterSamples | ? Path -like '*dedicated*' | measure CookedValue -Sum).Sum/1MB
        $sh=($c.CounterSamples | ? Path -like '*shared*' | measure CookedValue -Sum).Sum/1MB } catch {}
  "{0},{1},{2:F1},{3:F1},{4},{5},{6:F1},{7:F1}" -f (Get-Date -f HH:mm:ss),[int]((Get-Date)-$t0).TotalSeconds,($p.PrivateMemorySize64/1MB),($p.WorkingSet64/1MB),$p.HandleCount,$p.Threads.Count,$ded,$sh | Add-Content $out
  Start-Sleep $every }
"exit,$([int]((Get-Date)-$t0).TotalSeconds)" | Add-Content $out

