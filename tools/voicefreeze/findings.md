# Bandit Trap gate freeze: findings (2026-11-27, Asia/Kuwait)
Box-only analysis. No percentages are given; candidate "points" in the tool reports are evidence counts, not probabilities.
Saud's new logs `voicediag1786_saud_*_stderr.log` are **not on the box**. Only Salem's extracts in `/workspace/sf-diag1786/g1/` are, so the 17:27 numbers below are quoted from there (marked g1).

## 1. The assert answer (first)
**CONFIRMED (my own decoder `spu_mini_decode.py` + logged registers):**
- `LS[0x31C20] = 7F003200` = **`heqi r100, 0`** (RI10, op8 0x7F, RA = r100, I10 = 0, RT unused): the SPU halts if r100 word 0 == 0. Salem's field split is right. The next words are `hbrr`, `sfi r9,r101,0`, `sfi r10,r100,0`, `cgti r11,r101,-1`, `cgti r12,r100,-1`, `selb`, `selb`: absolute values of r101 and r100. That is the start of the compiler's **signed divide helper; the heqi is its divide-by-zero trap**. r100 is the divisor.
- `0x31A84` is **not the branch**: it is a return address (the call at 0x31A80 goes to 0x2FF88). Words there decode as `shli r16,r109,2; ila r15,0x26400; ...; ai r12,r88,36; ...; a r17,r16,r15`: normal code after a call.
- At the halt (`freeze-1555/live_1835/halt_diag_extract.txt` L66187-66244): `r100=00000000`, `r89=r7=0001F760`, `r92=00000200`, `r93=11373B80`, and **all 288 bytes at LS 0x1F760 are zero**. LS 0x1F760 is filled by a 288-byte GET from EA `r93+0x13CE0 = 0x11387860` (the GET at pc ~0x318EC).
- Who zeroed 0x11387860: `mixer-halt-1/ringwatch-results.md` run B. The mixer's 4KB ring PUT for **page 408 = EA 0x11387580** covers 0x11387860..0x1138797F. The ring has 360 pages (0x111EF580..0x11357580); pages per pass = 7 + 2*(visits-1), so page 408 needs **>= 201 visits** in one pass. The fatal pass in run B walked ids 0..128 and then 1..128 again (250 visits, 505 pages). `freeze-1555/analysis_1750/latch-and-clobber.md`: PUT_WATCH 0x11387860 went 0x3FE13FD7 -> 0, and the GET read 0 before the halt.
- So: **the trap tests the divisor r100, loaded from the 288-byte table at EA 0x11387860, which the mixer's own over-long ring write zeroed.**
**ASSUMED:** that r100 is loaded as `[r89 + 0x40 + 4*i]`. That comes only from gJ's PC-side disassembly. I could not check it on the box, because the overlay bytes before 0x31C20 are in no file here. SPU_DUMP_OVL in the race run will give them.

**Tie to 129/130 voices:** 130 voices alone cannot reach page 408 (130 visits = 265 pages, still inside the ring). Page 408 needs a pass that visits voices about twice, so the voice count is a symptom of the same scene change, not the cause (see §2b).

**Why EF 0x00DBA900 is never set again (CONFIRMED):** the only thing that sets it is the mixer job, once per cycle (Salem g1 + `cellSpurs.c` EventFlagSet path). After the heqi the mixer stops (`[spu] ... RETURNED rc=0` in the halt extract, then `EventFlagWait BLOCKED` from L66540 on; g1 L76797+). tid 7 (KslMsUpdater) waits on that flag forever, so the game hangs at the gate.
**Is our halt handling missing an RPCS3 path? No.** In my own words: on hardware a heqi that fires stops the SPU; it is a deliberate trap with no resume. RPCS3 treats a halt in a SPURS SPU thread as a fatal error and stops that SPU thread too; it does not skip the trap or restart the job. Our runtime does the same, except that it logs it as "job ran to completion", which is misleading. That wording is a log fix only, not the root fix. **The bug is upstream: the divisor is zero because the table was overwritten.**

## 2. QA review points
**(a) Where 0x31C20 lives (CONFIRMED part):** image.elf of 391227015 has text 0x3000..0x12D80 and data at 0x12D80 (filesz 0x50, memsz 0x2A0A0), so it zero-fills up to 0x3CE20. **0x2FE90..0x32A10 is inside that zero-fill. It is code loaded at runtime, not part of the lifted mixer**, which is why it runs in the SPU interpreter (needs SPU_INTERP_UNLIFTED=1, fix-log.md l.37-39).
**UNRESOLVED:** which image is mapped there. fix-log.md says flashATRAC.pic from dev_flash. gH says the bytes match EBOOT file offset 0x7D58A0 (LS = file - 0x7A3C80). The two disagree, and I cannot check either on the box (there are no EBOOT/pic bytes here). The race run settles it with `SPU_DUMP_OVL=...,0x2FE90` (source EA of the body DMA) plus `[fs] open` of flashATRAC.pic. Either way the assert is a divide-by-zero guard, and its input comes from the mixer's table.

**(b) "127 voices + group 2" is weak: QA is right (CONFIRMED from logs).**
- Run B held 117-127 voices for many passes, each walked once with no repeats and no overflow.
- voicediag1786 reached 127 voices with g2 = 118 (L35053) and had no halt.
- g1 burst 1 held 130 voices for about 6 s with no halt.
- The mixer de-dups a voice seen in several groups (path 2, dis.txt 0x6E10..0x6E9C: allocate only if no lower group bit is set in the voice mask).
- High voice count alone does not overflow. Overflow needs repeat visits.

**(c) Ranking:**
1. **Top (ASSUMED, strongest fit): a torn view between the live voice masks and the per-tick snapshot, during tid 17's bulk stop-all/restore at Now Loading.**
   - Mechanism, my own read of dis.txt 0x6D50..0x6E9C:
     - r8 = the voice mask (param+0x358, LS 0x2F758, from a 1168-byte GET at pc block 0x06BC0), and r27 = mask & current-group bit.
     - If the mask lacks the current group (path 1, 0x6D90), the mixer allocates ring pages for the voice **without de-dup**.
     - The group membership and budget come from the snapshot 0x111A2000/0x111A2800, which tid 7 copies each tick (fn 0x640C0 from lr 0x55484).
     - So a voice that the snapshot lists in g1/g2/g3, while its live mask has already been cleared by tid 17, is allocated once per group. That gives about 2-3x the visits, past page 408, the table is zeroed, then the heqi.
   - Evidence it fits:
     - g1 L74360 shows counts 130->2 and 127->0. That is 255 tid17 decrements (128 + 127; stop-all, lr 0x59590 via fn 0x58974 x255).
     - g1 L75722: mixer into 0x31C20.
     - g1 L75763: vm-sum g1=2, g3=130 (a stale snapshot still holding 130 in one group while the other is emptied).
     - g1 L76473: restore at lr 0x59724 x247.
     - The halt lands exactly between stop-all and restore.
     - Run B's fatal pass = the same voices walked twice (0..128 then 1..128).
   - Missing: per-pass mask vs snapshot at the fatal pass. Nobody has logged it yet.
2. **Second (ASSUMED): QA's PPU/SPU lost update on the voice records.** The SPU GETs the 2352-byte record (pc 0x06BC0) and PUTs 304 bytes back to rec+0x800 (pc 0x071EC). A tid17 store in between would be lost, so the stale ring index (+0x848) would survive.
   - For: the SPU is not under lwmutex 0x00DB8B80 (tid 17 and tid 7 use it); rec+0x848 is a ring index.
   - Against: on its own it does not explain a pass that walks the same ids twice; that is a visit-list problem, which (1) explains.
   - The two are not exclusive.
3. **Correction to the QA review:** vm-cnt +0x804/+0x808 are offsets in **table 0x111A1780** (counts at 0x111A1F84), not voice record +0x800. 0x111A1F84 is not inside any record's +0x800 block. So the SPU record PUT cannot write those counts. The 130->2 drop matches 255 tid17 decrements, which refutes the "no PPU writer / SPU write-back" claim with Salem's own numbers.
4. **Low:**
   - Voice leak or freer stall (C4): tid 7 frees normally until the flag stops.
   - cellSail* stubs (C5): nothing called near the burst in 1786 changes voice requests.
   - Kept in the tool, scored 0-1.

**Port-side differences that can widen the window (ASSUMED, to check, not fix):**
- the 0x2FE90 code runs interpreted (slower pass, longer window for tid 17 to change masks);
- uncapped FPS (78-94) makes tid 7/17 ticks more frequent;
- possibly the SPU sets 0xDBA900 before its pass's last PUT. The race run's check E tests that; if it is true, that is a SPURS ordering bug in our runtime and the real root fix.

## 3. Root fix
**None proposed yet. The evidence does not yet separate (1) from (2) or from a flag-ordering bug in our runtime.** No fix will clamp the ring index, guard the divide, patch the heqi, skip the job, or cap voices: all of those hide the bad pass. The fix follows from the race run:
- **M hits on the fatal pass, E clean:** find which ordering our runtime gives that hardware does not. Candidates: the snapshot copy vs the mixer's GETs, or the interpreted pass length.
- **E shows the set before the pass end:** fix the SPURS flag ordering in cellSpurs.c, at the root.
- **L hits:** fix the DMA/visibility ordering between the PPU stores and the SPU record GET/PUT.

## 4. Log-only points (all in race_run_spec.md, checker race_check.py)
- SPU at the branch: `[sfrace-halt]` with the insn word, op8, RA index + value, imm, r89/r93, LS at r89 (128 bytes + 288-byte hash) and the table EA r93+0x13CE0, matched to the last GET and the last PUT that covered 0x11387860.
- The divisor's source: the 288-byte GET of 0x11387860 (hash), and all ring/past-ring PUTs with page numbers. `SPU_DUMP_OVL=<dir>,0x2FE90` gives the overlay bytes to check the `[r89+0x40+4i]` load.
- The voice-count source: GETs of the snapshot counts 0x111A2800 (bytes) and bitmap 0x111A2000, every param GET with m358, every record GET (sub-hash of +0x800..+0x92F) and PUT (pre/post hash), and tid17/tid7 stores to params/records/table 0x111A1780 with old/new and tid. Everything goes on one clock (`sf_qpc_ns`, the same QPC formula as spu_host_ns).
- EF 0xDBA900: the SPU set (atomic PUTLLC on its line, or the SPURS set path) and the PPU wake in cellSpursEventFlagWait, on the same clock, with a dump on the first BLOCKED.

## 5. Tools
- `voice_freeze_analyzer.py` (README.md). Run on voicediag1786: no trap; bursts 5->77 and 86->127 held about 2 s. Run on the halt extracts (out_halt_extracts/): C1 trap chain fully matched (14 evidence lines).
- `race_check.py`: checks V/M/L/W/E for the race run.
- `spu_mini_decode.py`: own SPU decoder.

## 6. Update 18:10 (Asia/Kuwait): Saud's raw 17:27 log is now on the box
File: `testloop/voicediag1786_saud_20261127-172741_stderr.log`, 92,468 lines, mtime 17:50.
- **CONFIRMED** Salem's line numbers:
  - L73753/73763: hdd1 cache files 5444/5443 opened;
  - L75722-75725: the branch into 0x31C20, with `LS[0x31C20]: 7F003200 ...`;
  - L76797 onward: BLOCKED on 0x00DBA900, 1 s to 24 s (the print stops at its 24-line cap).
- **(a), new clue (ASSUMED):** L667 opens `/dev_flash/sys/external/flashATRAC.pic`, just before the mixer first interprets runtime-loaded code at 0x2FE98/0x2FE90 (L738-750). That favours fix-log's flashATRAC.pic over the EBOOT-blob reading. `SPU_DUMP_OVL` still has to prove it.
- **CONFIRMED** from the `[hle-lrc]` dumps: guest tid 17 runs a tight loop of `sys_ppu_thread_get_id`@0x53584, `sys_lwmutex_lock`@0x58C38 and `sys_lwmutex_unlock`@0x58CE4.
  - It ran about 65k calls/s from dump window 5 (t=147728.97 s, during burst 1) to the end of the log, before and after the halt.
  - Before that, a full window ran 44,742–50,060 calls per 20 s.
  - This is the busy "loop" Saud sees. tid 17 is the voice starter thread. Why it loops (for example, retrying while the pool is full) is ASSUMED. The watchdog's spin capture plus `sampler_hook_spec.md` (`SF_SAMP_TID`) will show its hot PC.
- `[spu-spin]` L76798: img 437063289 pc 0x0833C re-issues GETLLAR on 0x11095F80 (4M times). This is a second spinner, an SPU waiting on a line.

## 7. Black-screen hang after the boss (saud_blackhang_1817), 2026-11-27 18:30 Asia/Kuwait
See `blackhang_1817.md`. It is a new family: SPURS persistent tasks are not ended between stages, the taskset EA is re-used and the PPU stops dispatching at L107973. It is not heqi/EF 0xDBA900. The ATRAC3+ errors are from the 6ch BGM feed, not this hang. Watchdog v2 fires `spu_job_stuck` at L108150.
