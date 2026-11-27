# Launch gates for the autotester. Do not start MyGameRecomp unless all pass:
#  1) no MyGameRecomp process now
#  2) none has been seen for 5 continuous minutes (timer resets if one appears)
#  3) sfauto\gfx_runs_DONE.txt exists
#  4) no window titled like SFRACE / PLAY_Strikeforce_SFRACE
#  5) no other [TEST-SALEM] window
# Observes only; does not stop anyone else's process.

function Test-SfIdleGate {
    param(
        [string]$SfRoot = '%SF_LOCAL_PATH%',
        [int]$IdleMinutes = 5
    )
    $why = @()
    $procs = @(Get-Process MyGameRecomp -ErrorAction SilentlyContinue)
    $titles = @()
    foreach ($p in (Get-Process -ErrorAction SilentlyContinue)) {
        $t = $p.MainWindowTitle
        if ($t) { $titles += "$($p.Id)|$($p.ProcessName)|$t" }
    }
    $sfrace = @($titles | Where-Object { $_ -match 'SFRACE|PLAY_Strikeforce_SFRACE' })
    $salem = @($titles | Where-Object { $_ -match '\[TEST-SALEM\]' })
    $done = Test-Path -LiteralPath (Join-Path $SfRoot 'sfauto\gfx_runs_DONE.txt')

    $allowed = $true
    if ($procs.Count -gt 0) {
        $allowed = $false
        $why += "MyGameRecomp running: " + (($procs | ForEach-Object { "$($_.Id) '$($_.MainWindowTitle)'" }) -join '; ')
    }
    if (-not $done) { $allowed = $false; $why += 'sfauto\gfx_runs_DONE.txt missing' }
    if ($sfrace.Count -gt 0) { $allowed = $false; $why += 'SFRACE window present: ' + ($sfrace -join '; ') }
    if ($salem.Count -gt 0) { $allowed = $false; $why += '[TEST-SALEM] already open: ' + ($salem -join '; ') }

    return [pscustomobject]@{
        Allowed        = $allowed
        Why            = if ($why) { $why -join ' | ' } else { 'gates-pending-or-ok' }
        ProcessCount   = $procs.Count
        GfxRunsDone    = $done
        SfraceWindows  = $sfrace
        SalemWindows   = $salem
        IdleMinutes    = $IdleMinutes
        At             = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    }
}

function Wait-SfIdleGate {
    param(
        [string]$SfRoot = '%SF_LOCAL_PATH%',
        [int]$IdleMinutes = 5,
        [int]$PollSec = 15,
        [int]$MaxWaitMinutes = 180
    )
    $clearSince = $null
    $deadline = (Get-Date).AddMinutes($MaxWaitMinutes)
    while ((Get-Date) -lt $deadline) {
        $g = Test-SfIdleGate -SfRoot $SfRoot -IdleMinutes $IdleMinutes
        $busy = ($g.ProcessCount -gt 0) -or ($g.SfraceWindows.Count -gt 0) -or ($g.SalemWindows.Count -gt 0)
        if ($busy) {
            $clearSince = $null
            Write-Host "$(Get-Date -f HH:mm:ss) waiting: $($g.Why)"
        } else {
            if (-not $clearSince) { $clearSince = Get-Date }
            $mins = ((Get-Date) - $clearSince).TotalMinutes
            if ($g.GfxRunsDone -and $mins -ge $IdleMinutes) {
                Write-Host "$(Get-Date -f HH:mm:ss) idle gates passed ($([int]$mins) min clear, gfx_runs_DONE present)"
                return @{ Allowed = $true; Why = 'idle-gates-passed'; ClearMinutes = $mins }
            }
            $needDone = if ($g.GfxRunsDone) { '' } else { ', still need gfx_runs_DONE.txt' }
            Write-Host "$(Get-Date -f HH:mm:ss) no game for $([math]::Round($mins,2)) min (need $IdleMinutes)$needDone"
        }
        Start-Sleep -Seconds $PollSec
    }
    return @{ Allowed = $false; Why = "timeout after $MaxWaitMinutes min" }
}
