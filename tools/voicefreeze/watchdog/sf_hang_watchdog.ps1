<#
sf_hang_watchdog.ps1 -- DETECT-AND-STOP watchdog for the Strikeforce "Now Loading" hang (test copy only).

It never writes game memory, never injects, never presses keys, never sets env vars for the game and
never forces the game past the hang. It only: reads the stderr log (shared read), reads process/thread
CPU times and the window title, and - after a hang is detected - writes a report, copies dump files,
asks the game window to close (WM_CLOSE -> the runtime's own quit path) and kills it if that fails.

Signals (all from real log lines of our runtime; see README.md):
  ef_blocked           [cellSpurs] EventFlagWait BLOCKED ... Ns ... flagEA=0x00DBA900 with N >= -EfBlockedSec
  spu_halt             [SPU-HALT] / [SPU-TRACE] halt, or "branched into unlifted LS 0xA" whose LS[0xA] word is a
                       conditional halt (heqi/hgti/hlgti/heq/hgt/hlgt); fires after -HaltGraceSec
  loading_no_progress  a Now Loading marker ([fs] open '/dev_hdd1/cache/BLUS30471/<n>') and no non-heartbeat log
                       line for -NoProgressSec, and (live) the FPS title unchanged for as long
  busy_spin            (live) process CPU >= -BusyCpu cores for -BusySec, no progress line, FPS title unchanged
  busy_spin_hle        two [hle-lrc] dumps with no progress line between them and one (nid,lr,tid) >= -SpinCallsPerSec
  spu_job_stuck        (v2) [spu-spin] for a short repeating SPU job (>= -JobMinReturns completed runs) whose current
                       run never RETURNs within -JobStuckSec (no clock in a replay: -JobStuckLines lines)
  frozen_busy          (v2, live) FPS title unchanged for -FrozenSec and CPU >= -BusyCpu, whatever the log prints
  (seen only, never fires: task_reuse_unreturned, spu_spin_info - written to the report)
Version: v2 2026-11-27 (v1 = first 5 signals).

Windows PowerShell 5.1 compatible. Save as UTF-8 WITH BOM (the Arabic message needs it).
Usage (Salem):
  powershell -NoProfile -ExecutionPolicy Bypass -File sf_hang_watchdog.ps1 -Launch C:\...\PLAY_Strikeforce_VOICEDIAG1786_PAD.bat
  powershell -NoProfile -ExecutionPolicy Bypass -File sf_hang_watchdog.ps1 -AttachPid 11188 -Log C:\...\play_logs\x_stderr.log
  pwsh -File sf_hang_watchdog.ps1 -Replay saved_stderr.log [-ReplayStripPrefix]      (dry run, no process)
#>
param(
    [string]$Launch = '',              # .bat/.cmd (run as-is) or .exe (stderr redirected to -Log)
    [string]$LaunchArgs = '',
    [int]$AttachPid = 0,
    [string]$ProcName = 'MyGameRecomp', # game process name (without .exe) under the .bat launcher
    [string]$Log = '',                 # stderr log; empty = newest *stderr*.log in -LogDir written after start
    [string]$LogDir = '',              # default: <launcher dir>\play_logs
    [string]$OutDir = '',              # default: <launcher dir>\sfauto\hangwatch (or .\hangwatch)
    [string[]]$DumpPaths = @(),        # extra files/dirs/wildcards to copy (sfrace logs, ovl dirs)
    [string]$Replay = '',              # dry run on a saved log
    [switch]$ReplayStripPrefix,        # replay input lines look like "66154:[SPU-HALT] ..."
    [int]$NoProgressSec = 20,
    [int]$EfBlockedSec = 5,
    [int]$HaltGraceSec = 5,
    [double]$BusyCpu = 0.5,            # CPU cores (process CPU seconds per wall second)
    [int]$BusySec = 20,
    [int]$SpinCallsPerSec = 40000,
    [int]$JobMinReturns = 50,
    [int]$JobStuckSec = 10,
    [int]$JobStuckLines = 200,
    [int]$FrozenSec = 45,
    [string]$FlagEA = '0x00DBA900',
    [int]$LoadingHoldSec = 300,
    [int]$CloseWaitSec = 20,
    [int]$SpinCaptureSec = 25,         # after a fire, keep reading up to this long for one more [hle-lrc] dump
    [int]$PollMs = 500,
    [int]$MaxMin = 0,                  # 0 = watch until the game exits or a hang fires
    [switch]$NoClose,                  # report only, leave the game running
    [switch]$NoMessage
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2

# ---------------------------------------------------------------- Detection rules (keep in step with watchdog_logic.py)
$RX_EF        = [regex]'\[cellSpurs\] EventFlagWait BLOCKED tid=(\d+) (\d+)s on pattern 0x([0-9A-Fa-f]+) .*?flagEA=0x([0-9A-Fa-f]+)'
$RX_HALT_LINE = [regex]'^\[SPU-HALT\] img=(\d+) pc=0x([0-9A-Fa-f]+)|^\[SPU-TRACE\] halt at LS 0x([0-9A-Fa-f]+)'
$RX_BRANCH    = [regex]'^\[spu\] img=(\d+) branched into unlifted LS 0x([0-9A-Fa-f]+) \(lr=0x([0-9A-Fa-f]+)\)'
$RX_LSDUMP    = [regex]'^\s+LS\[0x([0-9A-Fa-f]+)\]: ([0-9A-Fa-f]{8})'
$RX_LOADING   = [regex]"^\[fs\] open '/dev_hdd1/cache/BLUS30471/\d+'|(?i:now ?loading)"
$RX_T         = [regex]'^\[(?:vm-sum|sfww|hle-lr|hle-lrc|vm|vm-cnt|vi)\].*?\bt=(\d+)'
$RX_LRC_HDR   = [regex]'^\[hle-lrc\] dump=(\d+) t=(\d+) pairs=(\d+)'
$RX_LRC       = [regex]'^\[hle-lrc\] (\d+) 0x([0-9A-Fa-f]+) 0x([0-9A-Fa-f]+) (\d+) ret=0x[0-9A-Fa-f]+ tid=(\d+)'
$RX_DISPATCH  = [regex]'^\[spu_workload\] dispatch HIT \(async\) fp=0x[0-9A-Fa-f]+ args=0x([0-9A-Fa-f]+) image=(\d+)'
$RX_RETURNED  = [regex]'^\[spu_workload\] async image=(\d+) RETURNED'
$RX_SPUSPIN   = [regex]'^\[spu-spin\] img=(\d+) pc=0x([0-9A-Fa-f]+) lr=0x([0-9A-Fa-f]+) GETLLAR ea=0x([0-9A-Fa-f]+)'
$HEARTBEAT    = @('^\[vm-sum\]','^\[hle-lrc\]','^\[cellSpurs\] EventFlagWait BLOCKED','^\[spu_workload\] task \d+ .*sleeping \d+s',
                  '^\[samp\]','^\[pcsample\]','^\[spu-spin\]','^\[sfrace','^\s*$',
                  '^\[WAIT\] event_queue_receive\(','^\[spu_workload\] WAIT_SIGNAL#','^\[cellAtrac\] Atrac3/3\+: ') | ForEach-Object { [regex]$_ }
$VERSION = 'v2 2026-11-27'
$NIDS = @{ '350D454E'='sys_ppu_thread_get_id'; '1BC200F4'='sys_lwmutex_unlock'; '1573DC3F'='sys_lwmutex_lock';
           '2A6D9D51'='sys_lwcond_wait'; 'E9A1BD84'='sys_lwcond_signal_all'; 'EF87A695'='sys_lwcond_signal' }
$FLAG = [Convert]::ToUInt32($FlagEA.Replace('0x',''), 16)

function Test-HaltOp([uint32]$w) {
    $op8 = $w -shr 24; $op11 = $w -shr 21
    return (@(0x7F,0x4F,0x5F) -contains $op8) -or (@(0x3D8,0x258,0x2D8) -contains $op11)
}

$S = @{
    now = $null; signals = New-Object System.Collections.ArrayList; fired = $null
    halt = $null; branch = $null; loading = $null; lastProgress = $null
    lrcCur = $null; lrcPrev = $null; lrcProgress = 0; spinTop = @()
    lrcText = New-Object System.Collections.ArrayList; lrcDone = New-Object System.Collections.ArrayList
    framesStalledSec = [double]::PositiveInfinity; cpuCores = $null; cpuWindowSec = 0; live = $false
    tail = New-Object 'System.Collections.Generic.Queue[string]'; tailAtFire = $null; spuSpin = New-Object System.Collections.ArrayList
    pcsample = New-Object System.Collections.ArrayList; samp = New-Object System.Collections.ArrayList
    jobs = @{}; stuck = $null
}
function Get-Job($img) {
    if (-not $S.jobs.ContainsKey($img)) { $S.jobs[$img] = @{ disp=0; ret=0; open=(New-Object System.Collections.ArrayList) } }
    return $S.jobs[$img]
}

function Add-Signal($name, $ln, $text, $detail, [bool]$fire) {
    if ($text.Length -gt 240) { $text = $text.Substring(0,240) }
    $sig = [ordered]@{ signal=$name; line=$ln; t_ms=$S.now; text=$text; detail=$detail; fires=$fire; wall=(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz') }
    [void]$S.signals.Add($sig)
    if ($fire -and -not $S.fired) { $S.fired = $sig; $S.tailAtFire = $S.tail.ToArray() }
}

function Close-Lrc {
    $c = $S.lrcCur; if (-not $c -or $c.calls.Count -lt $c.pairs) { return }   # incomplete dump: never compare it
    if ($S.lrcPrev -and $S.lrcPrev.no -eq $c.no) { return }
    $p = $S.lrcPrev
    if ($p -and $c.t -gt $p.t) {
        $dt = ($c.t - $p.t) / 1000.0
        $rates = foreach ($k in $c.calls.Keys) {
            $prev = 0; if ($p.calls.ContainsKey($k)) { $prev = $p.calls[$k] }
            $parts = $k.Split('/')
            $nm = '?'; if ($NIDS.ContainsKey($parts[0])) { $nm = $NIDS[$parts[0]] }
            [pscustomobject]@{ per_s=[math]::Round(($c.calls[$k] - $prev) / $dt); nid='0x'+$parts[0]; name=$nm; lr='0x'+$parts[1]; tid=[int]$parts[2] }
        }
        $S.spinTop = @($rates | Sort-Object per_s -Descending | Select-Object -First 10)
        if ($S.spinTop.Count -gt 0 -and $S.spinTop[0].per_s -ge $SpinCallsPerSec -and $c.progressBefore -eq 0) {
            Add-Signal 'busy_spin_hle' $c.ln ("[hle-lrc] dump={0}->{1}" -f $p.no, $c.no) @{ top=@($S.spinTop | Select-Object -First 5); interval_s=$dt } $true
        }
    }
    $S.lrcPrev = $c
}

function Feed-Line([long]$ln, [string]$line, $wallMs) {
    if ($S.tail.Count -ge 2000) { [void]$S.tail.Dequeue() }
    $S.tail.Enqueue($line)
    $m = $RX_T.Match($line)
    if ($null -ne $wallMs) { $S.now = $wallMs } elseif ($m.Success) { $S.now = [long]$m.Groups[1].Value }
    $hb = $false; foreach ($r in $HEARTBEAT) { if ($r.IsMatch($line)) { $hb = $true; break } }
    if (-not $hb) { $S.lastProgress = @($ln, $S.now, $line); $S.lrcProgress++ }
    if ($line.StartsWith('[spu-spin]')) { [void]$S.spuSpin.Add("L${ln}: $line") }
    elseif ($line.StartsWith('[pcsample]')) { [void]$S.pcsample.Add($line); if ($S.pcsample.Count -gt 400) { $S.pcsample.RemoveAt(0) } }
    elseif ($line.StartsWith('[samp]')) { [void]$S.samp.Add($line); if ($S.samp.Count -gt 400) { $S.samp.RemoveAt(0) } }

    $m = $RX_EF.Match($line)
    if ($m.Success -and [Convert]::ToUInt32($m.Groups[4].Value,16) -eq $FLAG) {
        $secs = [int]$m.Groups[2].Value
        if ($secs -ge $EfBlockedSec) { Add-Signal 'ef_blocked' $ln $line @{ tid=[int]$m.Groups[1].Value; secs=$secs; flag=$FlagEA } $true }
    }
    $m = $RX_HALT_LINE.Match($line)
    if ($m.Success -and -not $S.halt) {
        $pc = $m.Groups[2].Value; if (-not $pc) { $pc = $m.Groups[3].Value }
        $S.halt = @($ln, $S.now, $pc.ToUpper())
        Add-Signal 'spu_halt' $ln $line @{ pc='0x'+$pc.ToUpper(); grace_s=$HaltGraceSec } $false
    }
    $m = $RX_BRANCH.Match($line)
    if ($m.Success) { $S.branch = @($ln, $m.Groups[2].Value.ToUpper(), $m.Groups[1].Value) }
    $m = $RX_LSDUMP.Match($line)
    if ($m.Success -and $S.branch -and $m.Groups[1].Value.ToUpper() -eq $S.branch[1]) {
        $w = [Convert]::ToUInt32($m.Groups[2].Value, 16)
        if ((Test-HaltOp $w) -and -not $S.halt) {
            $S.halt = @($S.branch[0], $S.now, $S.branch[1])
            Add-Signal 'spu_halt' $S.branch[0] $line @{ pc='0x'+$S.branch[1]; img=$S.branch[2]; word=('{0:X8}' -f $w); grace_s=$HaltGraceSec } $false
        }
        $S.branch = $null
    }
    if ($RX_LOADING.IsMatch($line)) { $S.loading = @($ln, $S.now, $line) }
    $m = $RX_LRC_HDR.Match($line)
    if ($m.Success) {
        Close-Lrc
        if ($S.lrcCur -and $S.lrcCur.calls.Count -ge $S.lrcCur.pairs) { [void]$S.lrcDone.Add($S.lrcText); while ($S.lrcDone.Count -gt 2) { $S.lrcDone.RemoveAt(0) } }   # keep the last 2 complete dumps
        $S.lrcText = New-Object System.Collections.ArrayList
        $S.lrcCur = @{ no=[int]$m.Groups[1].Value; t=[long]$m.Groups[2].Value; pairs=[int]$m.Groups[3].Value; ln=$ln; calls=@{}; progressBefore=$S.lrcProgress }
        $S.lrcProgress = 0
    }
    if ($line.StartsWith('[hle-lrc]')) { [void]$S.lrcText.Add($line) }
    $m = $RX_LRC.Match($line)
    if ($m.Success -and $S.lrcCur -and [int]$m.Groups[1].Value -eq $S.lrcCur.no) {
        $S.lrcCur.calls[('{0}/{1}/{2}' -f $m.Groups[2].Value.ToUpper(), $m.Groups[3].Value.ToUpper(), $m.Groups[5].Value)] = [long]$m.Groups[4].Value
    }
    # S5 spu_job_stuck (keep in step with watchdog_logic.py)
    $m = $RX_DISPATCH.Match($line)
    if ($m.Success) {
        $j = Get-Job $m.Groups[2].Value; $a = $m.Groups[1].Value
        $prev = @($j.open | Where-Object { $_[1] -eq $a } | ForEach-Object { $_[0] })
        if ($j.ret -eq 0 -and $prev.Count) { Add-Signal 'task_reuse_unreturned' $ln $line @{ image=$m.Groups[2].Value; args='0x'+$a; earlier_dispatches_never_returned=$prev } $false }
        $j.disp++; [void]$j.open.Add(@($ln, $a))
    }
    $m = $RX_RETURNED.Match($line)
    if ($m.Success) {
        $j = Get-Job $m.Groups[1].Value; $j.ret++
        if ($j.open.Count) { $j.open.RemoveAt(0) }
        if ($S.stuck -and $S.stuck.image -eq $m.Groups[1].Value) { $S.stuck = $null }
    }
    $m = $RX_SPUSPIN.Match($line)
    if ($m.Success) {
        $j = Get-Job $m.Groups[1].Value
        $det = [ordered]@{ image=$m.Groups[1].Value; pc='0x'+$m.Groups[2].Value; lr='0x'+$m.Groups[3].Value; ea='0x'+$m.Groups[4].Value; dispatched=$j.disp; returned=$j.ret }
        if ($j.ret -ge $JobMinReturns -and $j.open.Count -and -not $S.stuck) {
            $S.stuck = @{ ln=$ln; t=$S.now; image=$m.Groups[1].Value; text=$line; det=$det }
            Add-Signal 'spu_job_stuck' $ln $line $det $false
        } else { Add-Signal 'spu_spin_info' $ln $line $det $false }
    }
    if ($S.stuck) {
        $k = $S.stuck; $rule = $null
        if ($null -ne $k.t -and $null -ne $S.now -and ($S.now - $k.t) -ge $JobStuckSec * 1000) { $rule = "no RETURNED for ${JobStuckSec}s" }
        elseif ($null -eq $k.t -and ($ln - $k.ln) -ge $JobStuckLines) { $rule = "no RETURNED in $JobStuckLines lines (log has no clock)" }
        if ($rule -and -not ($S.signals | Where-Object { $_.signal -eq 'spu_job_stuck' -and $_.fires })) {
            $d = [ordered]@{}; foreach ($x in $k.det.Keys) { $d[$x] = $k.det[$x] }; $d.confirmed_at_line = $ln; $d.rule = $rule
            Add-Signal 'spu_job_stuck' $k.ln $k.text $d $true
        }
    }
    Invoke-Tick $ln
}

function Invoke-Tick($ln) {
    if ($null -eq $S.now) { return }
    if ($S.halt -and $null -ne $S.halt[1] -and ($S.now - $S.halt[1]) -ge $HaltGraceSec * 1000) {
        if (-not ($S.signals | Where-Object { $_.signal -eq 'spu_halt' -and $_.fires })) {
            Add-Signal 'spu_halt' $S.halt[0] ("halt at LS 0x{0} + {1}s grace" -f $S.halt[2], $HaltGraceSec) @{ pc='0x'+$S.halt[2] } $true
        }
    }
    $quiet = $null
    if ($S.lastProgress -and $null -ne $S.lastProgress[1]) { $quiet = ($S.now - $S.lastProgress[1]) / 1000.0 }
    if ($S.loading -and $null -ne $S.loading[1] -and ($S.now - $S.loading[1]) -le $LoadingHoldSec * 1000) {
        $ref = $S.loading[1]; if ($S.lastProgress -and $null -ne $S.lastProgress[1] -and $S.lastProgress[1] -gt $ref) { $ref = $S.lastProgress[1] }
        if (($S.now - $ref) -ge $NoProgressSec * 1000 -and $S.framesStalledSec -ge $NoProgressSec) {
            if (-not ($S.signals | Where-Object { $_.signal -eq 'loading_no_progress' })) {
                $lp = $null; if ($S.lastProgress) { $lp = $S.lastProgress[2] }
                Add-Signal 'loading_no_progress' $ln ("Now Loading (L{0}) and no progress line for {1}s" -f $S.loading[0], $NoProgressSec) @{ loading_line=$S.loading[0]; last_progress=$lp; frames_stalled_s=$S.framesStalledSec } $true
            }
        }
    }
    if ($S.live -and $null -ne $S.cpuCores -and $S.cpuWindowSec -ge $BusySec -and $S.cpuCores -ge $BusyCpu -and $null -ne $quiet -and $quiet -ge $BusySec -and $S.framesStalledSec -ge $BusySec) {
        if (-not ($S.signals | Where-Object { $_.signal -eq 'busy_spin' })) {
            Add-Signal 'busy_spin' $ln ("CPU {0:N2} cores for {1}s, no progress line for {2:N0}s, title unchanged {3:N0}s" -f $S.cpuCores, $BusySec, $quiet, $S.framesStalledSec) @{ cpu_cores=$S.cpuCores } $true
        }
    }
    # v2 frozen_busy: no new frame for FrozenSec while the process burns CPU, regardless of what the log prints
    if ($S.live -and $null -ne $S.cpuCores -and $S.cpuWindowSec -ge $BusySec -and $S.cpuCores -ge $BusyCpu -and $S.framesStalledSec -ge $FrozenSec -and -not [double]::IsInfinity($S.framesStalledSec)) {
        if (-not ($S.signals | Where-Object { $_.signal -eq 'frozen_busy' })) {
            Add-Signal 'frozen_busy' $ln ("title (FPS/draws) unchanged {0:N0}s with CPU {1:N2} cores" -f $S.framesStalledSec, $S.cpuCores) @{ cpu_cores=$S.cpuCores; title_unchanged_s=$S.framesStalledSec } $true
        }
    }
}

# ---------------------------------------------------------------- Report
function Write-HangReport($outDir, $proc, $logPath) {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    $S.tail.ToArray() | Set-Content -Encoding UTF8 (Join-Path $outDir 'last_2000.log')
    $blocks = @($S.lrcDone | ForEach-Object { ,$_ })
    if ($S.lrcCur -and $S.lrcCur.calls.Count -ge $S.lrcCur.pairs) { $blocks += ,$S.lrcText }
    $lrc = @(); foreach ($b in ($blocks | Select-Object -Last 2)) { $lrc += $b }
    if ($lrc.Count) { $lrc | Set-Content -Encoding UTF8 (Join-Path $outDir 'hle_lrc_last2.log') }
    $where = @('# where it spins (from existing log options; none of them changes the game)', '## hottest HLE call sites between the last two [hle-lrc] dumps (calls/s)')
    $where += ($S.spinTop | ForEach-Object { '{0,9}/s {1}({2}) lr={3} tid={4}' -f $_.per_s, $_.name, $_.nid, $_.lr, $_.tid })
    $where += '## [spu-spin] (an SPU re-issuing GETLLAR on one line 4M times)'; $where += $S.spuSpin
    $where += '## last [pcsample] lines (SPU_PCSAMPLE=<secs>)'; $where += ($S.pcsample | Select-Object -Last 64)
    $where += '## last [samp] lines (PS3_SAMPLE=<ms>)'; $where += ($S.samp | Select-Object -Last 80)
    $where | Set-Content -Encoding UTF8 (Join-Path $outDir 'spin_where.txt')
    $rep = [ordered]@{
        when = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'); pid = $(if ($proc) { $proc.Id } else { $null })
        exe = $(if ($proc) { try { $proc.Path } catch { $null } } else { $null }); log = $logPath
        fired = $S.fired; signals = @($S.signals | Select-Object -First 60)
        last_progress = $S.lastProgress; loading = $S.loading; spin_top = $S.spinTop
        cpu_cores = $S.cpuCores; frames_stalled_s = $S.framesStalledSec
        version = $VERSION
        jobs_open = @($S.jobs.Keys | Where-Object { $S.jobs[$_].open.Count } | ForEach-Object { '{0}: dispatched {1} returned {2} open at L{3}' -f $_, $S.jobs[$_].disp, $S.jobs[$_].ret, (($S.jobs[$_].open | ForEach-Object { $_[0] }) -join ',L') })
        thresholds = [ordered]@{ NoProgressSec=$NoProgressSec; JobMinReturns=$JobMinReturns; JobStuckSec=$JobStuckSec; JobStuckLines=$JobStuckLines; FrozenSec=$FrozenSec; EfBlockedSec=$EfBlockedSec; HaltGraceSec=$HaltGraceSec; BusyCpu=$BusyCpu; BusySec=$BusySec; SpinCallsPerSec=$SpinCallsPerSec; FlagEA=$FlagEA }
        title = $(if ($proc) { $proc.MainWindowTitle } else { $null }); actions = New-Object System.Collections.ArrayList
    }
    return $rep
}

function Save-Report($outDir, $rep) {
    ($rep | ConvertTo-Json -Depth 6) | Set-Content -Encoding UTF8 (Join-Path $outDir 'hang_report.json')
    $f = $rep.fired
    $txt = @("Strikeforce hang report  $($rep.when)  (watchdog $($rep.version))", "pid: $($rep.pid)   exe: $($rep.exe)", "log: $($rep.log)",
             "FIRED: $($f.signal) at log line $($f.line): $($f.text)", '', 'all signals (first 60):')
    $txt += ($rep.signals | ForEach-Object { '  {0} {1,-20} L{2} :: {3}' -f $(if ($_.fires) { 'FIRE' } else { 'seen' }), $_.signal, $_.line, $_.text })
    $txt += '', "last progress line: $($rep.last_progress -join ' | ')", "loading marker: $($rep.loading -join ' | ')",
            "cpu cores: $($rep.cpu_cores)   title unchanged s: $($rep.frames_stalled_s)   title: $($rep.title)", '',
            'SPU jobs dispatched but not RETURNED:'
    $txt += ($rep.jobs_open | ForEach-Object { "  $_" })
    $txt += '', 'actions:'
    $txt += ($rep.actions | ForEach-Object { "  $_" })
    $txt | Set-Content -Encoding UTF8 (Join-Path $outDir 'hang_report.txt')
}

function Show-ArabicMessage($signal, $outDir, $how) {
    $body = "اكتُشف تعليق في اللعبة (شاشة Now Loading أو شاشة سوداء).`n`nالإشارة: $signal`n`n$how`n`nالتقرير محفوظ في:`n$outDir"
    if ($NoMessage) { Write-Host $body; return }
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $opt = [System.Windows.Forms.MessageBoxOptions]::RtlReading -bor [System.Windows.Forms.MessageBoxOptions]::RightAlign
        [void][System.Windows.Forms.MessageBox]::Show($body, 'مراقب التعليق - Strikeforce', 'OK', 'Warning', 'Button1', $opt)
    } catch { Write-Host $body }
}

# ---------------------------------------------------------------- Replay (dry run)
if ($Replay) {
    $ln = 0
    foreach ($raw in [System.IO.File]::ReadLines((Resolve-Path $Replay))) {
        $ln++; $line = $raw.Replace([string][char]0, '')
        $n = $ln
        if ($ReplayStripPrefix -and $line -match '^(\d+):(.*)$') { $n = [long]$Matches[1]; $line = $Matches[2] }
        Feed-Line $n $line $null
    }
    Close-Lrc
    if (-not $OutDir) { $OutDir = Join-Path (Get-Location) 'hangwatch_replay' }
    $f = $S.fired
    Write-Host "watchdog $VERSION replay: $Replay"
    if ($f) { Write-Host ("FIRST FIRE: {0} at L{1} t={2}" -f $f.signal, $f.line, $f.t_ms) } else { Write-Host 'FIRST FIRE: none' }
    $seen = @{}
    foreach ($sg in $S.signals) { $k = "$($sg.signal)/$($sg.fires)"; if (-not $seen.ContainsKey($k)) { $seen[$k] = 1
        Write-Host ('  {0} {1,-20} L{2} t={3}' -f $(if ($sg.fires) { 'FIRE' } else { 'seen' }), $sg.signal, $sg.line, $sg.t_ms) } }
    foreach ($x in ($S.spinTop | Select-Object -First 3)) { Write-Host ('    {0}/s {1}({2}) lr={3} tid={4}' -f $x.per_s, $x.name, $x.nid, $x.lr, $x.tid) }
    if ($f) {
        $dir = Join-Path $OutDir ('hang_{0}_replay' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
        $S.tail = New-Object 'System.Collections.Generic.Queue[string]'; foreach ($x in $S.tailAtFire) { $S.tail.Enqueue($x) }   # lines up to the fire
        $rep = Write-HangReport $dir $null (Resolve-Path $Replay).Path
        [void]$rep.actions.Add('replay: no process; no close, no kill')
        Save-Report $dir $rep
        Write-Host "report: $dir"
        $NoMessage = $true; Show-ArabicMessage $f.signal $dir 'وضع التجربة: لم تُغلق أي عملية.'
    }
    exit 0
}

# ---------------------------------------------------------------- Live: launch or attach
$t0 = Get-Date
$baseDir = if ($Launch) { Split-Path -Parent (Resolve-Path $Launch) } elseif ($Log) { Split-Path -Parent (Split-Path -Parent (Resolve-Path $Log)) } else { (Get-Location).Path }
if (-not $LogDir) { $LogDir = Join-Path $baseDir 'play_logs' }
if (-not $OutDir) { $OutDir = if (Test-Path (Join-Path $baseDir 'sfauto')) { Join-Path $baseDir 'sfauto\hangwatch' } else { Join-Path $baseDir 'hangwatch' } }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$wlog = Join-Path $OutDir ('watchdog_{0}.log' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
function W($m) { $l = '{0} {1}' -f (Get-Date -Format 'HH:mm:ss'), $m; Write-Host $l; Add-Content -Encoding UTF8 $wlog $l }

$proc = $null
if ($AttachPid) { $proc = Get-Process -Id $AttachPid }
elseif ($Launch) {
    $full = (Resolve-Path $Launch).Path
    if ($full -match '\.(bat|cmd)$') {
        $cmd = Start-Process -FilePath $env:ComSpec -ArgumentList ('/c "' + $full + '" ' + $LaunchArgs) -WorkingDirectory (Split-Path -Parent $full) -PassThru
        W "launched $full via cmd pid $($cmd.Id)"
        for ($i = 0; $i -lt 120 -and -not $proc; $i++) {
            Start-Sleep -Milliseconds 500
            $kids = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($cmd.Id)" | Where-Object { $_.Name -notmatch '^(conhost|cmd|timeout|findstr|powershell)\.exe$' })
            if ($ProcName) { $kids = @($kids | Where-Object { $_.Name -eq "$ProcName.exe" }) }
            if ($kids.Count) { $proc = Get-Process -Id $kids[0].ProcessId -ErrorAction SilentlyContinue }
        }
        if (-not $proc) { throw 'game process not found under the launcher (use -ProcName or -AttachPid)' }
    } else {
        if (-not $Log) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null; $Log = Join-Path $LogDir ('watchdog_{0}_stderr.log' -f (Get-Date -Format 'yyyyMMdd-HHmmss')) }
        $proc = Start-Process -FilePath $full -ArgumentList $LaunchArgs -WorkingDirectory (Split-Path -Parent $full) -RedirectStandardError $Log -PassThru
    }
} else { throw 'give -Launch, -AttachPid or -Replay' }
W "watching pid $($proc.Id) $($proc.ProcessName)"

if (-not $Log) {
    for ($i = 0; $i -lt 120 -and -not $Log; $i++) {
        $c = Get-ChildItem -Path $LogDir -Filter '*stderr*.log' -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge $t0.AddSeconds(-5) } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($c) { $Log = $c.FullName } else { Start-Sleep -Milliseconds 500 }
    }
    if (-not $Log) { throw "no *stderr*.log written in $LogDir after start; pass -Log" }
}
W "tailing $Log"

$S.live = $true
$fs = $null
for ($i = 0; $i -lt 60 -and -not $fs; $i++) {
    try { $fs = New-Object System.IO.FileStream($Log, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, ([System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete)) }
    catch { Start-Sleep -Milliseconds 500 }
}
$rd = New-Object System.IO.StreamReader($fs, [System.Text.Encoding]::UTF8)
$frag = ''; $ln = 0
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$cpuQ = New-Object System.Collections.Queue
$lastTitle = $null; $titleSince = 0

function Read-New {
    $chunk = $rd.ReadToEnd()
    if (-not $chunk) { return }
    $chunk = $frag + $chunk.Replace([string][char]0, '')
    $parts = $chunk -split "`r?`n"
    $script:frag = $parts[-1]
    for ($j = 0; $j -lt $parts.Count - 1; $j++) { $script:ln++; Feed-Line $script:ln $parts[$j] $sw.ElapsedMilliseconds }
}

while ($true) {
    Read-New
    $proc.Refresh()
    if ($proc.HasExited) { W "game exited (code $($proc.ExitCode)); no hang caught"; exit 0 }
    if ($MaxMin -gt 0 -and ((Get-Date) - $t0).TotalMinutes -gt $MaxMin) { W 'max time reached; no hang caught'; exit 0 }
    $now = $sw.ElapsedMilliseconds
    # frames: the runtime refreshes the title (FPS/draws) once a second, only from its present path
    $title = $proc.MainWindowTitle
    if ($title -match 'FPS:') {
        if ($title -ne $lastTitle) { $lastTitle = $title; $titleSince = $now }
        $S.framesStalledSec = ($now - $titleSince) / 1000.0
    } else { $S.framesStalledSec = [double]::PositiveInfinity }   # no FPS title: log-only rules
    # CPU over a sliding window of BusySec
    $cpuQ.Enqueue(@($now, $proc.TotalProcessorTime.TotalMilliseconds))
    while ($cpuQ.Count -gt 2 -and ($now - $cpuQ.ToArray()[1][0]) -ge $BusySec * 1000) { [void]$cpuQ.Dequeue() }   # keep the newest sample that is >= BusySec old
    $first = $cpuQ.Peek()
    $S.cpuWindowSec = ($now - $first[0]) / 1000.0
    if ($S.cpuWindowSec -gt 0) { $S.cpuCores = ($proc.TotalProcessorTime.TotalMilliseconds - $first[1]) / ($now - $first[0]) }
    $S.now = $now
    Invoke-Tick $ln
    if ($S.fired) { break }
    Start-Sleep -Milliseconds $PollMs
}

# ---------------------------------------------------------------- Hang: report, copy, flush, close, message
$f = $S.fired
W "HANG: $($f.signal) at log line $($f.line): $($f.text)"
# where it spins: wait (read-only) for the next [hle-lrc] dump so the call-rate table covers the hung state
if ($S.lrcCur -and $SpinCaptureSec -gt 0) {
    $no0 = $S.lrcCur.no; $tEnd = $sw.ElapsedMilliseconds + $SpinCaptureSec * 1000
    while ($sw.ElapsedMilliseconds -lt $tEnd -and ($S.lrcCur.no -eq $no0 -or $S.lrcCur.calls.Count -lt $S.lrcCur.pairs)) { Start-Sleep -Milliseconds $PollMs; Read-New; $proc.Refresh(); if ($proc.HasExited) { break } }
    Close-Lrc
    W ("spin capture: [hle-lrc] dump {0} -> {1}" -f $no0, $S.lrcCur.no)
}
$dir = Join-Path $OutDir ('hang_{0}_pid{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'), $proc.Id)
# per-thread CPU (host thread ids, same ids as tid= in [cellSpurs] and [samp] tid lines): 3 x 1 s
$thr = @()
foreach ($k in 1..3) {
    $proc.Refresh(); $a = @{}; foreach ($t in $proc.Threads) { try { $a[$t.Id] = $t.TotalProcessorTime.TotalMilliseconds } catch {} }
    Start-Sleep -Seconds 1; $proc.Refresh()
    $row = foreach ($t in $proc.Threads) { try { if ($a.ContainsKey($t.Id)) { [pscustomobject]@{ tid=$t.Id; ms=[int]($t.TotalProcessorTime.TotalMilliseconds - $a[$t.Id]) } } } catch {} }
    $thr += ('sample {0}: ' -f $k) + (($row | Sort-Object ms -Descending | Select-Object -First 12 | ForEach-Object { '{0}:{1}ms' -f $_.tid, $_.ms }) -join ' ')
}
Read-New
$rep = Write-HangReport $dir $proc $Log
$thr | Set-Content -Encoding UTF8 (Join-Path $dir 'threads_cpu.txt')
[void]$rep.actions.Add('report + last_2000.log + hle_lrc_last2.log + spin_where.txt + threads_cpu.txt written')
# copy sfrace / ovl dumps if present (wait until they stop growing, max 10 s)
$cands = @($DumpPaths) + @((Join-Path $LogDir 'sfrace_*.log'), (Join-Path $LogDir 'ovl_sfrace'))
$dd = Join-Path $dir 'dumps'
foreach ($c in $cands) {
    foreach ($it in @(Get-Item -Path $c -ErrorAction SilentlyContinue)) {
        $sz = -1; for ($i = 0; $i -lt 20; $i++) { $n = (Get-ChildItem $it.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum; if ($n -eq $sz) { break }; $sz = $n; Start-Sleep -Milliseconds 500 }
        New-Item -ItemType Directory -Force -Path $dd | Out-Null
        Copy-Item -Path $it.FullName -Destination $dd -Recurse -Force
        [void]$rep.actions.Add("copied $($it.FullName)")
    }
}
# flush: the runtime has no external flush request; its stdio thread flushes every PS3_STDIO_FLUSH_MS (50 ms
# default) and exit() flushes again (atexit). So: wait 1 s, read what is new, and read again after the close.
[void]$rep.actions.Add('flush: no external flush hook in this runtime; waited 1 s for the 50 ms stdio flusher')
Start-Sleep -Seconds 1; Read-New
$how = 'تُركت اللعبة تعمل (-NoClose).'
if (-not $NoClose) {
    $ok = $false
    try { $ok = $proc.CloseMainWindow() } catch {}
    [void]$rep.actions.Add("close: WM_CLOSE sent=$ok (runtime path: window closed -> ps3_host_quit -> REQUEST_EXITGAME -> exit 0)")
    if ($ok -and $proc.WaitForExit($CloseWaitSec * 1000)) {
        [void]$rep.actions.Add("closed cleanly, exit code $($proc.ExitCode)"); $how = 'أُغلقت اللعبة بشكل طبيعي.'
    } else {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        [void]$proc.WaitForExit(10000)
        [void]$rep.actions.Add("did not exit in ${CloseWaitSec}s -> killed (Stop-Process -Force)"); $how = 'لم تُغلق اللعبة بشكل طبيعي، فأُنهيت بالقوة.'
    }
    Start-Sleep -Milliseconds 500
    $before = $ln; Read-New
    if ($ln -gt $before) { [void]$rep.actions.Add("read $($ln - $before) more log lines after the close") }
    $S.tail.ToArray() | Select-Object -Last ([math]::Max(1, $ln - $before + 50)) | Set-Content -Encoding UTF8 (Join-Path $dir 'post_close_tail.log')
}
$rd.Close(); $fs.Close()
Save-Report $dir $rep
W "report: $dir"
Show-ArabicMessage $f.signal $dir $how
exit 0
