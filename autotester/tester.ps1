# Strikeforce auto play-tester (TEST COPY only).
# Launches ONE [TEST-SALEM] AUTOTEST window, runs the mission-1 route,
# captures PrintWindow shots, writes a short report, then closes only the
# window it started. Never touches PLAY_Strikeforce.bat, RPCS3, Downloads,
# Saud's game files, or any PID it did not start.
#
# Launch gates (hard): no MyGameRecomp for 5 continuous minutes AND
# sfauto\gfx_runs_DONE.txt exists AND no SFRACE window. Use -DryRun to
# exercise the route/parser without starting the game. Use -SkipWait only
# with -DryRun.
param(
    [switch]$DryRun,
    [switch]$SkipWait,
    [switch]$NoClose,
    [string]$Route = '',
    [int]$MaxSeconds = 600
)

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$sf = '%SF_LOCAL_PATH%'
if (-not (Test-Path -LiteralPath $sf)) { $sf = $here }  # box dry-run: no C: drive
. (Join-Path $here 'lib\wait_idle.ps1')

if (-not $Route) { $Route = Join-Path $here 'data\route_mission1.json' }
$runId = Get-Date -f 'yyyyMMdd-HHmmss'
$runDir = Join-Path $here "reports\run_$runId"
$shotDir = Join-Path $runDir 'shots'
New-Item -ItemType Directory -Path $shotDir -Force | Out-Null

$report = [ordered]@{
    run_id = $runId
    time_asia_kuwait = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + ' Asia/Kuwait (UTC+3)'
    dry_run = [bool]$DryRun
    how_far = 'not-started'
    blocked = @()
    steps = @()
    pid = 0
    log = ''
    shots = @()
}
$proc = $null
$log = ''
$atPad = Join-Path $sf 'sfauto\autotester\pad.txt'

function Add-Block($msg) { $script:report.blocked += $msg; Write-Host "BLOCKED: $msg" }
function Write-Step($id, $ok, $detail) {
    $script:report.steps += [pscustomobject]@{ id=$id; ok=$ok; detail=$detail }
    Write-Host ("step {0}: {1} — {2}" -f $id, $(if($ok){'ok'}else{'fail'}), $detail)
}

function Complete-Run {
    param([int]$code = 0)
    $covOut = Join-Path $runDir 'coverage.json'
    $covTxt = Join-Path $runDir 'coverage.txt'
    if ($log -and (Test-Path $log)) {
        $py = Get-Command python3, python -ErrorAction SilentlyContinue | Select-Object -First 1
        $cov = Join-Path $here 'lib\coverage.py'
        $names = Join-Path $here 'data\nid_names.json'
        $prev = Join-Path $here 'reports\coverage_last.json'
        if ($py) {
            $cargs = @($cov, $log, '--names', $names, '--out', $covOut, '--txt', $covTxt)
            if (Test-Path $prev) { $cargs += @('--prev', $prev) }
            & $py.Source @cargs
            if (Test-Path $covOut) { Copy-Item $covOut $prev -Force }
        }
    } elseif ($DryRun) {
        "dry-run: no coverage log" | Set-Content $covTxt
    }
    $reportPath = Join-Path $runDir 'report.json'
    ($report | ConvertTo-Json -Depth 8) | Set-Content $reportPath -Encoding UTF8
    $ar = @()
    $ar += "تقرير مختبر اللعبة — $runId — $($report.time_asia_kuwait)"
    $ar += "وصل إلى: $($report.how_far)"
    if ($report.pid) { $ar += "رقم العملية اللي فتحناها: $($report.pid)" }
    if ($report.log) { $ar += "اللوق: $($report.log)" }
    if ($report.blocked) { $ar += "موقوف: " + ($report.blocked -join ' ؛ ') }
    $ar += "الخطوات: $($report.steps.Count) — اللقطات: $($report.shots.Count)"
    $ar += "وضع عدم الموت: غير مؤكد للحين (ما انمسك عنوان الصحة)."
    $ar += "النقل: العنوان 0x008D3800 مجرب، بس ما عندنا إلا X=6499.8 بدون Y/Z."
    $ar += "تغطية الدوال: شوف coverage.txt — نسخة الأفلام v5 قد ما فيها SF_HLE_LRLOG."
    $ar += "أداة إعادة التشغيل (للباحثين): /workspace/sf-shared/replay/ — أمر واحد: replay.ps1 -Seq <ملف.padseq> -Log <stderr.log>"
    $ar -join "`n" | Set-Content (Join-Path $runDir 'report_ar.txt') -Encoding UTF8
    Write-Host "----"
    Get-Content (Join-Path $runDir 'report_ar.txt')
    Write-Host "---- report: $reportPath"
    if ($proc -and -not $DryRun -and -not $NoClose) {
        Write-Host "closing our pid $($proc.Id) only"
        Stop-Process -Id $proc.Id -ErrorAction SilentlyContinue
        Get-Process cmd, powershell -ErrorAction SilentlyContinue |
            Where-Object { $_.MainWindowTitle -like '*AUTOTEST*' -and $_.Id -ne $PID } |
            ForEach-Object { Stop-Process -Id $_.Id -ErrorAction SilentlyContinue }
    }
    exit $code
}

if ($SkipWait -and -not $DryRun) {
    throw '-SkipWait is only allowed with -DryRun (must not launch against a live session).'
}

if (-not $DryRun) {
    Write-Host 'waiting for idle gates (no MyGameRecomp for 5 min, gfx_runs_DONE, no SFRACE)...'
    $g = Wait-SfIdleGate -SfRoot $sf -IdleMinutes 5
    if (-not $g.Allowed) { Add-Block $g.Why; $report.how_far = 'idle-gate'; Complete-Run 2 }
} else {
    $g = Test-SfIdleGate -SfRoot $sf
    Write-Host "DryRun gate snapshot: allowed=$($g.Allowed) $($g.Why)"
}

$atDir = Join-Path $sf 'sfauto\autotester'
$state = Join-Path $sf 'sfauto\state_autotest'
if (-not $DryRun) {
    if (-not (Test-Path $atDir)) { New-Item -ItemType Directory -Path $atDir -Force | Out-Null }
    if (-not (Test-Path $state)) {
        $srcState = Join-Path $sf 'sfauto\state_movie1786'
        if (Test-Path $srcState) {
            Write-Host "copying state_movie1786 -> state_autotest (not the live ringwatch state)"
            Copy-Item $srcState $state -Recurse -ErrorAction SilentlyContinue
        } else { New-Item -ItemType Directory -Path $state -Force | Out-Null }
    }
    [IO.File]::WriteAllText($atPad, '')
}

if (-not $DryRun) {
    $bat = Join-Path $here 'PLAY_Strikeforce_AUTOTEST.bat'
    if (-not (Test-Path $bat)) { Add-Block "missing $bat"; $report.how_far = 'no-launcher'; Complete-Run 2 }
    $before = @(Get-Process MyGameRecomp -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
    Start-Process -FilePath $bat -WorkingDirectory (Split-Path $bat) | Out-Null
    $deadline = (Get-Date).AddMinutes(2)
    while ((Get-Date) -lt $deadline) {
        $now = @(Get-Process MyGameRecomp -ErrorAction SilentlyContinue)
        $mine = @($now | Where-Object { $before -notcontains $_.Id })
        if ($mine.Count -ge 1) { $proc = $mine[0]; break }
        Start-Sleep -Milliseconds 400
    }
    if (-not $proc) { Add-Block 'MyGameRecomp did not start'; $report.how_far = 'no-process'; Complete-Run 2 }
    $report.pid = $proc.Id
    Start-Sleep -Seconds 2
    $logs = Get-ChildItem (Join-Path $sf 'play_logs') -Filter 'autotest_*_stderr.log' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending
    if ($logs) { $log = $logs[0].FullName; $report.log = $log }
    Write-Host "started pid=$($proc.Id) log=$log"
}

function Invoke-Shot([string]$name, [string]$label) {
    $out = Join-Path $shotDir "$name.png"
    if ($DryRun -or -not $proc) {
        $script:report.shots += @{ name=$name; path=$out; dry=$true; label=$label }
        return
    }
    $shot = Join-Path $here 'lib\shot.ps1'
    & $shot -ProcId $proc.Id -Out $out | Out-Null
    $client = $out -replace '\.png$','_client.png'
    $src = if (Test-Path $client) { $client } else { $out }
    $script:report.shots += @{ name=$name; path=$src; label=$label }
    $ann = Join-Path $runDir 'annotations_pending.json'
    $item = @{ src=$src; dst=(Join-Path $shotDir "${name}_annotated.png"); boxes=@(@(40,40,1240,680)); labels=@($label) }
    $list = @()
    if (Test-Path $ann) { $list = @(Get-Content $ann -Raw | ConvertFrom-Json) }
    $list += $item
    ($list | ConvertTo-Json -Depth 6) | Set-Content $ann -Encoding UTF8
}

function Game-Alive {
    if ($DryRun) { return $true }
    return [bool](Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)
}

function Log-Has([string[]]$pats) {
    if (-not $log -or -not (Test-Path $log)) { return $false }
    $t = [IO.File]::ReadAllText($log)
    foreach ($p in $pats) { if ($t -match $p) { return $true } }
    return $false
}

function Invoke-Seq([string]$seqPath) {
    $drv = Join-Path $here 'lib\pad_driver.ps1'
    $par = @{ Seq=$seqPath; PadFile=$atPad; LogFile=$log }
    if ($proc) { $par.ProcId = $proc.Id }
    if ($DryRun) { $par.DryRun = $true }
    & $drv @par
    return $LASTEXITCODE
}

$routeObj = Get-Content $Route -Raw | ConvertFrom-Json
$how = 'route-start'
foreach ($st in $routeObj.steps) {
    if (-not (Game-Alive)) { Add-Block "process exited before $($st.id)"; $how = "exited-before-$($st.id)"; break }
    $seq = $st.seq
    if ($seq -and -not [IO.Path]::IsPathRooted($seq)) { $seq = Join-Path $here $seq }
    if ($seq -and (Test-Path $seq)) {
        try {
            $ec = Invoke-Seq $seq
            Write-Step $st.id ($ec -eq 0 -or $DryRun) "seq $($st.seq) exit=$ec"
            if ($ec -ne 0 -and -not $DryRun) { $how = "failed-$($st.id)"; break }
        } catch {
            Write-Step $st.id $false "$_"
            if (-not $DryRun) { $how = "failed-$($st.id)"; break }
        }
    } else {
        Write-Step $st.id $true "no-pad $($st.kind)"
    }
    if ($st.shot) { Invoke-Shot $st.id $st.label_ar }
    if ($st.watch_log -and -not $DryRun) {
        if (Log-Has @($st.watch_log)) {
            Write-Step "$($st.id)-watch" $true "gate/watch pattern hit"
            $how = "stopped-at-$($st.id)"
            if ($st.stop_on_hit) { break }
        }
    }
    $how = "after-$($st.id)"
}

$report.how_far = $how
$code = 0
if ($report.blocked.Count -gt 0 -and $report.how_far -ne 'idle-gate') { $code = 2 }
Complete-Run $code
