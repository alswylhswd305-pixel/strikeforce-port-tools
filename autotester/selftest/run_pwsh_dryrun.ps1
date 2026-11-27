# Dry-run pad_driver + movie_guard on the box (no game).
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
. (Join-Path $root 'lib/movie_guard.ps1')

$fails = 0
function Ok($name, $cond) {
    if ($cond) { Write-Host "  OK  $name" } else { Write-Host "  FAIL $name"; $script:fails++ }
}

$st = @{ Active=$false; Unsure=$true; Starts=0; Stops=0; SeenMovieLog=$false; Reason='no-log-yet' }
Update-SfMovieState -State $st -Chunk "" -LogOk $true | Out-Null
Ok "empty chunk + log ok still unsure (no sf-movie lines)" ($st.Unsure -eq $true)
$blk = Test-SfPadBlocked -State $st
Ok "blocked when unsure" ($blk.Blocked -eq $true)

Update-SfMovieState -State $st -Chunk "[sf-movie] PlayerStart cmd start=1`n" -LogOk $true | Out-Null
Ok "start active" ($st.Active -eq $true -and $st.Unsure -eq $false)
Ok "blocked when active" ((Test-SfPadBlocked -State $st).Blocked -eq $true)

Update-SfMovieState -State $st -Chunk "[sf-movie] PlayerStop at clock 8.00`n" -LogOk $true | Out-Null
Ok "stop idle" ($st.Active -eq $false -and $st.Unsure -eq $false)
Ok "not blocked when idle" ((Test-SfPadBlocked -State $st).Blocked -eq $false)

Update-SfMovieState -State $st -Chunk "" -LogOk $false | Out-Null
Ok "unreadable log is unsure" ($st.Unsure -eq $true)

# Dry-run the boot sequence against a finished-movie log (should admit START).
$pad = Join-Path $PSScriptRoot 'dry_pad.txt'
$ev  = Join-Path $PSScriptRoot 'dry_events.jsonl'
if (Test-Path $pad) { Remove-Item $pad -Force }
if (Test-Path $ev) { Remove-Item $ev -Force }
$log = Join-Path $PSScriptRoot 'sample_stderr.log'
& (Join-Path $root 'lib/pad_driver.ps1') -Seq (Join-Path $root 'sequences/boot_to_start.padseq') -PadFile $pad -LogFile $log -EventLog $ev -DryRun
Ok "pad_driver dry-run exit 0" ($LASTEXITCODE -eq 0)
$evtxt = Get-Content $ev -Raw
Ok "dry-run recorded a press-dry for START" ($evtxt -match 'press-dry' -and $evtxt -match '0x8')
# Dry-run should not have written a real pad press into the file as a hold... WriteAllText is skipped in DryRun.
$padContent = if (Test-Path $pad) { Get-Content $pad -Raw } else { '' }
Ok "dry-run did not write pad.txt" ([string]::IsNullOrEmpty($padContent))

# Mid-movie log should block presses
$mid = Join-Path $PSScriptRoot 'mid_movie.log'
"[sf-movie] PlayerStart cmd start=1`n" | Set-Content $mid
if (Test-Path $ev) { Remove-Item $ev -Force }
& (Join-Path $root 'lib/pad_driver.ps1') -Seq (Join-Path $root 'sequences/menu_cross.padseq') -PadFile $pad -LogFile $mid -EventLog $ev -DryRun
# menu_cross has no wait, just press — must be blocked, exit 2
Ok "press blocked during PlayerStart (exit 2)" ($LASTEXITCODE -eq 2)
$evtxt = Get-Content $ev -Raw
Ok "event is press-blocked" ($evtxt -match 'press-blocked')

if ($fails -gt 0) { Write-Host "pwsh fails: $fails"; exit 1 }
Write-Host "pwsh dry-run selftest ok"
exit 0
