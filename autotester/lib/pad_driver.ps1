# Closed-loop PAD_FILE driver for the Strikeforce test copy.
# Plays a .padseq file (or a single -Press) against a pad.txt that the game
# already has open via the PAD_FILE env var.
# NEVER writes pad during a movie/cutscene: watches [sf-movie] PlayerStart/Stop
# in the stderr log. If unsure, it does not press (see movie_guard.ps1).
# Does not launch the game. Does not touch other PIDs, RPCS3, Downloads, or
# PLAY_Strikeforce.bat. Default pad file is sfauto\autotester\pad.txt — never
# the live ringwatch_work\pad.txt used when Saud is playing.
#
# Usage:
#   pad_driver.ps1 -Seq path\to\file.padseq -Log path\to\stderr.log
#   pad_driver.ps1 -Press START -Hold 8 -Log ...
#   pad_driver.ps1 -Seq file.padseq -DryRun

param(
    [string]$Seq = '',
    [string]$Press = '',
    [int]$Hold = 0,
    [int]$Lx = -1,
    [int]$Ly = -1,
    [string]$PadFile = '',
    [string]$LogFile = '',
    [int]$ProcId = 0,
    [int]$DrainTimeoutSec = 8,
    [switch]$DryRun,
    [switch]$NoGuard,
    [string]$EventLog = ''
)

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
. (Join-Path $here 'movie_guard.ps1')

$buttonMap = @{
    SELECT=0x0001; L3=0x0002; R3=0x0004; START=0x0008
    UP=0x0010; RIGHT=0x0020; DOWN=0x0040; LEFT=0x0080
    L2=0x0100; R2=0x0200; L1=0x0400; R1=0x0800
    TRIANGLE=0x1000; CIRCLE=0x2000; CROSS=0x4000; SQUARE=0x8000
    STICK=0x10000
}

function Resolve-Mask([string]$tok) {
    if ($tok -match '^0x[0-9A-Fa-f]+$') { return [uint32]($tok) }
    $u = $tok.ToUpper()
    if ($buttonMap.ContainsKey($u)) { return [uint32]$buttonMap[$u] }
    throw "unknown button/mask: $tok"
}

# Refuse to drive the pad file Saud uses while playing.
$forbidden = @(
    '\sfauto\ringwatch_work\pad.txt',
    '/sfauto/ringwatch_work/pad.txt'
)

function Get-DefaultPad {
    $root = '%SF_LOCAL_PATH%'
    if ($env:SF_AT_PAD) { return $env:SF_AT_PAD }
    return $root
}

if (-not $PadFile) { $PadFile = Get-DefaultPad }
$padNorm = $PadFile.Replace('/','\')
foreach ($f in $forbidden) {
    if ($padNorm.ToLower().EndsWith($f.ToLower()) -or $padNorm.ToLower().Contains('\ringwatch_work\pad.txt')) {
        throw "refusing to write ringwatch_work\pad.txt (that file is for Saud's play session). Use sfauto\autotester\pad.txt."
    }
}

if (-not $EventLog) {
    $dir = Split-Path $PadFile -Parent
    if ($dir) { $EventLog = Join-Path $dir 'pad_events.jsonl' }
}

function Write-Event($kind, $detail) {
    $o = [ordered]@{
        ts = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss.fffK')
        kind = $kind
    }
    foreach ($k in $detail.Keys) { $o[$k] = $detail[$k] }
    $line = ($o | ConvertTo-Json -Compress)
    if ($EventLog) {
        $ed = Split-Path $EventLog -Parent
        if ($ed -and -not (Test-Path $ed)) { New-Item -ItemType Directory -Path $ed -Force | Out-Null }
        Add-Content -LiteralPath $EventLog -Value $line -Encoding UTF8
    }
    Write-Host $line
}

$movie = @{ Active = $false; Unsure = $true; Starts = 0; Stops = 0; SeenMovieLog = $false; Reason = 'no-log-yet' }
$logOff = [int64]0
# Prime movie state from the existing log (last 8 MiB), then follow from EOF.
# Starting at EOF alone would miss a movie that already started or already ended.
if ($LogFile -and (Test-Path -LiteralPath $LogFile)) {
    $fs = [IO.File]::Open($LogFile, 'Open', 'Read', 'ReadWrite')
    try {
        $len = $fs.Length
        $from = [Math]::Max([int64]0, $len - 8MB)
        $fs.Seek($from, 'Begin') | Out-Null
        $sr = New-Object IO.StreamReader($fs)
        $prime = $sr.ReadToEnd()
        $sr.Close()
        $logOff = $len
        Update-SfMovieState -State $movie -Chunk $prime -LogOk $true | Out-Null
    } finally { $fs.Dispose() }
}

function Refresh-Movie {
    if ($NoGuard) {
        $movie.Active = $false; $movie.Unsure = $false; $movie.Reason = 'NoGuard'
        return
    }
    if (-not $LogFile) {
        $movie.Unsure = $true; $movie.Reason = 'no-logfile'
        return
    }
    $off = $logOff
    $tail = Get-SfLogTail -LogFile $LogFile -Offset ([ref]$off)
    $script:logOff = $off
    Update-SfMovieState -State $movie -Chunk $tail.Text -LogOk $tail.Ok | Out-Null
}

function Wait-PadDrain([int]$hold) {
    $t0 = Get-Date
    while (((Get-Date) - $t0).TotalSeconds -lt $DrainTimeoutSec) {
        Start-Sleep -Milliseconds 50
        if (-not (Test-Path -LiteralPath $PadFile)) { break }
        $raw = [string](Get-Content -LiteralPath $PadFile -Raw -ErrorAction SilentlyContinue)
        if (-not $raw -or $raw.Trim().Length -eq 0) { break }
    }
    $n = if ($hold -gt 0) { $hold } else { 40 }
    Start-Sleep -Milliseconds ([int]($n * 16.7))
}

function Send-PadLine([uint32]$mask, [int]$hold, [int]$lx, [int]$ly, [string]$src) {
    Refresh-Movie
    $blk = Test-SfPadBlocked -State $movie
    if ($blk.Blocked) {
        Write-Event 'press-blocked' @{ mask = ('0x{0:X}' -f $mask); hold = $hold; why = $blk.Why; src = $src }
        return $false
    }
    if ($hold -le 0) { $hold = 40 }
    $line = ('0x{0:X} {1}' -f $mask, $hold)
    if ($lx -ge 0 -and $ly -ge 0) { $line = $line + " $lx $ly" }
    if ($DryRun) {
        Write-Event 'press-dry' @{ line = $line; src = $src }
        return $true
    }
    $dir = Split-Path $PadFile -Parent
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    # Set-Content can add a newline; cellPad fgets is fine with that.
    [IO.File]::WriteAllText($PadFile, $line)
    Write-Event 'press' @{ line = $line; src = $src; movie = $movie.Reason }
    Wait-PadDrain $hold
    return $true
}

function Wait-MovieEnd([int]$timeoutSec) {
    $t0 = Get-Date
    while (((Get-Date) - $t0).TotalSeconds -lt $timeoutSec) {
        Refresh-Movie
        if ($movie.SeenMovieLog -and -not $movie.Active -and $movie.Stops -gt 0) {
            Write-Event 'wait-movie-end' @{ ok = $true; starts = $movie.Starts; stops = $movie.Stops }
            return $true
        }
        Start-Sleep -Milliseconds 200
    }
    Refresh-Movie
    Write-Event 'wait-movie-end' @{ ok = $false; why = $movie.Reason; starts = $movie.Starts; stops = $movie.Stops; timeout = $timeoutSec }
    return $false
}

function Wait-LogPat([string]$pat, [int]$timeoutSec) {
    $t0 = Get-Date
    while (((Get-Date) - $t0).TotalSeconds -lt $timeoutSec) {
        $off = $logOff
        $tail = Get-SfLogTail -LogFile $LogFile -Offset ([ref]$off)
        $script:logOff = $off
        Update-SfMovieState -State $movie -Chunk $tail.Text -LogOk $tail.Ok | Out-Null
        if ($tail.Ok -and $tail.Text -match $pat) {
            Write-Event 'wait-log' @{ ok = $true; pattern = $pat }
            return $true
        }
        Start-Sleep -Milliseconds 200
    }
    Write-Event 'wait-log' @{ ok = $false; pattern = $pat; timeout = $timeoutSec }
    return $false
}

function Invoke-PadSeqFile([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) { throw "sequence not found: $path" }
    $n = 0; $ok = 0; $fail = 0; $blocked = 0
    $lines = Get-Content -LiteralPath $path
    foreach ($raw in $lines) {
        $n++
        $line = $raw.Trim()
        if (-not $line -or $line.StartsWith('#')) { continue }
        if ($line -match '^meta\s+') { Write-Event 'meta' @{ line = $line }; continue }
        $parts = $line -split '\s+'
        $cmd = $parts[0].ToLower()
        switch ($cmd) {
            'sleep' {
                $sec = [double]$parts[1]
                Write-Event 'sleep' @{ seconds = $sec }
                if (-not $DryRun) { Start-Sleep -Milliseconds ([int]($sec * 1000)) }
            }
            'press' {
                $mask = Resolve-Mask $parts[1]
                $h = 40; $lx_ = -1; $ly_ = -1
                if ($parts.Count -ge 3 -and $parts[2] -match '^\d+$') { $h = [int]$parts[2] }
                if ($parts.Count -ge 5) { $lx_ = [int]$parts[3]; $ly_ = [int]$parts[4] }
                $r = Send-PadLine $mask $h $lx_ $ly_ $line
                if ($r) { $ok++ } else { $blocked++ }
            }
            'stick' {
                $lx_ = [int]$parts[1]; $ly_ = [int]$parts[2]
                $h = 40
                if ($parts.Count -ge 4) { $h = [int]$parts[3] }
                $r = Send-PadLine 0x10000 $h $lx_ $ly_ $line
                if ($r) { $ok++ } else { $blocked++ }
            }
            'wait_movie_end' {
                $t = 180
                if ($parts.Count -ge 2) { $t = [int]$parts[1] }
                if ($DryRun) { Write-Event 'wait-movie-end' @{ dry = $true; timeout = $t } }
                elseif (-not (Wait-MovieEnd $t)) { $fail++; throw "wait_movie_end failed after ${t}s (will not press)" }
            }
            'wait_log' {
                $t = 60; $pat = ($parts | Select-Object -Skip 1) -join ' '
                if ($pat -match '^(.*)\s+timeout=(\d+)$') { $pat = $matches[1]; $t = [int]$matches[2] }
                elseif ($parts.Count -ge 3 -and $parts[-1] -match '^\d+$') {
                    $t = [int]$parts[-1]
                    $pat = ($parts[1..($parts.Count-2)] -join ' ')
                }
                if ($DryRun) { Write-Event 'wait-log' @{ dry = $true; pattern = $pat } }
                elseif (-not (Wait-LogPat $pat $t)) { $fail++; throw "wait_log failed: $pat" }
            }
            'wait_title' {
                $t = 60; $pat = ($parts | Select-Object -Skip 1) -join ' '
                if ($parts.Count -ge 3 -and $parts[-1] -match '^\d+$') {
                    $t = [int]$parts[-1]
                    $pat = ($parts[1..($parts.Count-2)] -join ' ')
                }
                if ($DryRun) { Write-Event 'wait-title' @{ dry = $true; pattern = $pat }; break }
                if ($ProcId -le 0) { throw "wait_title needs -ProcId" }
                $t0 = Get-Date; $hit = $false
                while (((Get-Date) - $t0).TotalSeconds -lt $t) {
                    $p = Get-Process -Id $ProcId -ErrorAction SilentlyContinue
                    if (-not $p) { throw "process $ProcId exited during wait_title" }
                    if ($p.MainWindowTitle -match $pat) { $hit = $true; break }
                    Start-Sleep -Milliseconds 250
                }
                Write-Event 'wait-title' @{ ok = $hit; pattern = $pat }
                if (-not $hit) { $fail++; throw "wait_title failed: $pat" }
            }
            default { throw "unknown command at line $n : $line" }
        }
    }
    Write-Event 'seq-done' @{ file = $path; ok = $ok; blocked = $blocked; fail = $fail }
    return @{ Ok = $ok; Blocked = $blocked; Fail = $fail }
}

# --- entry ---
Write-Event 'begin' @{ pad = $PadFile; log = $LogFile; seq = $Seq; dry = [bool]$DryRun; noguard = [bool]$NoGuard }
if ($Seq) {
    $res = Invoke-PadSeqFile $Seq
    if ($res.Fail -gt 0 -or ($res.Ok -eq 0 -and $res.Blocked -gt 0)) { exit 2 }
    exit 0
}
if ($Press) {
    $mask = Resolve-Mask $Press
    $h = if ($Hold -gt 0) { $Hold } else { 40 }
    $r = Send-PadLine $mask $h $Lx $Ly "cli:$Press"
    if ($r) { exit 0 } else { exit 2 }
}
Write-Host "usage: pad_driver.ps1 -Seq file.padseq -Log stderr.log"
exit 1
