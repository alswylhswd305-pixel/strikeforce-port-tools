# Replay one Strikeforce pad sequence with one command (test copy only).
# Does not launch the game unless -Launch is passed, and -Launch is refused
# unless the idle gates pass (no MyGameRecomp for 5 continuous minutes,
# gfx_runs_DONE.txt present, no SFRACE window). Prefer attaching to a tester
# window that was already started with PAD_FILE pointing at autotester\pad.txt.
#
# One-command examples (PowerShell, test copy):
#   .\replay.ps1 -Seq sequences\boot_to_start.padseq -Log %SF_LOCAL_PATH%
#   .\replay.ps1 -Seq sequences\boot_to_start.padseq -Log <stderr> -DryRun
#
# The game must have been started with:
#   PAD_FILE=<test>\sfauto\autotester\pad.txt
#   SF_MOVIE_LOG=1
# Never uses ringwatch_work\pad.txt.

param(
    [Parameter(Mandatory=$true)][string]$Seq,
    [string]$Log = '',
    [string]$PadFile = '',
    [int]$ProcId = 0,
    [switch]$DryRun,
    [switch]$Launch,
    [switch]$NoGuard
)

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$driver = Join-Path $here 'lib\pad_driver.ps1'
if (-not (Test-Path $driver)) { throw "missing $driver" }

$sf = '%SF_LOCAL_PATH%'
if (-not $PadFile) { $PadFile = Join-Path $sf 'sfauto\autotester\pad.txt' }

if ($Launch) {
    $wait = Join-Path $here 'lib\wait_idle.ps1'
    . $wait
    $g = Test-SfIdleGate -SfRoot $sf
    if (-not $g.Allowed) { throw "launch refused: $($g.Why)" }
    throw "replay.ps1 -Launch is not wired to start a window here; use tester.ps1 for a full run, or start the AUTOTEST launcher yourself and rerun without -Launch."
}

if ($ProcId -le 0 -and -not $DryRun) {
    $p = Get-Process MyGameRecomp -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -like '*TEST-SALEM*' } |
        Select-Object -First 1
    if ($p) { $ProcId = $p.Id }
}

if (-not $Log -and $ProcId -gt 0) {
    # Best-effort: newest autotest/movie stderr in play_logs.
    $logs = Get-ChildItem (Join-Path $sf 'play_logs') -Filter '*stderr.log' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending
    if ($logs) { $Log = $logs[0].FullName }
}

$args = @{
    Seq = (Resolve-Path $Seq).Path
    PadFile = $PadFile
    LogFile = $Log
    ProcId = $ProcId
}
if ($DryRun) { $args.DryRun = $true }
if ($NoGuard) { $args.NoGuard = $true }
& $driver @args
exit $LASTEXITCODE
