# PS3 → native PC with ps3recomp

Use this playbook when converting **any** PS3 title to a native PC build with [ps3recomp](https://github.com/sp00nznet/ps3recomp) static recompilation, using RPCS3 as the behaviour oracle. It distills the Dynasty Warriors: Strikeforce (BLUS30471) work of 2026-11-26 into a generic, ordered checklist. Strikeforce numbers appear only as a worked example.

Labels: **KNOWN** = read in a cited source. **ASSUMED** = reasoned, not verified. **VERIFY** = a concrete test. Never invent a success rate or an "X% done" figure. Search the web (and re-read upstream docs) before treating a claim as current. Keep GPL-derived code out of any release. Do not touch the user's PC, Downloads, or firmware unless they approve that exact step in their own words.

Pins to refresh each campaign (values below are the 2026-11-26 pins; re-check HEAD):

- **P** = ps3recomp master, then `e85647a` (tag v0.20.0 is `d81c393`). Master carries PR #847: lwmutex FIFO hand-off, `cellSpurs_register_ctx_handlers` (maxContention), and the Windows InitOnce lock fix.
- **R** = a pinned RPCS3 commit (then `0ca5eb0` / `7ad67aad` for sysmodule). Prefer a title that RPCS3 already rates Playable.

Companion tools written during the Strikeforce work (box copies; adapt paths): `tools/rpcs3_objsnap.py`, `tools/spurs_objdiff.py`, and the untested skeleton `auto_convert_loop.py`.

---

## Standing rules

1. Disc data, `dev_flash`, and any decrypted SPRX stay on the user's machine. Firmware-derived output is local and git-ignored; never commit or distribute it (P `docs/FIRMWARE_LLE.md`).
2. Unresolved NIDs default to faking `CELL_OK` and leave out-params untouched (`PS3_HLE_UNRESOLVED`). That hides missing handlers as "success".
3. Do not port code from RPCS3 or other GPL trees into the port (P `CONTRIBUTING.md`). Read RPCS3 for layouts and behaviour, then write a clean-room handler or lift the user's own firmware.
4. Force-unstick, `PPU_NOOP_BAD_VCALL`, and `YDKJ_FORCE_HLE`-style bypasses are diagnostics, never the fix.
5. Log caps lie. If a log says "never happened", first remove the cap.
6. Measure with counts and milestones, not guesses.

---

## 0. Laws (verified rules of thumb)

Rules taken from the Strikeforce (BLUS30471) work of 2026-11-26, written so the next title can apply them. **KNOWN** = at least one verified case in the chain below. **HEURISTIC** = exact arithmetic, or a working rule recommended here, that was not itself a measured fix. Disproved leads are cited only as lessons, never as fixes. Do not invent a success rate or an "X% done" figure.

Verified fix chain: (1) `cellVideoOutGetDeviceInfo` struct layout → NULL `bctr` crash. (2) ATRAC hang. (3) OSK auto-confirm. (4) `cellOvis` overlay table. (5) "Queue never pushed" was a log cap. (6) MOC hang: the event flag had no taskset (`isIwl` / `addr` / `spuPort` / `wid`). (7) A depth-only shadow clear started a new frame and presented early. (8) VB overflow, fixed with a mid-frame flush without presenting. (9) Depth surface at offset 0 treated as "none". (10) libmixer `SetNotifyEventQueue(0)` remap.

### L1. Fakes are guilty first

**Law.** A fake `CELL_OK`, or a default that leaves out-params or state unset, is the first suspect when the game later crashes, hangs, or sees nothing.

**Evidence.** Fix 2: seven `cellAtrac` streaming NIDs were unresolved; the stub returned `CELL_OK` and left out-params untouched. Fix 4: `cellOvisInitializeOverlayTable` faked OK and `GetOverlayTableSize` returned 0, so overlay SPU code loaded empty. Fix 1: `cellVideoOutGetDeviceInfo` was registered, but a missing `colorInfo` hid `availableModes` at the wrong offset, so PSGL saw no 720p mode and boot crashed on a NULL `bctr`. Fix 6: an event flag created with no taskset left `isIwl=0`, `addr=0`, so `SendSignal` failed silently. Fix 9 and Fix 10 are the sentinel-0 form of the same law (L5).

**Check.** `PS3_HLE_UNRESOLVED=fail`. Collect `[hle] UNRESOLVED NID` lines. For a registered handler, dump layouts (L2) and confirm every out-param is written.

**Label.** KNOWN

### L2. Guest layout is the ABI

**Law.** If the HLE C struct is not the SDK / RPCS3 guest layout, the game reads zeros or stale fields and then calls through a NULL object.

**Evidence.** Fix 1: missing `colorInfo` in `cellVideoOutGetDeviceInfo` put `availableModes` at +0x0C instead of +0x20; the crash was a NULL `bctr` ("opd 0x7190"). The same class is documented for `cellAudioOutGetDeviceInfo` / `GetState` and GameData `StatGet` (source mismatch; not this title's crash).

**Check.** `clang -Xclang -fdump-record-layouts` on both headers; compare the offsets the HLE writes into guest memory against RPCS3 `CHECK_SIZE`. Run with `PS3_HLE_TRACE=400 PS3_CALLTRACE=200 PPU_VCALL_BT=1 PS3_EXIT_CHAIN=1`.

**Label.** KNOWN

### L3. Log caps lie

**Law.** If a log says something "never happened", remove the cap before treating that as a fact.

**Evidence.** Fix 5: a 24-line push log produced the false claim that the third queue was never pushed. With the cap removed, all three queues were pushed and drained (`h1=h4=h5=h8`).

**Check.** Uncap the relevant log (here the LFQueue push log / `[sf-lfq2]`), rerun, then believe "never".

**Label.** KNOWN

### L4. An unstick is a diagnosis, never the fix

**Law.** Forcing a waiter or counter only proves the wait was standing in for unfinished work. The fix is the missing writer or the missing HLE state.

**Evidence.** `SF_MOC_UNSTICK` let the stage run at 8 fps with ~874 draws and a still-black frame. The hang's verified fix was Fix 6 (`isIwl=1`, `addr=spurs`, `spuPort=0xFF`, and a real `wid`), not a forced counter. `PPU_NOOP_BAD_VCALL` and `YDKJ_FORCE_HLE`-style bypasses are the same class.

**Check.** After an unstick run, dump the event-flag and taskset objects (`SPURS_EF_STATS=1 PS3_WAITBT=1`) and compare them to RPCS3 (`rpcs3_objsnap.py` + `spurs_objdiff.py`). Keep the force flag off in any build you keep.

**Label.** KNOWN

### L5. Zero is often valid

**Law.** Offset 0, token 0, and key 0 are often valid guest values. A test of the form `if (offset)` drops a real surface, waiter, or queue.

**Evidence.** Fix 9: the scene depth buffer lives at offset 0; treating that as "no depth" fell back to a shared buffer that is cleared on every target switch and mid-frame flush; `DEPTH_OFF=1` made the village appear. Fix: a separate `has_zeta` flag and a lookup by offset, never `offset != 0`. Fix 10: `SetNotifyEventQueue(0)` must remap to `0x8000CAFE02460300`; key 0 is not "no queue". The same class: waiter token 0 is a valid WID0/task0 token, not "empty".

**Check.** For any "is present?" test, use an explicit has-flag. Confirm depth with `DEPTH_OFF=1`. Confirm mixer with `AUDIO_RATE=1 AUDIO_PEAK=1`.

**Label.** KNOWN

### L6. Do not Present a half-built frame

**Law.** A depth-only clear, a mid-frame flush, or any bookkeeping submit must not start or Present a new frame.

**Evidence.** Fix 7: a shadow-map clear with no colour target was treated as a frame start and presented early; after the fix the stage ran at 62 FPS with no debug switches. Fix 8: a complete frame overflowed `MAX_VERTICES` (393,216) and later draws were dropped as `upload_empty` (ground, sky, and hills missing). Fix: flush the recorded batch mid-frame without presenting and keep recording the same frame. After that, sky, hills, characters and HUD rendered at about 90 FPS.

**Check.** `D3D12_DROP_STATS_EVERY=60 VP_SUBMIT=3`. A clear with no colour target must not begin or present a frame. When the VB, IB, or draw list is full, flush without Present. Look for a rising `upload_empty` count.

**Label.** KNOWN

### L7. A familiar offset is not the same object

**Law.** A well-known LS or register offset is not that kernel or RSX field until the lifted code, the task arguments, or the enum table say so. Check those before inventing a theory.

**Evidence (verified facts).** In the MOC image, work-area `+0x1D0` is a stack field filled from `CellSpursTaskArgument` word1; it is not kernel LS `0x1D0` (`wklCurrentAddr`). The hang's verified fix was Fix 6. Vertex type 7 is UB256 and CMP is 6 (SCE SDK table, RPCS3). This title issues no subchannel-1 methods in the 3D range, and the in-stage `cmask` is `0x01010101`; the half-built frame was Fix 7. Primitive-restart strip cutting is correct to implement, but it did not change the visible picture here.

**Check.** `cellSpursCreateTask` prints `arg=w0 w1 w2 w3`; confirm the same 16 bytes arrive in r3 (`SPURS_TASKSET_TRACE=1`). Disassemble with `tools/spu_disasm.py` and read the lifted C. Diff the same SPURS objects, not all of memory (`rpcs3_objsnap.py` + `spurs_objdiff.py`). For RSX names, read RPCS3 `gcm_enums.h` before assigning a vertex type or method.

**Label.** KNOWN

### L8. Bisection costs ceil(log2 N) runs

**Law.** To find one bad item among N (a draw, a commit, a NID), disable or revert half each run. The worst case is ceil(log2 N) runs, not N (for N = 400, 9 runs).

**Evidence.** Exact arithmetic. In this campaign it is the recommended method (`git bisect` for a regressing change; `SPURS_EF_FORCE` / force-HLE only as a temporary diagnostic bisect list that must end empty). A full 400-draw bisect has not been measured on this title.

**Check.** Bad commit: `git bisect start && git bisect bad HEAD && git bisect good <known-good>`. Draws: gate off the upper half of the list (or a `DRAW_SKIP_*` / local skip), see if the artefact remains, repeat. NIDs: `PS3_HLE_UNRESOLVED=fail`, or force-HLE half of the suspects, then shrink the set.

**Label.** HEURISTIC

### L9. Priority score = (hits × severity) / fix time

**Law.** Rank open problems by (how often a run reaches them × how badly they block a milestone) divided by estimated fix time, and work the highest score first.

**Evidence.** This is the ordering that produced the verified chain: the boot crash (Fix 1) blocked every later milestone, then the hangs that blocked in-stage (Fixes 2–6), then the picture (Fixes 7–9), then audio (Fix 10). No numeric scores or a percentage speedup were assigned.

**Check.** Keep a short table: milestone blocked (boot / load / in-stage / picture / audio), hit count from a `PAD_SCRIPT` log, and a time estimate. Recompute after each verified fix. Do not put two unproven fixes in one build (L12).

**Label.** HEURISTIC

### L10. Throughput = instances × 3600 / cycle seconds

**Law.** Runs per hour ≈ N × 3600 / T_cycle, where T_cycle is seconds from launch to the observation (boot + observe, excluding build time) and N is the number of parallel instances.

**Evidence.** Arithmetic from this title's measured boot (Salem, render-bugs-round3): boot to stage is 135 s, of which 75 s is idle on PRESS START, so about 60 s once that idle is cut. For an observation time T = 30 s that is 3600/(135+30) ≈ 22/h today, versus 2 × 3600/(60+30) = 80/h with two instances and the idle removed. For T = 60 s the same arithmetic is ~18/h versus 60/h. These are calculated rates, not a measured campaign throughput. Build time is excluded and unknown. Measured later the same day (Salem): stage reached in about 70 s after the idle cut, and 4 parallel instances ran together (about 2.7 GB VRAM).

**Check.** Cut scripted idle on PRESS START. Run N copies against a test folder. Time one cycle with a wall clock before quoting a rate: N × 3600 / (boot_without_idle + observe).

**Label.** KNOWN (formula and the 135/75 s split). The 22 vs 80 figures are arithmetic from T = 30 s, not a measured throughput.

### L11. The ABI includes events and remaps the game polls

**Law.** A `CELL_OK` return is not enough if the game is waiting on a sysutil event, a magic queue key, or an out-param the handler never wrote.

**Evidence.** Fix 3: OSK `LoadAsync` must broadcast LOADED `0x502`, later FINISHED `0x503`; `UnloadAsync` writes big-endian UTF-16 and UNLOADED `0x504`. The Windows stub that required a non-exported `cellOskDialogInit` sent nothing, so savedata hung. Fix 10: `SetNotifyEventQueue(0)` remaps to `0x8000CAFE02460300`; without the remap the mixer queue never matches (silence, peak=0). Fix 2 is the out-param form: streaming ATRAC must implement `GetStreamDataInfo` / `AddStreamData` / second-buffer NIDs, and remain-frame must not always be `-1`.

**Check.** Log sysutil events around `cellSysutilCheckCallback` (`PS3_HLE_ARGS=7FCFC915` for LoadAsync). Mixer: `AUDIO_RATE=1 AUDIO_PEAK=1`. Read RPCS3 for event IDs and magic keys, then write a clean-room handler.

**Label.** KNOWN

### L12. One change per build; keep a known-good snapshot

**Law.** Change one thing per build. After a verified fix, keep a snapshot you can roll back to in seconds.

**Evidence.** The verified chain is ten separate fixes. Several screenshot-plausible theories (subchannel-1 colour mask, vertex type 7 = CMP, strip restart as the visible bug, r3/0x1D0 as kernel LS) would have landed in the same tree as Fixes 6–9 and hidden which change worked. Numbered patch files keep each fix reviewable (section 11).

**Check.** One patch file per fix. After a confirming run, tag or copy the test build. If a later change regresses, bisect against that tag (L8).

**Label.** HEURISTIC

---

## 1. Setup

**Symptom.** The port is on an old tag, breakpoints do nothing, or the game cannot find its disc files.

**Fastest diagnostic.** `git log -1 --oneline` on the SDK copy. In RPCS3, confirm GDB Server is on and PPU Decoder is Interpreter. In the port, confirm `/dev_bdvd/PS3_GAME/...` opens (`PS3_FSLOG=1`).

**Typical root cause.** v0.20.0 (`d81c393`) predates the #847 runtime fixes. RPCS3 breakpoints under the LLVM decoder return OK and never fire (R `PPUThread.cpp`). A wrong `PS3_VFS_ROOT` makes the game poll a missing index every frame on a black screen (Strikeforce: `LINKDATA.IDX` when the root was `vfs\` instead of `vfs\dev_bdvd`).

**Fix pattern.**

- Rebase the runtime onto ps3recomp master ≥ the #847 fix commit.
- Lift PPU with the usual pipeline: `ppu_loader.py`, `ppu_lifter.py --hle-stubs`, `gen_hle_nids.py --all`.
- Map the user's own dump, never a distributed image:
  - `PS3_VFS_ROOT` = the directory that makes `/dev_bdvd/X` → `<root>/X` (usually the folder that contains `PS3_GAME`).
  - `PS3_HDD0_ROOT` / `PS3_HDD1_ROOT` / `PS3_GAMEDATA_ROOT` writable.
  - `PS3_DEV_FLASH` = a read-only copy of the user's RPCS3 `dev_flash` (needed for runtime firmware such as `flashATRAC.pic`).
- RPCS3 oracle: GDB server `127.0.0.1:2345`. Use the **Interpreter** decoder whenever you need breakpoints. `tools/rpcs3_probe` / `rpcs3_objsnap.py` attach there. Connection pauses the emu, so every read is from one instant.
- Optional: `PAD_SCRIPT` / `PAD_STICK` for a repeatable path to the same screen (Tornado pattern).

---

## 2. NID resolution

**Symptom.** An import has no name, or a stub is registered under the wrong NID.

**Fastest diagnostic.** `python tools/nid_database.py compute_nid <name>` and `--lookup 0xXXXXXXXX`. Cross-check against `EBOOT.imports.json`.

**Typical root cause.** **KNOWN:** NID = first 4 bytes, read **little-endian**, of SHA-1(`name` ‖ suffix `6759659904250490566427499489741A`) (R `PPUModule.cpp`; confirmed because `cellSysmoduleLoadModule` → `0x32267A31`). P `docs/NID_SYSTEM.md` still says a 4-byte suffix and a big-endian read — that is **wrong**. Do not trust it.

**Fix pattern.** Compute names from RPCS3 `REG_FUNC` lists. Regenerate the table with `gen_hle_nids.py --all`. A "handler exists" line only means a C function is registered, not that the body is complete.

---

## 3. Boot crashes from HLE struct layout mismatches

**Symptom.** Early NULL `bctr` / crash, a refused video mode, silence, a bogus "not enough space" dialog, or a fifth movie that never ends.

**Fastest diagnostic.** Dump both headers with `clang -Xclang -fdump-record-layouts` and compare offsets the HLE actually writes into **guest** memory against RPCS3 headers (`CHECK_SIZE`). Run with `PS3_HLE_TRACE=400 PS3_CALLTRACE=200 PPU_VCALL_BT=1 PS3_EXIT_CHAIN=1`. Use `PS3_HLE_ARGS=<nid>` for r3–r10, and `PS3_HLE_UNRESOLVED=fail` to find the load-bearing fake. `PS3_SCTRACE=fail` catches allocator syscalls. `PPU_NOOP_BAD_VCALL=1` is a band-aid only.

**Typical root cause.** The HLE C struct is not the SDK / RPCS3 guest layout, so the game reads zeros or stale fields and then calls through a NULL object. **Worked example (Strikeforce):** missing `colorInfo` in `cellVideoOutGetDeviceInfo` (NID `0x1E930EEF`) put `availableModes` at +0x0C instead of +0x20; PSGL found no 720p mode, skipped heap setup, and crashed on a NULL `bctr` ("opd 0x7190").

**Fix pattern (write SDK-sized fields, then unit-test the layout).**

| Area | RPCS3 / SDK layout to match | What v0.20 got wrong |
|---|---|---|
| `cellVideoOutGetDeviceInfo` `0x1E930EEF` | `colorInfo` 20 B at +0x0C, modes at +0x20; fill `refreshRates` (e.g. 59.94+60) | no `colorInfo`; modes at +0x0C; `refreshRates=0` |
| `cellAudioOutGetDeviceInfo` `0x7663E368` | DeviceInfo **136 B**; latency **u16 at +6**; modes at **+8**; SoundMode **8 B** (`layout` u32 at +4); **state=1 (AVAILABLE)**; latency 13 | 4-byte SoundMode, no latency, modes at +6, state=2 |
| `cellAudioOutGetState` `0xF4E3CAA0` | **20 B**; `downMixer` at **+8**; `soundMode` at **+12** | downMixer at +4, soundMode at +8 |
| GameData `StatGet` | size **0x1448**; `sizeKB` at **+0x13FC**, `sysSizeKB` at +0x1400 | wrote `sizeKB` at +0xB9C (inside `titleLang`) |
| syscall 352 `sys_memory_get_user_memory_size` | live `size - used` from the real pool | fixed 256 / 192 MB, so a large heap can get `ENOMEM` |
| `cellSysCache` | `RELAYED` on a clean reuse; move an unclean cache aside | always `CLEARED` (stale-cache title bugs) |
| `cellSail` Finalize | free the player / adapter slot | slots never freed (Nth movie hangs) |
| `cellAtrac` streaming | implement GetStreamDataInfo / AddStreamData / second-buffer NIDs; remain-frame must not always be `-1` | unresolved fakes; "STREAMING is not implemented" decodes garbage |
| libmixer notify | `SetNotifyEventQueue(0)` remaps to `0x8000CAFE02460300` (RPCS3 `cellAudio.cpp`) | key 0 never matches the mixer queue → silence, peak=0 |
| ATRAC3plus | allow the channel count the decoder already supports (e.g. 6ch) | HLE rejects `channels > 2` |

Also confirm AudioOut / mixer with `AUDIO_RATE=1 AUDIO_PEAK=1`. Mixer holes after a non-zero peak are an SPU-pace issue, not a struct issue.

---

## 4. Sysmodule IDs

**Symptom.** `cellSysmoduleLoadModule(id)` "succeeds", then a later import is NULL or unresolved.

**Fastest diagnostic.** Map `id` in P `libs/system/cellSysmodule.h` and R `cellSysmodule.h` / `cellSysmodule.cpp` (`MODULE_INFOS` is 0-based). List `PS3_GAME/USRDIR/*.sprx`. Log `UNRESOLVED NID` lines and look them up.

**Typical root cause.** **KNOWN:** ps3recomp only marks the module loaded; it does not load the SPRX or patch imports. **Worked example:** `0x003B` = `CELL_SYSMODULE_SYSUTIL_OSK_EXT` (`libsysutil_oskdialog_ext.sprx`, library `cellOskExtUtility`, 17 `cellOskDialogExt*` functions). None were registered.

**Fix pattern.** Identify the library, register real handlers or honest errors (so the game can take a fallback), and stub only callbacks you intend to ignore. If the title loads its own USRDIR SPRX, that PRX must be lifted (`lift_prx` / `ppu_lifter --raw --base`); empty imports will not fix it.

---

## 5. OSK / dialog auto-confirm

**Symptom.** Savedata or name-entry hangs after `SetLayoutMode` / `SetInitialKeyLayout`. No sysutil OSK events.

**Fastest diagnostic.** `PS3_HLE_ARGS=7FCFC915` (LoadAsync). In RPCS3, look for `sending CELL_SYSUTIL_OSKDIALOG_LOADED`. On exit, read `[exit-chain]`.

**Typical root cause.** **KNOWN:** the Windows stub requires `cellOskDialogInit`, which is **not a real PS3 export**, so the game never calls it. LoadAsync returns `0x8002B301` and sends nothing. The native path that does send events is Linux-only (`PS3RECOMP_NATIVE_OSK_HEADLESS`).

**Fix pattern (auto-confirm, clean-room).**

- LoadAsync must not require Init. Broadcast **LOADED `0x502`**.
- On a later `cellSysutilCheckCallback` poll, broadcast **FINISHED `0x503`**.
- UnloadAsync writes `result=0` and the text as big-endian UTF-16 into the result buffer, length = `min(len, capacity)`, then **UNLOADED `0x504`**.
- Text from `OSK_AUTO_TEXT`, else the game's init text, else a short default.
- `numCharsResultString` is the buffer **capacity** (read, never write). `GetSize` writes **u16 1,1** (not a pixel size). Abort sends FINISHED with ABORT. Real errors are `0x8002B501..B504`; BUSY is `0x8002B105`.
- Register any Ext* imports the title actually calls (SendFinishMessage `0x42439DB5` first).

---

## 6. Loading hangs (SPURS / overlays)

**Symptom.** "Now Loading" (or an equivalent) renders forever. Frames may still flip. A task sits in `WAIT_SIGNAL`.

**Fastest diagnostic.** `SPU_DUMP_MISS=<dir> SPU_MISS_FATAL=1` (a fatal exit means a program was dropped). `SPU_CH_BLOCK=1` prints the blocking channel. Default log line `EventFlagWait BLOCKED … flagEA=`. `SPURS_EF_STATS=1 PS3_WAITBT=1`. Dump the event-flag and taskset objects (phase 7).

**Typical root causes, in the order they actually bit Strikeforce.**

1. **cellOvis.** `cellOvisInitializeOverlayTable` unresolved (fakes OK); `GetOverlayTableSize` returns 0. Overlay SPU code loads empty. Fix: copy overlay segments into the table; match the SDK prototype.
2. **Event flag created with no taskset.** HLE left `isIwl=0`, `addr=0`, so `SendSignal` went to taskset 0 and failed silently. Fix: `isIwl=1`, `addr=spurs`, `spuPort=0xFF`.
3. **Workload id.** Give each taskset its own wid (0…N). Set `wklInfo1[wid].arg` to that taskset. Write **LS 0x1D8 and 0x1DC = wid** on async-dispatched tasks (the policy-module path already does; the HLE dispatch path often does not).
4. **Waiter token** is `(wid<<8)|task`. Token 0 is a valid WID0/task0 token, not "empty". Decode it and signal that task, not task 0 of `eaSignal`.
5. **Notify under the lock.** Waking a waiter after releasing the lock raced and crashed; notify while the lock is held.
6. **LFQueue guest protocol** (same class). Upstream `_cellSpursLFQueueInitialize` writes depth at **+0x0C**, which is `push1.m_h7/m_h8` — a fresh queue looks **full**. There is no `_cellSpursLFQueuePushBody` (`0x8A85674D`) or `PopBody` (`0x35DAE22B`). `AttachLv2EventQueue` is a no-op, so `m_eq_id` stays 0 and a blocking PPU push cannot sleep. Init must match the 128-byte `CellSyncLFQueue` line (m_bs = -1, direction, init; depth is **not** at +0x0C). CompletePush publishes **h5 before** the wake, and signals only the **head** of `push2/m_hs1`.
7. **Runtime limits still in master.** `TS_TRACK` is 8 with no release (Demon's Souls raised it to 64). `ShutdownTaskset` / `JoinTaskset` are no-ops (zombie tasks can corrupt a loader buffer). Only `WAIT_SIGNAL` among the taskset syscalls is real.

**Fix pattern.** Prefer one root fix for the class (phase 10) over a per-queue patch. If you must hand-write LFQueue, write it clean-room against the public line protocol (RPCS3 `cellSync.cpp` is a specification, not a source to copy). `cellSpursQueue` is a **different** layout from LFQueue (Demon's Souls fix 12 vs 19).

---

## 7. Diagnosing hangs

**Symptom.** A wait that never ends: job handles, event flags, lwcond, or a retry loop with `cia=0`.

**Fastest diagnostic (do these in order).**

1. **Uncap logs.** A 24-line push log produced the false claim "the third queue is never pushed". With a full log, all three queues were pushed and drained (`h1=h4=h5=h8`).
2. Log the actual wait: which EA, which word, which compare (e.g. "done" at `P+0x1C`, then a counter at `handle+0x38`).
3. **Check task arguments byte for byte.** `cellSpursCreateTask` prints `arg=w0 w1 w2 w3`. Confirm the same 16 bytes arrive in r3 at task entry (`SPURS_TASKSET_TRACE=1`, plus one temporary log in `spu_run_lifted_job_abi`). Generic tasks must get `TaskInfo.args` as RPCS3 does. Watch for a CRI/YDKJ `r3_override` heuristic that rewrites word1.
4. **Find who writes a counter from the lifted SPU**, not from a guess. Disassemble with `tools/spu_disasm.py` and read the lifted C. In the Strikeforce MOC image, work-area `+0x1D0` was a **stack field** filled from **argument word1** — not kernel LS `0x1D0` (`wklCurrentAddr`). The −1 ran only when that word was non-zero.
5. Compare **the same SPURS objects** in RPCS3 and the port (`rpcs3_objsnap.py` + `spurs_objdiff.py`). Do not diff all of memory; addresses differ. Skip host-only fields (taskset `running`/`waiting`; lwmutex free is `0` here and `0xFFFFFFFF` in RPCS3).
6. RPCS3: break on the import stub from `imports.json` (CreateTask `0xBEB600AC`, EventFlagWait `0x373523D4`, LFQueue PushBody `0x8A85674D`). Interpreter only.

**Typical root cause.** Missing or wrong HLE state on the PPU side of a Sony SPU protocol, or a log artefact.

**Fix pattern.** Fix the writer or the argument delivery. **`SF_*_UNSTICK` / forced counters are diagnostic only.** Forcing the Strikeforce MOC counter to 0 let the stage run at 8 fps with ~874 draws and a still-black frame — the wait was standing in for unfinished work. `SPU_INTERP_MISS` is **not** an upstream env var; it is a local patch in some ports. Upstream `SPU_INTERP_UNLIFTED` only covers unlifted PCs (and may have a PC threshold). There is no upstream switch to interpret a **lifted** SPURS task; an A/B needs a local skip of that fingerprint.

---

## 8. SPU: capture, lift, rebuild

**Symptom.** `dispatch MISS`, a dropped program, a loader that waits forever, or firmware-only code (ATRAC, overlays) that never runs.

**Fastest diagnostic.** `SPU_DUMP_MISS=<dir>` plus `SPU_MISS_FATAL=1`. Count `dispatch HIT` / `MISS` and "interpreting unlifted LS". Inventory: `tools/extract_spu_images.py` and `port/spu/inventory.json`.

**Typical root cause.** A runtime-loaded ELF or job was not in the lift set. Overlapping `PT_LOAD` / overlay images cannot be lifted ("overlapping PT_LOAD memory ranges (including BSS) are unsupported") — Strikeforce cloth image `375200614` is the worked example; it must stay on the interpreter. Firmware images pulled from `dev_flash` at runtime also cannot be lifted from the EBOOT.

**Fix pattern (standard loop used by Tornado, Simpsons, Demon's Souls).**

```
SPU_DUMP_MISS=<dir>   # run until the miss is written
# ELF dumps: rename/copy to .elf if needed
python tools/build_spu_workloads.py --images <dir> --lifted <port>/spu \
    --out <port>/spu/spu_workloads.c --register-fn port_spu_register_all --constructor --title <TAG>
# raw job modules:
python tools/lift_jobmods.py ...
# PIC / firmware pieces, if present:
python tools/lift_spu_pic.py ...
# rebuild, rerun; success looks like: dispatch HIT (async) fp=0x...
```

Bulk-lift every embedded image up front when you can (GoW Ascension `prepare.ps1` pattern). Keep `SPU_INTERP_UNLIFTED=1` and `PS3_DEV_FLASH` for images that cannot be lifted. `SPU_INTERP_UNLIFTED` is slower and has documented hand-off limits (P `docs/SPU_INTERPRETER_LIFTED_HANDOFF.md`); it is a fallback, not the goal. Upstream has no `SPU_INTERP_MISS`.

---

## 9. Graphics: draws issued, nothing on screen

**Symptom.** In-stage (or any 3D scene) runs at a healthy FPS with hundreds of draws, but the window shows the clear colour (black, magenta, olive). Menus that draw into offset 0 may already look fine.

**Fastest diagnostic, in this order (Windows legacy D3D12, `libs/video/rsx_d3d12_backend.c` — the template default).**

1. `D3D12_DROP_STATS_EVERY=60 VP_SUBMIT=3`. Read `[PRESENTGATE] targets:`, `render_frame=YES/SKIPPED`, `records_full`, `not_vp`, `vp_fallback_ps`, deferred flips. This confirms or kills the present-gate theory in one run.
2. Look at the **GPU** copy of the offscreen colour target, not guest RAM. `RENDERDOC_DLL=… CELLMARK_DUMP=…` (pixel history, mesh viewer). Or temporarily call `rsx_d3d12_composite_from_offscreen(2)` before present. `GCM_GUEST_FB` / a CPU display of the guest address will show the CPU clear even when the GPU has the scene (P comment at the off_rt path).
3. `NV3089_GATE=<file>` during a scene frame; also log `cellGcm_current_scanout`. If the game blits the offscreen surface to the display buffer, that blit is a **CPU copy of guest RAM** and will move zeros / the clear.
4. Only if the GPU RT is truly empty: `VTX_DUMP=1 VP_NOFIXPROJ=1` (positions or constants all zero → missing SPU output). Then one knob at a time: `DEPTH_OFF=1`, `CMASK_FORCE=1`, `CULL_OFF=1`. `VP_FIXPROJ=1` also turns on **silently** when c0–c15 are all zero and can hide missing matrices — leave `VP_NOFIXPROJ=1` while diagnosing.
5. RPCS3 RSX capture (Alt+C) of the same scene: draw count, target list, one draw's vertices/constants, and the last methods before flip. Optional: toggle Write Color Buffers.

**Typical root cause.** **KNOWN** at P: the legacy D3D12 backend sets `has_display` only when some draw has `rt_off == 0`. Offscreen draws still execute on the GPU, but the ticker **does not Present**. PR #747 describes the resulting black frame with nothing useful in the log. **Worked example:** colour at `0x0B530000`, display buffers at `0x0D750000` / `0x0D3B0000` — all non-zero, so the window stayed on the magenta clear. `d3d12_set_viewport` is a **TODO no-op**; the shader epilogue uses identity x/y. That can shift or flip, and is **ASSUMED** not enough to cull every vertex. Depth, colour-mask, cull, and zero transform constants can cull everything.

**Fix pattern.**

- Treat a draw to the **current scanout offset** as onscreen, not only `rt_off == 0`.
- If NV3089 (or a similar transfer) is the present path, do a **GPU** blit from the matching `off_rt` instead of a CPU copy of guest RAM; wire `rsx_d3d12_composite_from_offscreen` (defined at P, **no caller** in `e85647a`).
- Longer term: move Windows onto the shared register-file draw engine (PR #748 was still open as of this writing).
- If vertices are zero, go back to the SPU job that should have written them (phase 7), not the viewport.

**Verified worked examples (Strikeforce, confirmed by in-stage runs, not theory).**

- **A depth-only clear started a new frame.** The shadow-map pass clears depth with no colour target bound. The backend treated that clear as a frame start and presented early, so the screen showed a half-built frame. Fix: a clear with no colour target must not begin or present a frame. Result: the stage ran at 62 FPS with no debug switches.
- **The per-frame vertex buffer overflowed.** Once each frame is complete, one frame must fit the upload heap. Strikeforce filled `MAX_VERTICES` (393,216) after the shadow pass plus 343 scene draws, and every later draw was dropped as `upload_empty`, so the ground, sky and hills were missing (the clear colour showed through). Diagnose with `D3D12_DROP_STATS_EVERY=60` and look for a rising `upload_empty` count. Fix: when the VB, IB or draw list is full, flush the recorded batch mid-frame **without presenting** and keep recording the same frame. Nothing is skipped. Result: sky, hills, characters and HUD render at about 90 FPS.
- **A depth surface at offset 0 was treated as "no depth".** Strikeforce's scene depth buffer lives at offset 0, and the backend read offset 0 as "no depth surface". The scene then fell back to the shared depth buffer, which is cleared on every target switch and every mid-frame flush, so the village buildings, trees and near ground failed the depth test (`DEPTH_OFF=1` made them appear). Fix: track a separate has-depth flag (`has_zeta`) and look the depth surface up by offset (`off_ds_find_z`), never `offset != 0`. Result: the village renders at about 94 FPS with no debug switches.
- **Cutting the strip on primitive restart is correct, but it wasn't the visible bug here.** Carry triangle-strip state across 256-index `DRAW_INDEX_ARRAY` chunks within one BEGIN/END, and cut on the restart index (`0x1DAC`/`0x1DB0`). This is worth doing anyway.
- Only results confirmed by a run go in this list. Leads that were disproved are not recorded as fixes.

---

## 10. Root-fix option: LLE of `libsre`

**Symptom.** A stream of SPURS/LFQueue/event-flag/waiter-token bugs, each patched one at a time.

**Typical root cause.** **KNOWN:** the PPU HLE is a guessed guest-memory protocol, while the other side is Sony's real SPU code (the game's lifted image, or `libsre`). P `docs/FIRMWARE_LLE.md` calls HLE SPURS "a source of endless problems on essentially every SPURS title."

**Fix pattern (needs the user's own spoken approval, then their own firmware).**

0. The user decrypts `libsre.sprx` from **their** firmware in RPCS3 (Decrypt PS3 Binaries). Record SHA-1 and firmware version. The file stays local.
1. Follow P's lift path (VERIFY each tool's `--help`; inFamous 2 uses `tools/lift_libsre.sh`): `prx_relocate`, `lift_prx`, `ppu_lifter --raw --base`, `prx_exports`, `extract_spu_images`, `build_spu_workloads`. Output under `generated/`, git-ignored.
2. **Self-test before the game:** load the lifted PRX, call the real `_cellSpursLFQueueInitialize` / `PushBody` on a 128-byte line, and check fullness, `AGAIN`, head-only waiter advance, and token `(wid<<8)|task`. Compare a line dump with RPCS3 at the first PushBody.
3. Hook the SPU kernel after `cellSpursInitialize` (upstream has only a title-specific hook; read a published port such as inFamous 2 `stubs.cpp`). Disable hand-written queue overrides — `libsre` replaces them. The runner already prefers a loaded PRX export over HLE (`prx_load_module`).
4. Boot to the same point. On `STAT` / assert, fix the **HLE state** `libsre` is reading (sysPrxForUser / lv2), not by force-HLE-ing the entry. Keep force-HLE only as a temporary bisect list that must end empty.
5. Keep `SPU_DUMP_MISS` + `SPU_MISS_FATAL` on for kernel images the lifter misses. Overlapping-overlay images stay a separate lifter problem; LLE does not fix them.
6. Fallback if the kernel will not run: lift only the queue / LFQueue entry points (DoD3 `gen_libsre.py` pattern), plus a real Attach, `LS 0x1DC = wid`, and token routing, gated by the same self-test.

Published end-to-end LLE runs were few as of this writing (the FIRMWARE_LLE doc and inFamous 2). Do not quote a success rate.

---

## 11. Automating the capture–lift–rebuild loop

**Symptom.** Manual miss → lift → rebuild cycles eat the day, and stalls are re-discovered by hand.

**What can be automatic.** SPU images and raw jobs that `SPU_DUMP_MISS` wrote: lift, register, rebuild, rerun. Scripted input (`PAD_SCRIPT`) to the same milestone. Parsing logs for unresolved NIDs, null calls, RSX drop stats, and hangs.

**What cannot.** Writing a correct new HLE body, a struct-layout fix, or a present-gate fix. The loop **reports** those. A human still has to think.

**Fix pattern.**

```
run (watchdog + stall timer)
  -> parse logs (misses, UNRESOLVED NID, null-call, D3D12 drops, PSO FAIL)
  -> lift new SPU dumps / jobmods
  -> report remaining HLE / RSX / hang items
  -> rebuild -> rerun
```

Stop after `--stable N` iterations with nothing new, or `--max-iter`. Compare a frame folder to an RPCS3 reference only as a report, not as a silent pass. The skeleton `auto_convert_loop.py` written for this work was **untested** against any title; read every TODO before a real run. Numbered patch files (Killzone how-to) keep each fix reviewable. Port-local save states (inFamous 2 `.p3ss`) help only after the state you want is reachable.

---

## 12. Measuring real progress

**Symptom.** Someone asks "how much of the game is done?"

**Rule.** Give **counts with sources**, plus a milestone table. Do not invent a single percentage. A registered handler is not necessarily a complete handler. Stale `missing_imports.txt` files drift (Strikeforce: 254/78 one day, 264/82 the next).

**Counts to take every campaign (recompute from the current build and a current run log).**

| Counter | How |
|---|---|
| Imported NIDs | `ppu_loader` log + `EBOOT.imports.json` |
| In generated HLE table | `ps3_hle_register(` in `ppu_hle_nids.cpp` |
| Filled only by port `.inc` | `stubs.cpp` / `ps3_load_prx_modules` |
| Still unresolved if called | imports minus table minus port fills |
| Unresolved **actually called** | `[hle] UNRESOLVED NID` (first-hit only unless `PS3_HLE_TRACE` / `PS3_HLE_TOP` is on — enable them when you need counts) |
| SPU images: extracted / lifted / unliftable / dispatch HIT vs MISS | `inventory.json`, `build_spu_workloads` log, run stderr |
| PPU functions emitted | `ppu_lifter` log (primaries + mid-function wrappers) |
| Null-call / `bctr to NULL` / unresolved icall | stderr; should be 0 at a healthy milestone |

**Milestones (yes/no, with a screenshot or log line):** boot, savedata, title / PRESS START, menus, loading finished, in-stage running, scene visible on the display, audio non-silent, input working.

**Worked example (Strikeforce, 2026-11-26 09:09 Asia/Kuwait, pre-in-game hang):** 346 imported NIDs / 26 libraries; 264 in the generated table; 10 more from port `.inc`; 72 with no handler; only 3 of those 72 called up to the black screen. SPU: 41 embedded images, 40 lifted, 1 unliftable (cloth); play19 dispatched 6 (5 lifted, cloth in the interpreter), 0 dispatch misses. PPU: 23,659 functions emitted; 0 null-call hits in play16–19. Milestones through Now Loading were yes; in-game was no. Those ratios describe **converted files**, not "percent of the game". Later the same day the stage ran at 63 FPS once the event-flag/wid bug was fixed, and audio peaked non-zero after the mixer-key + 6ch fixes — still without a single overall percentage.

When a milestone moves, append a dated row; do not rewrite history.
