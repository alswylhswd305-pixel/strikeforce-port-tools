# Black-screen hang after the boss (village load) — saud_blackhang_1817

Log: `testloop/saud_blackhang_1817_stderr.log` (109,558 lines, build 1786_movie_v5, no SF_HLE_LRLOG, no sampler).
Line numbers below are in that log unless marked "17:27" (= `testloop/voicediag1786_saud_20261127-172741_stderr.log`).
Box-only analysis; no code was changed in the game or the runtime.

## Verdict
**This is a new family. It is not the mixer heqi / EF 0x00DBA900 hang** (CONFIRMED, see §1).
- The PPU side stops dispatching right after the village load starts (L107973).
- Every SPU thread still visible in the log is polling an **empty or stale CellSyncLFQueue**.
- Persistent physics-type SPURS tasks **are never seen to end** between stages, and the third stage re-creates taskset 0x16FA2000 at the **same EA** while the earlier instances never RETURNed.
- What the main thread waits on is **not in this log**: no HLE call-site counts, no sampler, and the [sf-lfq] init/push logs were capped long before. §4 is the PC run that answers it.

## 1. Per live thread after L107958 (last fs open `1509`)

| thread | what it does | status |
|---|---|---|
| mixer taskset 0x00DB8F80 (img 391227015) | keeps cycling to the end: `WAIT_SIGNAL#210500 … #221500 … ran=15-16ms` from L109402 on. No `[SPU-HALT]`, no LS 0x31C20, no `EventFlagWait BLOCKED` line anywhere in the log. | **CONFIRMED alive → not the heqi/EF family** |
| tid 10 `_cellsurMixerMain` (created L263) | `[WAIT] event_queue_receive(q=1 timeout=9000000) lr=0x4D510`: 60,210 such lines in the whole log, at the same cadence before and after the hang. It is the normal audio-period wait. | CONFIRMED normal; not the hang |
| tid 51 `KslStrLoader` (created L107967) + BGM SetData 6ch 1690 frames (L107969-70) | This is the 9th KslStrLoader. The same create→SetData pattern ran 8 times before: L5467, 7209, 36051, 47463, 48573, 88571, 98662, 102911. The **same** track (1690 frames, loop [208512,3461120)) played fine from L36057. The runtime logs only fs *opens*, not reads, so "no fs open for 20 s" does not show the loader stalled. The BGM decoder keeps being called after the hang: decode errors at L109455-109532. | tid51 waiting vs reading: **unknown (ASSUMED not the blocker)** |
| img 437063289 (taskset 0x11057180 task 0, args 0x11058B00) | 14,897 dispatches, 14,896 RETURNED. The last dispatch is L107973 (built L107974) and never returns. At L108150: `[spu-spin] pc=0x0833C lr=0x07470 GETLLAR ea=0x11095F80` = the LFQueue initialised at L66 (owner 0x11057180, dir 2 = PPU→SPU, depth 2048). Line `0CFC0000 00000CFC 0CFC0000 00000CFC` → pop h1=h4=0xCFC, push h5=h8=0xCFC → **queue empty**. The consumer is waiting for a PPU push that never comes. No dispatch of any image after L107973. | CONFIRMED spin on an empty queue. CONFIRMED the PPU dispatcher of this per-frame job stopped at L107973. That this is a *consequence* of the PPU stall is ASSUMED. The same signature is in 17:27 (L76786/L76798, `084B`) after the mixer halt, and in freeze-1555/gE (stderr L1280, `0773`), where the dumps showed PPU put==get and guest tid 1 in a yield loop. So it is a common downstream symptom of "PPU stopped", not a cause. |
| img 361927206 (stage-B instance, args 0x16C54100) | L107252: `[spu-spin] pc=0x0B42C GETLLAR ea=0x16C53F80`. 0x16C53F80 = stage-B taskset 0x16C52680 + 0x1900, the same offset as queue 0x16FA3900 = 0x16FA2000 + 0x1900 (L34784). Only the stage-B instance uses 0x16C5xxxx queues. The line holds `00000000 CDCDCDCD FFFFFFFF 006B42C0`, which is not a sane queue header. | CONFIRMED a stage-B task is **still executing after stage C started** (L106846) and polls a queue whose memory now holds something else. That the memory was freed and reused is ASSUMED. |
| img 433674278 (stage A or C instance, args 0x16FE1680) | L108353: spin `pc=0x13C0C GETLLAR ea=0x16FA3980` (taskset 0x16FA2000 queue 2, init L34785, depth 8, dir 0). Line `00050000 00000005 …` → empty (5 pushed / 5 popped). | CONFIRMED empty-queue poll; which instance it is (A or C): unknown |

**Task lifecycle (CONFIRMED by counting `dispatch HIT (async)` vs `async image=N RETURNED`):**
- 361927206 and 433674278 are dispatched once per stage: L34787/34788 into taskset 0x16FA2000; L47365/47366 into 0x16C52680; L106846/106847 into **0x16FA2000 again, same args 0x16FA3A80 / 0x16FE1680**. They RETURNed **0 of 3** times.
- 454077064 instances *do* RETURN before each re-dispatch (L47300-02, L102689-91), so the runtime can end tasks when the game's own protocol makes them return.
- image 9000 (args 0x14C04380) is re-dispatched with the same args at L47344 and L106822 and never RETURNed.
- No taskset shutdown, destroy or join line exists in the log (searched). WAIT_SIGNAL lines: 0x16FA2000 only L38228..47259 (6); 0x16C52680 L50294..95345 (36).
- 17:27 has the same 2-of-2 non-returning pattern (L12341/12343, L40555/40556) but **no EA reuse**; it hung elsewhere (mixer halt).
- This log hangs at the **first stage that re-uses a taskset EA** (n = 1, so weak evidence).

**Hypotheses for the black hang** (all ASSUMED, ranked by evidence in hand):
- **H1, stale tasks:** when the game tears a stage down, our runtime does not stop the persistent tasks of that taskset. Most likely they sit in an LFQueue poll our port never wakes into a SPURS wait, so a shutdown has nothing to stop at.
  - Zombie instances (B proven, A possible) then share or alias queues with the stage-C tasks re-created at the same EA. The stage-C handshake the main thread waits for (the "frame physics results" wait func_005AF870 seen in gE/1760, `mixer-halt-1/researcher-ring-base.md` L240) is lost or consumed by the wrong instance.
  - The main thread stops presenting: title frozen at FPS 63 / draws 12.
  - The zombies explain part of the ~5.2 busy cores (each [spu-spin] is a host thread re-reading one line ≥4M times). The rest is unknown and may be the PPU poll.
- **H2, lost wake (old class):** the old slot-freeze / lost-wake class (H1/H1c in `mixer-halt-1/ringwatch-results.md` §2) on the 0x16FA39xx queues, triggered by the stage change. Not separable from H1 with this log: `[sf-lfq] init` lines stop after the stage-A set (L34744-34813, capped) and `[sf-lfq2]` push lines end at L38224 (400-line cap).
- **Rejected:**
  - loader handshake as the *first* cause: no evidence either way, and the same pattern worked 8 times;
  - ATRAC decode never producing data: decode is still called after the hang (§3);
  - the mixer/EF family (§1 table).

## 2. Watchdog v2 (fires on this pattern without SF_HLE_LRLOG and without a Now Loading marker)
Files: `watchdog/sf_hang_watchdog.ps1` + `watchdog/watchdog_logic.py` (same rules), version `v2 2026-11-27`.
- **spu_job_stuck (fires):** a `[spu-spin]` line for a *short, repeating* SPU job, i.e. one with ≥ JobMinReturns (50) completed runs, whose current run never RETURNs within JobStuckSec (10 s live). A replay without a t= clock uses JobStuckLines (200) instead.
  - Persistent tasks (0 returns) only give `spu_spin_info` (seen, never fires).
- **frozen_busy (fires, live only):** FPS title unchanged for FrozenSec (45 s) and CPU ≥ BusyCpu, whatever the log prints.
- **Heartbeats added** (not progress), because the hung game keeps printing them: `[WAIT] event_queue_receive(`, `[spu_workload] WAIT_SIGNAL#`, `[cellAtrac] Atrac3/3+:` decoder errors.
- **Seen-only `task_reuse_unreturned`:** a dispatch with the same image and args as an earlier dispatch that never RETURNed (here L47344, L106822, **L106846, L106847**). The report also lists every job dispatched but not RETURNED.
- **Results:**
  - this log: first fire `spu_job_stuck` at L108150 (confirmed at L108350). **Nothing fires in L1-108149.**
  - 17:27: unchanged first fire `spu_halt` L75722. spu_job_stuck is seen at L76798 and fires later, after spu_halt and ef_blocked. Nothing fires before L75722.
  - 27 other box logs with dispatch lines: no new fire. gE extract: seen at L1280, too short to confirm. It was a real freeze.
  - Live pwsh test (fake_game replaying this log): fired 10 s after the spin line, report written, kill path OK.
  - `frozen_busy` / title / WM_CLOSE / MessageBox are not testable on Linux.
- A rule "no fs open for N s after a loader thread starts" was **not added**. KslStrLoader starts 9 times with long fs-quiet stretches in normal play, and reads are not logged, so it would false-alarm.

## 3. ATRAC3+ "Missing atrac3p feature: Channel unit extension"
- **CONFIRMED, it is the 6ch BGM:**
  - every decode-error line in both logs reports `num_channel_blocks 4`, i.e. the 6ch decoder (handle 0x119FA1F0, KslAt3Decoder tid 15);
  - 105/105 here, 384/384 in 17:27;
  - not the voice mixer (SPU image 391227015) and not the mono handle 0x11E55028.
- Errors come in clusters during normal play (L39232-41138, 44907-46942, 60434-65784, 97902-98606 …), with no hang. The cluster after the hang (L109455+) starts ~1,300 lines after 437063289 stopped. **→ It causes the thin / "jee taan taan" BGM, not this hang and not the voice freeze** (CONFIRMED that it coexists with normal play; "not causal" is ASSUMED from that).
- **What the message means (own words):**
  - An ATRAC3+ frame is a chain of channel units. Each unit opens with a 2-bit tag: mono, stereo, "extension" or end.
  - The open decoder we vendor never implemented the extension tag and drops the whole frame when it sees one (`atrac/at3_standalone/atrac3plusdec.cpp:326`).
  - In the same clusters the decoder also reports a first bit that should be 0 ("Invalid start bit"), and unit tags that do not match the fixed 5.1 block layout (`:331`, printed even for a plain mismatch).
  - Together this says the bytes handed in at `data_off + k*block_align` are **not real frame starts** (misaligned, stale or never-fed bytes). It does not say the game uses extension units.
- **Real root fix:** make cellAtrac hand the decoder the exact bytes of frame k.
  - Code-reading suspects in `atrac/cellAtrac.c` (ASSUMED until the §4 hashes show which one):
    - (a) `cellAtracResetPlayPosition` L435-456 rewrites `file_fed = roff+n` and the ring, but does not flush the decoder or reset `next_frame`/`pcm_frame`.
      - After a forward seek, `decode_frame` L152-175 decodes every frame between the old position and the new one from the host copy.
      - Those bytes were never fed: zeros from `calloc` L270.
      - `frame_is_fed` L140-146 only checks `< file_fed`, so it treats them as fed.
    - (b) `cellAtracAddStreamData` L474-491 copies from the write pointer computed *now*, not the one the title was given by GetStreamDataInfo L458-472. Equal unless something moved `valid_off+valid_bytes` in between.
    - (c) loop handling at `cellAtracDecode` L321-329 relies on the linear host copy holding the loop region.
  - Fix = a valid-range model: which file bytes the host copy really holds. A seek flushes the decoder and restarts at k-1. A frame outside the valid range returns NODATA instead of decoding garbage.
  - Implement extension units only if verified real frames contain the tag. As far as I know there is no public spec for its contents. No GPL/LGPL decoder code is to be copied into our MIT code: the vendored at3_standalone is LGPL-2.1, kept separate.

## 4. PC run spec (log-only; changes no game behaviour)
Existing env, no rebuild. SF_HLE_LRLOG* are in the VOICEDIAG1786 launcher/exe; their source is not on the box. PS3_SAMPLE is in `ps3recomp-study/runtime/ppu/ppu_loader.cpp`, PS3_FSLOG in `runtime/ppu/ppu_fs.cpp`, SPU_PCSAMPLE in `runtime/spu/spu_channels.c`:
```
SF_HLE_LRLOG=1  SF_HLE_LRLOG_DUMP=5     # [hle-lrc] call counts per (nid, lr, tid) every 5 s: shows the main-thread poll
PS3_SAMPLE=5                            # [samp] PPU sampler (+ SF_SAMP_TID=1 if that log hook from sampler_hook_spec.md is built)
SPU_PCSAMPLE=2                          # [pcsample] SPU pc histogram
PS3_FSLOG=1                             # fs log (opens; reads too if the build has it)
```
New log-only hooks (one small build, print only; no new behaviour):
1. **Taskset/task lifecycle:** one line per cellSpursCreateTaskset / Shutdown / Join / Destroy / CreateTask / task exit / host-thread start/stop, with taskset EA, task id, image, args, host tid.
   - It answers "does the game shut 0x16FA2000 down, and does our runtime stop its threads?"
2. **LFQueue uncapped for the physics queues:** a new env `SF_LFQ_LOG_MAX=0` (0 = no cap) for the `[sf-lfq]` init/push/woke lines and the `[sf-lfq2]` stream.
   - Plus a pop line from the SPU side when a GETLLAR poll on a known queue EA sees h1/h5 change: queue EA, host tid, image, before/after.
3. **cellAtrac per call** (`SF_ATRAC_LOG=1`): tid, handle, function, pos, file_fed, valid_off/valid_bytes, write EA given and used, add bytes, and the FNV-1a of the added bytes.
   - At each decode error: frame k, file offset, first 16 bytes, and the FNV of the 1712 bytes. Offline, the box compares them with the real track bytes.
4. Run under watchdog v2: `-Launch <bat> -JobStuckSec 10 -FrozenSec 45`. On a fire it saves last_2000, hle_lrc_last2, spin_where, threads_cpu and dumps, then closes the game.

## 5. Lifecycle tool result (added 18:40 Asia/Kuwait, `lifecycle/sf_lifecycle.py`)
- The 18:17 findings above are reproduced automatically.
- **New, from the 17:27 log (CONFIRMED lines):**
  - At L76789/L76790, after the hang and ~36k lines after stage B started at L40515, `task 1/0 (taskset 0x16FA2000) sleeping 1s in WAIT_SIGNAL` print next to the stage-B tasks of 0x16C52680 (L76792/L76796).
  - Only stage A ever dispatched onto 0x16FA2000 in that log. **So stage-A tasks were still parked in WAIT_SIGNAL during stage B.**
  - `task 0 (taskset 0x14C02A80) sleeping 1s` prints twice (L76791, L76795) while the image-9000 runs from A and B are both open: two waiters for one task.
  - This backs H1 (old-stage tasks are never stopped). In this log they park in WAIT_SIGNAL; in 18:17 one spins on its old queue.

## §3b Update 2026-11-27 18:46 (from باحث الرياضيات, atrac-validator/)
Frame grid OK (block_align 1712, data_off 168/100 on all 8 tracks; VERIFY with hashfile). Bad bursts = whole 131072-byte chunks empty (zero-like) or wrong (random-like), so the add path is the suspect, not header/decode offsets; no-flush-on-seek less likely for these bursts. New ASSUMED suspect: AddStreamData copies the ring at call time (cellAtrac.c L485), before the game's read into the ring lands; no lock between tid51 (adds) and tid15 (decode). SF_ATRAC_LOG field list: atrac-validator/README.md.
