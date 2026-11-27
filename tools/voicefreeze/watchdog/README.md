# sf_hang_watchdog: detect-and-stop for the Strikeforce "Now Loading" and black-screen hangs (test copy)

**Version v2 2026-11-27** (v1 = the first five signals). v2 adds `spu_job_stuck`, `frozen_busy`, three heartbeat patterns, and the seen-only `task_reuse_unreturned` / `spu_spin_info`, for the 18:17 black hang (`../blackhang_1817.md`). Checksums are at the end.

**What it does:** it watches the game, and when the hang is real it saves a report, closes the game (or kills it) and shows an Arabic message.

**What it never does:**
- write game memory, inject code, press keys, or set env vars for the game;
- skip, force or fake anything.

It reads only these things:
- the stderr log (shared read);
- process and thread CPU times;
- the window title. The runtime refreshes `... | FPS: x | draws: n | WxH` once a second, from its present path only, so an unchanged title means no new frames.

## Files
| File | What |
|---|---|
| `sf_hang_watchdog.ps1` | the watchdog (Windows PowerShell 5.1 or pwsh 7; UTF-8 with BOM, CRLF) |
| `watchdog_logic.py` | box-side Python port of the same detection rules (replay a saved log) |
| `check_hang_reports.py` | box-side checker for saved hang reports; reuses `../voice_freeze_analyzer.py` and `../race_check.py` |
| `sampler_hook_spec.md` | existing "where it spins" log options + one minimal new per-thread sampler hook (log-only) |
| `tests/fake_game.py` | box-only harness: plays a saved log into a file, then hangs (busy or blocked), for a live pwsh test |

## How Salem runs it (Saud's PC, test copy)
Launch the game through the watchdog. It runs the launcher as-is and finds `MyGameRecomp.exe` under it, plus the newest `play_logs\*stderr*.log`:
```
powershell -NoProfile -ExecutionPolicy Bypass -File sf_hang_watchdog.ps1 -Launch <TEST_COPY>\PLAY_Strikeforce_VOICEDIAG1786_PAD.bat
```
Or attach to a running game:
```
powershell -NoProfile -ExecutionPolicy Bypass -File sf_hang_watchdog.ps1 -AttachPid <pid> -Log C:\...\play_logs\voicediag1786_saud_<ts>_stderr.log
```
Useful switches:
- v2: `-JobMinReturns 50`, `-JobStuckSec 10`, `-JobStuckLines 200` (replay without a clock), `-FrozenSec 45`.
- `-NoProgressSec 20`, `-EfBlockedSec 5`, `-HaltGraceSec 5`, `-BusyCpu 0.5`, `-BusySec 20`, `-SpinCallsPerSec 40000`: thresholds.
- `-CloseWaitSec 20`: wait after WM_CLOSE before killing.
- `-SpinCaptureSec 25`: after a fire, wait for one more `[hle-lrc]` dump.
- `-DumpPaths <paths>`: extra files or dirs to copy.
- `-NoClose`: report only, leave the game running.
- `-NoMessage`: no message box.
- `-MaxMin <n>`: stop watching after n minutes.

Reports go to `<game dir>\sfauto\hangwatch\hang_<yyyyMMdd-HHmmss>_pid<pid>\`. Copy that folder to the box at `/workspace/sf-shared/testloop/hangwatch/`.

**Optional, for "where it spins":** these are existing log options, set in a copy of the launcher, never by the watchdog.
- `SF_HLE_LRLOG=1` is already on in VOICEDIAG1786. `SF_HLE_LRLOG_DUMP=10` gives finer call rates.
- `SPU_PCSAMPLE=2`.
- `PS3_SAMPLE=5`. It suspends threads briefly to sample them, so a sampled run is a slightly different run.

See `sampler_hook_spec.md`.

## Detection rules (same regexes in the .ps1 and watchdog_logic.py)
| Signal | Fires when | Log lines it reads (real formats) |
|---|---|---|
| `ef_blocked` | a BLOCKED line on flag 0x00DBA900 with N >= `EfBlockedSec` (5) | `[cellSpurs] EventFlagWait BLOCKED tid=<host> Ns on pattern 0x0001 (...) flagEA=0x00DBA900 ...` (cellSpurs.c prints once a second, at most 24 lines per process) |
| `spu_halt` | `HaltGraceSec` (5) after an SPU halt | `[SPU-HALT] img= pc=`, `[SPU-TRACE] halt at LS 0x...`, or `[spu] img=N branched into unlifted LS 0xA ...` whose next `LS[0xA]: W` word is a conditional halt (heqi/hgti/hlgti/heq/hgt/hlgt; 7F003200 = heqi r100,0) |
| `loading_no_progress` | a Now Loading marker in the last `LoadingHoldSec` (300), no progress line for `NoProgressSec` (20), and (live) the FPS title unchanged for as long | marker: `[fs] open '/dev_hdd1/cache/BLUS30471/<n>'` (5444/5443 at the gate) or the text "now loading" |
| `busy_spin` (live) | process CPU >= `BusyCpu` cores over `BusySec` (20), no progress line for `BusySec`, FPS title unchanged for `BusySec` | Get-Process TotalProcessorTime + MainWindowTitle |
| `spu_job_stuck` (v2) | a `[spu-spin]` for an image with >= `JobMinReturns` (50) completed runs whose current run (dispatched, not RETURNED) still has not RETURNED after `JobStuckSec` (10 s); in a replay with no t= clock, after `JobStuckLines` (200) lines | `[spu_workload] dispatch HIT (async) fp= args=0x.. image=N`, `[spu_workload] async image=N RETURNED`, `[spu-spin] img=N pc= lr= GETLLAR ea=` (printed once per host thread after 4M re-reads of one line). Persistent tasks (0 returns) only give `spu_spin_info`. |
| `frozen_busy` (v2, live) | FPS title unchanged for `FrozenSec` (45) and CPU >= `BusyCpu` over `BusySec`, whatever the log prints | MainWindowTitle + TotalProcessorTime |
| `task_reuse_unreturned` (seen only) | a dispatch with the same image+args as an earlier dispatch that never RETURNed (taskset re-created at the same EA) | dispatch / RETURNED lines |
| `busy_spin_hle` | two consecutive complete `[hle-lrc]` dumps, no progress line between them, one (nid, lr, tid) >= `SpinCallsPerSec` (40000) | `[hle-lrc] dump=N t= pairs=P` + `[hle-lrc] N 0xNID 0xLR count ret= tid=` |

**Progress line** means any line that is not a timer heartbeat. These lines keep printing while the game is hung, so they do not count as progress: `[vm-sum]`, `[hle-lrc]`, `EventFlagWait BLOCKED`, `[spu_workload] task N ... sleeping Ns`, `[samp]`, `[pcsample]`, `[spu-spin]`, `[sfrace*]`, blank lines, and (v2) `[WAIT] event_queue_receive(...)`, `[spu_workload] WAIT_SIGNAL#...`, `[cellAtrac] Atrac3/3+: ...` decoder errors. The 18:17 black hang kept printing these, so v1's busy rule never saw a quiet log. If there is no FPS title (no window), the frame condition is skipped and the log-only rules still apply.

## On detection (in this order)
1. **Capture where it spins.** It waits up to `SpinCaptureSec` for the next complete `[hle-lrc]` dump, then takes 3 × 1 s per-thread CPU samples (host thread ids, the same ids as `tid=` in `[cellSpurs]` and `[samp]`).
2. **Write the report.** Files: `hang_report.txt` / `.json` (version, the SPU jobs dispatched but not RETURNED, fired signal, line, text, all signals seen, pid, exe, log, thresholds, CPU, title, actions), `last_2000.log`, `hle_lrc_last2.log`, `spin_where.txt`, `threads_cpu.txt`.
3. **Copy dumps if present.** `play_logs\sfrace_*.log` and `play_logs\ovl_sfrace\` (race_run_spec.md), plus `-DumpPaths`. It waits until they stop growing (max 10 s) and copies them to `dumps\`.
4. **Flush.** The runtime has **no external flush request**. Its stdio thread flushes every `PS3_STDIO_FLUSH_MS` (50 ms by default; ps3_stdio.c), and `exit()` flushes again through atexit. So the watchdog waits 1 s, then reads the log again after the close (`post_close_tail.log`).
5. **Close the game.**
   - `CloseMainWindow()` sends WM_CLOSE, which the runtime handles as "window closed": `ps3_host_quit` → REQUEST_EXITGAME → PS3_QUIT_GRACE_MS (3 s) → `exit(0)`.
   - If the game has not exited after `CloseWaitSec`, it runs `Stop-Process -Force`.
   - Which one happened is written in the report.
6. **Show the message.** An Arabic message box (RTL) names the signal, the report folder, and whether the game closed cleanly or was killed.

## Box checks
```
python3 watchdog_logic.py --selftest
python3 watchdog_logic.py LOG [--strip-prefix]                 # replay a saved log
pwsh -File sf_hang_watchdog.ps1 -Replay LOG -OutDir /tmp/hw     # same rules in the .ps1 itself (dry run, writes a report)
python3 check_hang_reports.py /workspace/sf-shared/testloop/hangwatch
python3 check_hang_reports.py --selftest
```
pwsh 7.4.6 is unpacked on the box at `/workspace/tools/pwsh/pwsh`.

## Verified on the box (2026-11-27, Asia/Kuwait)
**v2 (18:30 Asia/Kuwait):** the .ps1 replay and the Python port agree on every log below.
- `testloop/saud_blackhang_1817_stderr.log` (109,558 lines, no clock after L132):
  - first fire `spu_job_stuck` at L108150 (img 437063289, 14,897 dispatched / 14,896 RETURNED; confirmed at L108350);
  - nothing fires in L1-108149;
  - seen: `task_reuse_unreturned` at L47344, L106822, L106846, L106847, and `spu_spin_info` at L107252 and L108353.
- 17:27 log: first fire still `spu_halt` at L75722. `spu_job_stuck` is seen at L76798 and fires after spu_halt and ef_blocked. Nothing fires before L75722.
- live_1835 extract, gJ, 1786 diag extract: unchanged from v1.
- Scan of 27 box logs/extracts that contain dispatch lines: no new fire. `freeze-1555/gE/stderr_37800_39200.txt` sees `spu_job_stuck` at L1280; that was a real freeze (PPU put==get), and the extract is too short to confirm.
- Live: pwsh attached to `tests/fake_game.py` playing the 18:17 log up to L108160, then spinning. `spu_job_stuck` fired 10 s after the spin line; report and kill path OK.
- `frozen_busy` needs a window title, so it is Windows-only and not tested.

**v1:**
The .ps1 replay and the Python port give the same results.

**Saud 17:27 log** (`testloop/voicediag1786_saud_20261127-172741_stderr.log`, 92,468 lines):
- `spu_halt` is seen at L75722 (`LS[0x31C20]: 7F003200`) and fires after the 5 s grace.
- `ef_blocked` fires at L76814 (BLOCKED 5s on 0x00DBA900).
- `loading_no_progress` fires at L78024 (marker L73763 `5443`; last progress line L76787).
- `busy_spin_hle` fires at L78050 (dump 6→7: tid 17 at 65,283 calls/s each of sys_ppu_thread_get_id@0x53584, sys_lwmutex_lock@0x58C38 and sys_lwmutex_unlock@0x58CE4).
- No signal fired during the first 75,721 lines, which include the earlier, completed loading at L43879/43897.

**Other logs:**
- `freeze-1555/live_1835/halt_diag_extract.txt` (`--strip-prefix`): `spu_halt` is seen at L66154; `ef_blocked` fires at L66555. The extract has no t= clock, so the grace cannot elapse.
- `freeze-1555/gJ/ev/stderr_halt_trace.txt`: halt seen, no fire (86 lines, no EF lines).
- `testloop/reports/voicediag1786_diag_lines.txt` (1786 run, no freeze): nothing fired. This file is a filtered diag extract, so it is a weak negative control.

**Live test** with pwsh on Linux and `tests/fake_game.py`:
- tailing and per-line rules;
- `busy_spin` at 1.0 core with no progress;
- `ef_blocked`;
- the dump copy;
- the kill fallback. CloseMainWindow returns false on Linux, so the clean-close path, the window title and the MessageBox are **not testable on the box**.

**Windows-only parts** that only Salem's run can show: `Get-CimInstance` child lookup, `MainWindowTitle`, WM_CLOSE → clean exit, and the MessageBox.

## Checksums (sha256, v2 2026-11-27)
```
1b5242baae69242e1fe6444238b9a5c2fa7114b01af913ccf6c0c426846a3115  sf_hang_watchdog.ps1
e4aacf95e0610c084723844bbf3011afbdda7cf98479014c31616e4faae648ea  watchdog_logic.py
ea3a9aaf0020f068b4b3fda066b3185c274e5df5ceb94424fda7b9fd6f33bc6f  check_hang_reports.py
231874490d21a90617463239e850f07f4e5effa79389f5d834d65435f5958c3b  sampler_hook_spec.md
90bc1fe230b15fdd8ad93e11664fc51f44527b799991cf30a2330f6a195a79ae  tests/fake_game.py
```
