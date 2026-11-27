# Host loop for the NPC bot on the TEST COPY only.
# Reads guest memory (proven player XYZ at 0x008D3800), tails the stderr
# movie log, calls lib/npc_bot.py, writes sfauto\autotester\pad.txt.
# HARD GATE (also inside the Python brain): no presses while a movie is
# active or the movie state is unsure. Ollama (default qwen3:14b) sets
# tactics every -TacticSec seconds; reflexes run every -TickMs.
# Refuses a window titled "Saud plays". Refuses ringwatch_work\pad.txt.
# Does not launch the game. Does not change PLAY_Strikeforce.bat.
param(
    [int]$ProcId = 0,
    [string]$LogFile = '',
    [string]$PadFile = '',
    [int]$Seconds = 120,
    [int]$TickMs = 100,
    [double]$TacticSec = 2.5,
    [string]$Model = 'qwen3:14b',
    [string]$Fallback = 'qwen3.5:4b',
    [string]$HostUrl = 'http://127.0.0.1:11434',
    [string]$Goal = 'stay_village',
    [switch]$ForceMine,
    [switch]$DryRun,
    [string]$PromptStyle = 'auto',
    [string]$Mission = '',
    [string]$MissionsFile = '',
    [switch]$NoOllama
)

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$kit = Split-Path $here -Parent
. (Join-Path $here 'movie_guard.ps1')

$cs = Join-Path $here 'SFAT_VM.cs'
if (-not ([System.Management.Automation.PSTypeName]'SFAT_VM').Type) {
    Add-Type -Path $cs -ErrorAction Stop
}

$sf = '%SF_LOCAL_PATH%'
if (-not $PadFile) {
    if (Test-Path -LiteralPath (Join-Path $sf 'sfauto\autotester')) {
        $PadFile = Join-Path $sf 'sfauto\autotester\pad.txt'
    } else {
        $PadFile = Join-Path $kit 'pad_npc_bot.txt'
    }
}
$padNorm = [string]$PadFile
if ($padNorm.ToLower().Contains('\ringwatch_work\pad.txt') -or $padNorm.ToLower().Contains('/ringwatch_work/pad.txt')) {
    throw "refusing to write ringwatch_work\pad.txt. Use sfauto\autotester\pad.txt."
}

function Get-Target {
    if ($ProcId -gt 0) { return Get-Process -Id $ProcId -ErrorAction Stop }
    $p = Get-Process MyGameRecomp -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -like '*TEST-SALEM*' }
    if (-not $p) { throw 'ما لقيت نافذة [TEST-SALEM]' }
    if (@($p).Count -gt 1 -and -not $ForceMine) { throw 'more than one [TEST-SALEM]; pass -ProcId' }
    return ($p | Select-Object -First 1)
}

$py = $null
if (-not $DryRun) {
    $py = Get-Command python3, python -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $py) { throw 'python3/python not found; needed to run lib/npc_bot.py' }
}

$proc = $null
$vbOk = $false
if (-not $DryRun) {
    $proc = Get-Target
    if (-not $ForceMine -and $proc.MainWindowTitle -match 'Saud plays') {
        throw "refusing npc_bot on a 'Saud plays' window (pid $($proc.Id))"
    }
    [SFAT_VM]::Open($proc.Id)
    $vb = [SFAT_VM]::FindBase()
    if (-not $vb.Trim()) { throw 'no guest base (signature miss)' }
    [SFAT_VM]::VB = [Convert]::ToInt64($vb.Trim().Split(' ')[0], 16)
    $vbOk = $true
    Write-Host "npc_bot pid=$($proc.Id) title='$($proc.MainWindowTitle)' base=$($vb.Trim()) model=$Model"
}

if (-not $LogFile -and $proc) {
    $logs = Get-ChildItem (Join-Path $sf 'play_logs') -Filter 'autotest_*_stderr.log' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending
    if ($logs) { $LogFile = $logs[0].FullName }
}

$POS = 0x008D3800
$addrFile = Join-Path $kit 'data\godmode_addrs.json'
$hpEa = 0L
$hpKind = ''
$hpStatus = 'unconfirmed'
if (Test-Path $addrFile) {
    $cfg = Get-Content $addrFile -Raw | ConvertFrom-Json
    $hps = @($cfg.confirmed_hp)
    if ($hps.Count -gt 0) {
        $hpEa = [Convert]::ToInt64(($hps[0].ea -replace '0x',''), 16)
        $hpKind = [string]$hps[0].kind
        $hpStatus = 'confirmed'
    }
}

$movie = @{ Starts = 0; Stops = 0; Active = $false; Unsure = $true; SeenMovieLog = $false; Reason = 'no-log-yet'; LastEvent = '' }
$logOff = 0L
$runDir = Join-Path $kit ("reports\npc_" + (Get-Date -f 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $runDir -Force | Out-Null
$statePath = Join-Path $runDir 'state.json'
$eventsPath = Join-Path $runDir 'npc_bot.jsonl'
$brain = Join-Path $here 'npc_bot.py'
$t0 = Get-Date
$ticks = 0
$xyzStart = $null
$movieActiveSince = $null
if ($Mission) {
    Write-Host ("mission={0}" -f $Mission)
    if (-not $MissionsFile) {
        $cand = @(
            (Join-Path $kit 'data\missions.json')
        )
        foreach ($c in $cand) { if (Test-Path $c) { $MissionsFile = $c; break } }
    }
    if (-not $PSBoundParameters.ContainsKey('Seconds')) {
        if ($Mission -eq 'M1') { $Seconds = 480 }
        elseif ($Mission -eq 'M2') { $Seconds = 900 }
        elseif ($Mission -eq 'M3') { $Seconds = 720 }
        elseif ($Mission -eq 'M4') { $Seconds = 300 }
    }
}


Write-Host "log=$LogFile pad=$PadFile events=$eventsPath seconds=$Seconds"

while (((Get-Date) - $t0).TotalSeconds -lt $Seconds) {
    if ($proc -and -not (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) {
        Write-Host 'process exited'
        break
    }
    if ($LogFile) {
        $off = $logOff
        $tail = Get-SfLogTail -LogFile $LogFile -Offset ([ref]$off)
        $logOff = $off
        Update-SfMovieState -State $movie -Chunk $tail.Text -LogOk $tail.Ok | Out-Null
    } else {
        $movie.Unsure = $true
        $movie.Reason = 'no-logfile'
    }

    $x = $null; $y = $null; $z = $null; $hp = $null
    if ($vbOk) {
        $x = [double][SFAT_VM]::RF($POS)
        $y = [double][SFAT_VM]::RF($POS+4)
        $z = [double][SFAT_VM]::RF($POS+8)
        if ($hpStatus -eq 'confirmed' -and $hpEa -ne 0) {
            if ($hpKind -eq 'f32') { $hp = [double][SFAT_VM]::RF($hpEa) }
            else { $hp = [int64][SFAT_VM]::R32($hpEa) }
        }
    }

    $flags = @{ loading = $false; halt = $false; eventflag_wait = $false }
    if ($LogFile -and (Test-Path $LogFile)) {
        # Cheap tail window for halt/loading flags (last 64 KiB).
        $fs = [IO.File]::Open($LogFile, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
        try {
            $len = $fs.Length
            $start = [Math]::Max(0, $len - 65536)
            $fs.Seek($start, [IO.SeekOrigin]::Begin) | Out-Null
            $sr = New-Object IO.StreamReader($fs)
            $chunk = $sr.ReadToEnd()
            $sr.Close()
            if ($chunk -match 'SPU-HALT|0x31C20') { $flags.halt = $true }
            if ($chunk -match 'EventFlagWait') { $flags.eventflag_wait = $true }
            if ($chunk -match 'Now Loading|/cache/BLUS30471/') { $flags.loading = $true }
        } finally { $fs.Dispose() }
    }

    $elapsed = ((Get-Date) - $t0).TotalSeconds
    if ($movie.Active) {
        if (-not $movieActiveSince) { $script:movieActiveSince = Get-Date }
    } else { $script:movieActiveSince = $null }
    $movieActiveSec = 0
    if ($movieActiveSince) { $movieActiveSec = ((Get-Date) - $movieActiveSince).TotalSeconds }

    if ($vbOk -and -not $xyzStart -and $null -ne $x) {
        $script:xyzStart = @($x, $y, $z)
    }

    $logHits = @()
    if ($LogFile -and (Test-Path $LogFile)) {
        try {
            $fs2 = [IO.File]::Open($LogFile, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
            try {
                $len2 = $fs2.Length
                $st2 = [Math]::Max(0, $len2 - 65536)
                $fs2.Seek($st2, [IO.SeekOrigin]::Begin) | Out-Null
                $sr2 = New-Object IO.StreamReader($fs2)
                $tail2 = $sr2.ReadToEnd()
                $sr2.Close()
                foreach ($pat in @('BLUS30471/5443','BLUS30471/5444','SPU-HALT','0x31C20','EventFlagWait BLOCKED','frames decoded 0 shown 0')) {
                    if ($tail2 -and ($tail2.Contains($pat))) { $logHits += $pat }
                }
            } finally { $fs2.Dispose() }
        } catch {}
    }
    if ($flags.halt) { $logHits += 'SPU-HALT'; $logHits += '0x31C20' }
    if ($flags.eventflag_wait) { $logHits += 'EventFlagWait BLOCKED' }

    $state = [ordered]@{
        t = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + ' Asia/Kuwait (UTC+3)'
        movie = @{
            active = [bool]$movie.Active
            unsure = [bool]$movie.Unsure
            reason = [string]$movie.Reason
            starts = [int]$movie.Starts
            stops  = [int]$movie.Stops
        }
        player = @{
            x = $x; y = $y; z = $z
            hp = $hp; hp_ea = $(if ($hpStatus -eq 'confirmed') { '0x{0:X8}' -f $hpEa } else { $null })
            hp_status = $hpStatus
        }
        enemies = @()
        log_flags = $flags
        log_hits = $logHits
        elapsed_sec = [math]::Round($elapsed, 1)
        movie_active_sec = [math]::Round($movieActiveSec, 1)
        stuck_watch = @{
            xyz_start = $xyzStart
            xyz_now = $(if ($null -ne $x) { @($x, $y, $z) } else { $null })
            progress_elapsed_sec = [math]::Round($elapsed, 1)
            pos_eps = 50
        }
        goal = $Goal
        last_tactic = $null
    }
    if ($Mission) { $state['mission'] = @{ id = $Mission } }
    ($state | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath $statePath -Encoding UTF8

    if ($DryRun) {
        Write-Host ("dry tick movie active={0} unsure={1} reason={2} xyz={3} {4} {5}" -f $movie.Active, $movie.Unsure, $movie.Reason, $x, $y, $z)
    } else {
        $pargs = @($brain, '--tick', '--state', $statePath, '--pad', $PadFile, '--events', $eventsPath, '--host', $HostUrl, '--model', $Model, '--fallback', $Fallback, '--prompt-style', $PromptStyle)
        if ($Mission) { $pargs += @('--mission', $Mission) }
        if ($MissionsFile) { $pargs += @('--missions-file', $MissionsFile) }
        # Ask Ollama on the first tick and roughly every TacticSec thereafter.
        if (-not $NoOllama -and (($ticks -eq 0) -or (($ticks * $TickMs) % [int]($TacticSec * 1000) -lt $TickMs))) {
            $pargs += '--ollama'
        }
        $out = & $py.Source @pargs 2>&1 | Out-String
        Write-Host $out
        if ($out -match '"stop":\s*true') {
            Write-Host "mission stop requested (goal or fail) — releasing pads"
            if ($out -match '"needed":\s*true') {
                Write-Host "SCREENSHOT REQUESTED — please capture a PrintWindow shot of the test window now."
            }
            [IO.File]::WriteAllText($PadFile, '')
            $ticks++
            break
        }
    }
    $ticks++
    Start-Sleep -Milliseconds $TickMs
}

Write-Host "npc_bot done ticks=$ticks events=$eventsPath"
if ($py -and (Test-Path $eventsPath)) {
    Write-Host "---- ollama bake-off metrics ----"
    & $py.Source $brain '--summarize-events' $eventsPath
}
# Leave pad empty when we exit so a last press does not stick.
if (-not $DryRun -and $PadFile) {
    [IO.File]::WriteAllText($PadFile, '')
}
