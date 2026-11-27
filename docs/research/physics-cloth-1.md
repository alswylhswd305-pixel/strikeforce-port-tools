# Physics pass 1: cloth and scarf (bugs #3 and #10)

Title: Dynasty Warriors: Strikeforce (BLUS30471), ps3recomp port, build 1650_ovl1.
Written 2026-11-26 (Asia/Kuwait) by the physics/RE researcher. This was static research on the box only. Nothing was run on Saud's PC.

Labels:
- **KNOWN**: read directly from bytes, disassembly or source.
- **ASSUMED**: inferred and not yet proven.
- **VERIFY**: needs a run or log on Saud's PC.

No GPL code is copied here. RPCS3 behaviour is described in my own words with file:line pointers.

## Pins
- **R** = RPCS3 `0ca5eb0efe50ec4e8aa07892ab86d57842246eb4` (box: `/workspace/recomp-refs/rpcs3`). Paths are under `rpcs3/Emu/Cell/`.
- **P** = ps3recomp master `e85647a` (box: `/workspace/ps3-research/ps3recomp`). The `runtime/spu/*` and `libs/sync/cellSync.c` files are byte-identical to `/workspace/ps3recomp-study`.
- **S** = Saud's private changes, from the box snapshot `/workspace/ps3recomp-study/saud-prior/` (`pc-spu_workload.c`, `pc-spu_interp.c`, `port-overrides/*.inc`).
  - This is OLDER than Salem's 1650_ovl1 tree. **Every S line number must be re-checked against Salem's tree (VERIFY).**
- Cloth ELF on the box is `/workspace/sf-spu/cloth9000.elf`. It is the same file as `img9000.elf`; sha256 starts 65d1b660.
- Disassemblies:
  - `cloth_text.dis` (.text)
  - `ovl_cloth.dis` and `ovl_ponytail.dis` (made with `tools/spu_disasm.py --base 0x3080`)
  - `init.dis`

---

## 1. How the cloth job is fed and run

### 1.1 Image layout (KNOWN, from ELF headers and bytes)

| piece | LS | size | ELF p_paddr | notes |
|---|---|---|---|---|
| .SpuGUID / .init | 0x3000 / 0x3010 | small | resident | .init holds the ctors |
| **sec_cloth** overlay | 0x3080 | filesz 0x75F0 (section 0x75E8) | 0x40000 | overlay A |
| **sec_ponytail** overlay | 0x3080 | 0xB0C0 | 0x47600 | overlay B, same LS window |
| .text | 0xE180-0x16FF0 | | resident | entry **0xE190** |
| .rodata | 0x17020 | | resident | 0x17620 holds 0xFFFFFFFF_FFFC0000 (= −0x40000) |
| .data.libovis | 0x17690 | 0x30 | resident | the libovis overlay table, below |
| .bss | 0x17700 | 0x25300 | resident | 0x17700 = the 48-byte job header slot |

.data.libovis holds 16-byte entries of {LS addr, DMA size, paddr, resident flag}:
- Entry 0: {0x3080, **0x7600**, 0x40000, 0}
- Entry 1: {0x3080, **0xB100**, 0x47600, 0}
- The word at 0x176B0 is the entry count, 2.

Both entries start with resident = 0.

The DMA sizes are filesz rounded up. The ponytail DMA therefore reads 0x40 bytes past the end of the 0x126C0-byte table that the game sizes. On LS those bytes land in 0xE140-0xE17F, which is padding below .text, so this is harmless.

Salem's inventory says sec_cloth is 0x75F0 and sec_ponytail is 0xB0C0. Those are the ELF sizes and they are correct. The sizes the game actually DMAs are 0x7600 and 0xB100.

### 1.2 Task entry and main loop (KNOWN at instruction level; meaning of fields ASSUMED)

1. **0xE190** sets up the stack, saves r3-r6, runs `.init` at 0x3010, then calls **0x14B58**.
2. **0x14B58** calls the main loop **0xE1E8**. On return it EXITs: syscall 0 through the trampoline pointer at `[LS[0x2FB8] + 0xC4]`, which is the taskset context `syscallAddr` slot at 0x27C4.
3. **0xE1E8** splits the two SPURS task registers:
   - `r4.word0` → **r113** is the LFQueue EA. It is passed to the pop at 0xE338.
   - `r4.word1` → **r122** is the **overlay table EA**. It is passed to the libovis loader at 0xEEF8 and 0xEF38.
   - Together these are the 64-bit *taskset* argument (`taskset->args`).
   - `r3.word3` is the EA of a **48-byte block**. It is DMA'd to LS 0x17700 at 0xE370-0xE3C4 and is ASSUMED to be the cloth system header.
   - `r3.word2` is the EA of a **16-byte block**, DMA'd to the stack at 0xE3E0-0xE430.
   - `r3.word0` goes to 0x15380.
   - Together these are the per-task argument (`TaskInfo.args`).
4. **Loop 0xE330-0xE35C** calls the **LFQueue pop at 0x14BF0**:
   - The pop uses GETLLAR/PUTLLC on the queue line.
   - It reads the taskset context via `LS[0x2FB8]` at +0x98, +0xA0 and +0xD4. These are TaskInfo context-save, ls_pattern and taskId; the meaning is ASSUMED from the `SpursTasksetContext` layout in R `Modules/cellSpurs.h:1237-1265`.
   - When the queue is empty it issues **WAIT_SIGNAL** (`il r3,2` at 0x15030 and 0x151E8, `bisl` to the trampoline).
   - If the pop returns non-zero, the loop retries forever.
5. After a pop, a branch at 0xE454 picks one of two paths:
   - **sec_cloth**: load overlay entry 0x17690 (0xEEE4-0xEF0C) → work at 0xE458 → unload at 0x15B20.
   - **sec_ponytail**: load entry 0x176A0 (0xEF20-0xEF4C) → work at 0xE850 → unload.
   - What decides the path per job is **not decoded yet (VERIFY by logging overlay GET source offsets, D2)**.
6. Between jobs it calls **POLL** (0x14BD0, syscall 3). If bit 2 of the result is set, it calls **YIELD** (0x14B88, syscall 1), then returns to the pop.
7. **The libovis loader 0x15B58-0x15E0C** finds the entry and **skips the load if the resident flag is set**. Otherwise it issues plain GETs (cmd 0x40) of at most 0x4000 bytes each:
   - source = `table_EA + paddr − 0x40000` (using the −0x40000 constant at 0x17620)
   - destination = LS 0x3080
   - The unload (0x15B20) clears the flag. **Every job therefore re-DMAs its overlay fresh from the PPU-side table.**

### 1.3 Inside the overlays (KNOWN counts; meaning ASSUMED)

**Overlay float opcode counts:**

| overlay | fm | fma | fnms | fi | frest | frsqest |
|---|---|---|---|---|---|---|
| sec_cloth | 312 | 299 | 94 | 55 | 28 | 27 |
| sec_ponytail | 695 | 664 | 198 | 104 | 60 | 44 |

**Overlay DMA:**
- sec_cloth: list GETL ×6 and list PUTL ×5, plus plain GET/PUT, and 4 lock-line atomics (`MFC_RdAtomicStat`).
- sec_ponytail: GETL ×3 and PUTL ×2.

**Float constants** (upper-halfword immediates):
- 1.0, 0.5, 2^23
- ~0.7071 (√½)
- a ~1e-6 epsilon
- two small tolerances, with upper halves 0x3C23 and 0x3A83

**No immediate for a timestep (such as 1/60) or a gravity value.** dt, gravity and wind are ASSUMED to come from the DMA'd header or job data.

**Channels read across .text and both overlays: only `MFC_RdTagStat` and `MFC_RdAtomicStat`** (KNOWN).
- No SPU decrementer and no signal-notify reads.
- **The SPU side has no clock of its own.** Any time input comes from PPU-written memory.

The overlays call back into resident .text helpers (0xEF68, 0x10918, 0x11A88, 0x16060).

**Pattern (ASSUMED):** gather particles and constraints with list GETs, solve with Newton-Raphson using frsqest/frest refined by fi, then scatter positions with list PUTs to main memory. The RSX then reads that main-memory buffer through the IO-mapped vertex stream:
- P `libs/video/rsx_vertex_fetch.c:64-77`: guest memory is read directly at draw time.
- Offset bit 31 selects MAIN (IO map) vs LOCAL.
- There is only a per-draw cache (Saud's backend `rsx_d3d12_backend.c` ~6532, VERIFY in Salem's tree). So a PUT that lands at the right EA before the draw is visible to it.

### 1.4 PPU side (partly KNOWN from imports; creation args VERIFY)

EBOOT imports (from `progress-src/out/EBOOT.imports.json`):
- `cellSpursCreateTask` 0xBEB600AC
- `cellSpursLFQueuePushBody` 0x8A85674D
- `cellSpursLFQueueInitialize` 0x011EE38B
- `cellSyncLFQueueSize` 0x167EA63E
- `cellOvis` 0x82F294B2 and 0xA876C911 (GetOverlayTableSize and InitializeOverlayTable)

The EBOOT payload is SCE-wrapped on the box, so I could not disassemble the PPU creator. That will need runtime logs.

**Expected flow (ASSUMED):**
1. The PPU loads the cloth ELF and calls InitializeOverlayTable to copy the overlay segments into a table.
2. It creates a taskset whose args = {queue EA : table EA}.
3. It creates the task with args pointing to the header and parameter blocks.
4. Every frame it pushes one or more cloth jobs into the LFQueue.
5. Later it draws the cloth from the PUT buffer.

`hang-1532/SUMMARY.md` shows `func_00543DA4` spinning until two LFQueues at obj+0x30 and obj+0x34 drain. **That these are the cloth queues is ASSUMED, not shown (VERIFY with the `[sf-lfq] init` q values).**

---

## 2. RPCS3 vs port, item by item

| item | RPCS3 (R) | port (P / S) | verdict |
|---|---|---|---|
| Default SPU decoder | LLVM recompiler (`system_config.h:27`) | lifted C + interpreter fallback | n/a |
| Float accuracy setting | `spu_xfloat_accuracy` defaults to **approximate** (`system_config.h:66`; enum `system_config_types.h:386-392`) | always ISA-exact helpers | port is *stricter* (KNOWN) |
| fa / fs | interpreter adds in host float with the host rounding mode (`SPUInterpreter.cpp:1177-1189`) | exact SPU lane: truncation, extended range, denormal→0 (P `spu_helpers.h:600-617` spec; `717-740` lanes; double fast path with truncation `753-778`) | port exact (KNOWN) |
| fm | host multiply, then flushes denormals and patches extended exponents (`SPUInterpreter.cpp:1191-1225`) | exact lane (P `spu_helpers.h:724`) | port exact |
| fma / fms / fnms | **two host roundings**, multiply then add (`SPUInterpreter.cpp:2073-2125`) | single exact fused-then-truncate lane (P `spu_helpers.h:730`, `773`) | port exact; RPCS3 approximates |
| frest / frsqest | fraction LUT plus exponent table (`SPUInterpreter.cpp:690-735`) | same LUT method, commented "matches RPCS3 LUT" (P `spu_helpers.h:1667-1714`) | same (KNOWN) |
| fi | done in float (`SPUInterpreter.cpp:1522-1535`, marked TODO) | integer-exact interpolation (P `spu_helpers.h:1361-1397`) | port exact |
| "precise" interpreter variants | exist (`SPUInterpreter.cpp:2194` FREST, `2219` FRSQEST, `2349` FA, `2353` FM, `2679` FI, `2780` FMA). I found no selection site in this commit, so the default interpreter uses the fast versions (ASSUMED) | n/a | n/a |
| cflts / csflt | `SPUInterpreter.cpp:1548-1580` | P interp uses the same helpers as lifted code (`spu_interp.c:212-240`) | equivalent |
| Unimplemented opcode | n/a | logs "unimplemented op" and halts (P `spu_interp.c:349-352`). **Every mnemonic in .text and both overlays has a case** (KNOWN, diffed) | not a cause |
| MFC list DMA | `do_list_transfer` (`SPUThread.cpp:2927`). Each element's LS address keeps the EA's low 4 bits and advances by the size rounded up to 16 (`SPUThread.cpp:3286`, `3351`, `3444-3447`) | `mfc_run_list` follows the same rules, with stall bit 31 and 15-bit size (P `spu_dma.h:870-940`; element layout `99-108`) | same (KNOWN) |
| Task ELF load | `spursTasksetLoadElf` **stops at segments with paddr ≥ 0x40000**, so overlays are NOT loaded at task start (`Modules/cellSpursSpu.cpp:1997-2050`, called from `1777` and `1824`) | `spu_elf_load_to_ls` loads **all** PT_LOADs by vaddr, so sec_ponytail overwrites sec_cloth at 0x3080 (P `spu_workload.c:181-218`) | differs; harmless (ASSUMED), because the loader always re-DMAs (resident flag starts at 0) |
| Task registers | r3 = TaskInfo.args (128-bit). r4 preferred dword = taskset->args, other dword = spurs (`Modules/cellSpursSpu.cpp:1401-1403`) | r3 = LS 0x2780..0x278C. r4 = {0x2768, 0x276C, 0x2760, 0x2764}, **set only if spurs_lo ≠ 0** (P `spu_lifted_job.h:203`, `286`) | layout matches by construction; **values VERIFY** (D0) |
| Taskset syscalls | handled by the SPURS kernel (`Modules/cellSpursSpu.cpp:1366` → ProcessSyscall) | P `spu_channels.c:2334+`: EXIT halts except for image 22 (2373/2382); WAIT_SIGNAL parks via `spu_taskset_wait_signal` (2396-2459). **S `pc-spu_interp.c:484-486` runs img 9000-9031 syscalls as image 22** | VERIFY that wakes reach img 9000 |
| libovis | `Modules/cellOvis.cpp:33-43`: both exports are **todo stubs that return OK**. `cellSysmodule.cpp:91`: OVIS has no PRX path. How the real table gets filled under RPCS3 is open (VERIFY; possibly LLE firmware) | S `port-overrides/strikeforce_ovis.inc` copies every paddr ≥ 0x40000 PT_LOAD to table + (paddr − 0x40000) and returns 0x126C0. The log line "filled 0x126C0 bytes, 2 overlay segs" was seen (`loading_hang_chblock.txt:4`) | content believed correct; **timing and identity VERIFY** (D3) |
| LFQueue size | `Modules/cellSync.cpp:1527-1563` (push-head minus pop-head, modulo 2·depth) | P `libs/sync/cellSync.c:768-777` uses the host-layout bug; S override fixed this in build 1545 | fixed |
| Debugger | `GDB.cpp:582`: SPU thread selection is commented out, so **the GDB stub is PPU-only** | n/a | affects the parity method (section 5) |

**Net:** the port's float math is closer to the hardware than RPCS3's default, and RPCS3 draws the cloth correctly (gfx-advisor H1a: Zhao Yun's back cloth hangs right). Last-bit float differences therefore **cannot** explain a sheet stretched to a fixed far point. List-DMA rules match. The real difference is in **how the task is run** (dispatch, wake, stop, registers, overlay bytes), not the math.

---

## 3. What the symptoms say (KNOWN from images)

Images checked:
- `saud_scarf_guard_1629a/b.jpg`
- `freeze-1555/live_1822/snap_182502_client.png`
- `freeze-1555/live_1822/player_face_1826.jpg`

What they show:
- The part of the scarf near the body (skinned or pinned vertices) follows the skeleton but **does not sway**. This is bug #10.
- A cyan or beige strip runs from the shoulder to **one stable far point** at the upper right. In the stretched case this becomes a huge sheet that covers the screen. This is bug #3.
- There is no jitter, no explosion to NaN-like spikes, and no flicker.

**The free particles are never advanced.** Either the job output never reaches the buffer the draw reads, or the buffer holds stale or initial data. Bugs #3 and #10 are **one bug**: #10 is how it looks when the free part happens to sit near the body, #3 when it sits far away.

Diagnosis that is free at runtime, needing no build (VERIFY):
1. Walk the character a long way and watch the far point.
   - If it stays at a fixed **world** spot, the particles were written once (or initialised) and are then frozen.
   - If it sits at the map origin, the buffer was never written.
2. Then turn the camera. A stretch that tracks the camera points to a view-space or parameter mixup instead.

---

## 4. Ranked root-cause hypotheses

Stiffness cause by category:
- **Job not dispatching or finishing:** most likely, H1.
- **Wrong input, or input to the wrong EA:** H2/H4, next.
- **Output not uploaded:** H3. The port has no persistent VB cache, so this means "written to a different EA", not "not uploaded".
- **Float math:** least likely, H5.

### H1 (rank 1, ASSUMED): the interpreted cloth task (img 9000) does not consume and complete jobs every frame in-stage
Sub-causes, in order:
- **H1a: not dispatched in that run.**
  - The box copy of `PLAY_Strikeforce.bat` sets `SPU_INTERP_UNLIFTED=1` but **not** `SPU_INTERP_MISS=1`. `sfrun.ps1:13` sets both.
  - The env of the 18:22 `PLAY_Strikeforce_FIX1650.bat` is unknown.
  - The stretch was **also** seen in sfauto runs (with MISS=1), so H1a alone cannot be the whole story.
- **H1b: dispatched, then ended early.**
  - S `sf_interp_miss_entry` (`pc-spu_workload.c:1617-1626`) runs the interpreter once and treats **any** return as task end.
  - P `spu_interp.c:496` returns early ("rejoin") when `image_id >= 0` and a lifted function is found at the PC. Its own comment says pure interpretation should use a negative id.
  - img 9000 is positive. Any lifted registration that `spu_lifted_lookup` resolves at a cloth PC (image-0 wildcard, resident overlay) would end the cloth task silently.
  - The only trace is one of the first 16 `[sf-spu] interpreted task img=9000 ... stopped code=... pc=...` lines, or `[spu] CROSS-IMAGE dispatch ... requested by image 9000`.
- **H1c: parked forever.**
  - The pop's WAIT_SIGNAL parks the task, and the push-side wake (S `strikeforce_lfqueue.inc`) only signals waiters it can find from `push2.pack` / `m_hs1`, and only for task id < 128.
  - If the waiter id the SPU stored doesn't match what the wake reads, the task sleeps forever.
  - The SPU writes it via ctx +0xD4, so a wrong taskId in our context breaks this too.
  - Freeze logs show WAIT_SIGNAL sleepers in several tasksets (`stderr_tail_155051:80-84`).

### H2 (rank 2, ASSUMED): wrong task registers or context
- If r4 is not exactly {queue EA, table EA} (r4 is left unset when `spurs_lo == 0`, P `spu_lifted_job.h:286`), or r3 is not TaskInfo.args, the task pops a wrong queue or DMAs overlays from a wrong EA.
- The result is either garbage code at 0x3080 or a silent idle.
- Same for TaskInfo +0x98/+0xA0/+0xD4 in the context built at S `pc-spu_workload.c:845-860`.

### H3 (rank 3, ASSUMED): output and draw disagree
The overlay PUTLs land in a buffer the draw does not read. Possible causes:
- a double-buffer index from a PPU frame counter
- an IO-offset (bit 31 MAIN) translation in `rsx_vertex_fetch.c:64-77`
- the draw happening before the job completes (missing sync on the completion atomics)

### H4 (rank 4, ASSUMED): inputs zero or stale
- The 48-byte header or job item carries dt, gravity or wind of 0. Possible sources:
  - a stubbed time source on the PPU
  - an unresolved import faking `CELL_OK`. Log: `[hle] UNRESOLVED NID 0xC044FAB1 ...` and five others in `log_scan_1825.txt`.
- That gives stiffness, but by itself does not explain the far-point stretch.

### H5 (rank 5, LOW): float semantics
Ruled down by section 2. The port is ISA-exact and RPCS3 is approximate yet correct. All opcodes are implemented, and list-DMA rules match.

### Overlay swap question (Salem's (a))
The swapping logic is the game's own libovis code running inside the task. It re-DMAs the right overlay before every use. The port's extra ELF-time load into 0x3080 is overwritten by that DMA.
- Overlay swapping matters only if the **table bytes** are wrong or missing at DMA time (H2/H3-type; checked by D3), or if a lifted-overlay residency registration makes the interpreter rejoin the wrong code (H1b).
- **It is not float math.**

## Single most likely root cause and one fix

**Most likely root cause (ASSUMED; confidence low-to-medium; no fix1650 full log and no PPU disassembly on the box):** the cloth task img 9000 is not running its per-frame solve to completion in-stage, so the free particles never move. The most code-evident mechanism is **H1b**: a pure-interpreted image running with a *positive* image id, whose single interpreter run is treated as the whole task. Any early return (rejoin, cross-image hit, or a stop the wrapper does not re-enter) kills the persistent cloth task for the rest of the session without a visible error.

**The one fix (apply only after V1 confirms that img 9000 dispatched and then stopped or rejoined early):**
- Run SPU_INTERP_MISS images as **true pure-interpreter images**: a negative interpreter image id, as `spu_interp.c` ~490-496 documents.
- Keep the 0xA70 syscall service in `pc-spu_interp.c:484` keyed to the miss-image flag rather than to the numeric range.
- Keep `sf_interp_miss_entry` re-entering the interpreter until a real SPU stop or a taskset EXIT, the same way the normal dispatcher loops.

This fix is generic for any unliftable SPURS task. It has no cloth special case, no forced values, no hardcoded constants and no skips.

**If V1 instead shows the task alive and popping each frame,** this fix is wrong. Move to H2 → H3 → H4 in that order with D0-D5. The general fix then becomes "make the task run under the exact SPURS task contract RPCS3 uses", in the generic task-start code:
- r3 = TaskInfo.args
- r4 = taskset args : spurs
- the correct TaskInfo and taskId in the context
- every push wakes the stored waiter

---

## 5. Verification and fix plan for Salem (Saud's PC; test copy only; one change per build)

Rules (playbook):
- Work on a **copy** of the exe folder.
- Make **one** change per build.
- Diagnostic logs are temporary.
- Unsticks, skips and forced values are diagnostics only, never the fix.
- Log caps can lie. `PS3_LOG_FIRST(…,16)` hides later events, so prefer per-second counters.

### V1: no rebuild; read what already exists
1. In `PLAY_Strikeforce_FIX1650.bat` and whatever launches the sfauto runs: are `SPU_INTERP_UNLIFTED=1` **and** `SPU_INTERP_MISS=1` both set?
2. Grep `fix1650_stderr.log` and the latest sfauto stderr for each of these:
   - `SPU_INTERP_MISS` (expect the KSG2PS3SPUCloth fp 357AF568F39B68C1 → img 9000)
   - `interpreted task img=9000` (its `stopped code=… pc=…`; any pc other than an EXIT means an early end)
   - `CROSS-IMAGE` with `image 9000`
   - `[mfc] REJECTED` with `img=9000`
   - `unimplemented op`
   - `[sf-ovis]` (both lines; note the table EA)
   - `[sf-lfq] init` (note every q EA)
   - `[sf-lfq] push` (which q and task get woken)
3. Report how many times each appears and the first and last timestamps.

### V2: build A = diagnostics only (D0 + D1 + D2)
- **Env:**
  - `SPU_INTERP_UNLIFTED=1 SPU_INTERP_MISS=1 SPURS_TASKSET_TRACE=1 SPU_INTERP_STATS=<seconds>`
  - plus HLE arg tracing for `BEB600AC` (CreateTask) and `8A85674D` (PushBody), via `PS3_HLE_ARGS` if your tree has it
  - plus `SPU_DUMP_MISS` if available, to confirm the bytes match the box ELF hash
- **D0:** from `[taskset] run image=9000 r3=… r4=…`, check r4.word0 = a `[sf-lfq] init` q, and r4.word1 = the `[sf-ovis]` table EA. Check r3 matches the CreateTask args.
- **D1 (temporary log):** per-second counters for img 9000, printed **before** the image id is swapped to 22:
  - pops returning 0 (detect the return at pc 0xE35C, or count the 0x14BF0 entries)
  - WAIT_SIGNAL entries
  - WAIT_SIGNAL returns
  - POLL/YIELD
  - interpreter returns
  - **Expected:** pops per second track frames per second in-stage, and the task never "stops".
- **D2 (temporary log):** for img 9000, every GET/GETL/PUT/PUTL as {pc, cmd, ea, lsa, size}, rate-limited per second (not first-N).
  - Flag any GET with source inside [table, table+0x12700); the source offset says which overlay loaded.
  - Keep the PUT/PUTL EA ranges for D5.

### V3: build B = overlay and input check (D3 + D4)
- **D3:** on the first instruction at LS 0x3080 after each loader run, hash LS 0x3080..+0x75F0 (cloth) or +0xB0C0 (ponytail). Compare with the hashes of `sec_cloth` / `sec_ponytail` in the ELF (from file offsets 0x9700 / 0x10D00 in `cloth9000.elf`, i.e. the PT_LOAD offsets, or from `SPU_DUMP_MISS`).
- **D4:** at pc 0xE360 (after a successful pop), dump the popped item and the 48 bytes at LS 0x17700, once per second. Zeros where dt or gravity should be point to H4.

### V4: render side (D5)
- Run `DRAW_LIMIT` plus `VP_ATTRS` / `VP_ATTRS_FP` / `VP_ATTRS_DUMP` on the scarf draw (gfx-advisor H1a recipe). Translate attr0's offset (bit 31 = MAIN → IO map) to an EA.
- Check that the EA falls inside a D2 PUT/PUTL range from the **same** frame. A mismatch points to H3.

### Then apply the one fix
- Do this only if V1 or V2 point to H1b.
- Make the single change in a test-copy build, then repeat the D1 counters and the visual "walk away" test.
- If those pass, run the parity check below.

---

## 6. Review of Salem's proposal

Salem's inventory facts check out against the box ELF:
- image 375200614 and fp 357AF568F39B68C1 (not re-hashed here)
- entry 0xE190
- sec_cloth at LS 0x3080 with size 0x75F0, and sec_ponytail at LS 0x3080 with size 0xB0C0

One correction: the sizes the game DMAs are **0x7600** and **0xB100**. The table offsets are 0 and **0x7600** (paddr 0x47600 − 0x40000).

| step | verdict | why / what to change |
|---|---|---|
| (1) Lift the resident image and the two overlays separately | **CHANGE (defer)** | It buys speed and coverage, not correctness. A correct interpreter already gives PS3 behaviour. Do it only **after** D1 shows the interpreted task consuming every frame and the parity check passes, so we never debug a lift and a run-contract bug at once. |
| (2) Register them in `spu_workloads.c` | **CHANGE (defer, same as 1)** | When it is done, register the resident .text as the task image, and each overlay as overlay code keyed by its content, not as a wildcard image 0. Image-0 wildcards are exactly what can trigger H1b rejoins. |
| (3) In `strikeforce_ovis.inc`, after InitializeOverlayTable, call `spu_overlay_register_verified_region` for table+0 and table+0x7600 | **CHANGE** | It is only meaningful once overlays are lifted. Until then it could make the interpreter rejoin lifted code (H1b), so it is harmful now. When used, pass the real signature (P `spu_channels.c:1999`): content_ea = table+0 / table+0x7600, load_lsa = 0x3080, span = **0x7600 / 0xB100** (the DMA sizes, which arrive in ≤0x4000 chunks; continuation GETs are tracked by `spu_overlay_note_get`, `spu_channels.c:2215-2260`), image_id = the cloth task's id, and the code segments of each overlay. |
| (4) Verify with SPU_INTERP_STATS and VP_ATTRS | **KEEP, extend** | Add SPURS_TASKSET_TRACE (D0), per-second counters (D1), the DMA log (D2), the overlay hash (D3) and the header dump (D4). Without D1 and D2, STATS alone cannot tell "running" from "running the right job into the right buffer". |

### Salem's question (b): parity method
**Verdict: CHANGE.** Watching the same vertex buffer live in both emulators over N frames is not a valid comparison:
- **The RPCS3 GDB stub is PPU-only** (R `GDB.cpp:582`), so SPU state cannot be stepped there.
- **The inputs differ** between the two runs: animation phase, frame timing, dt.

Proposed method:
1. **Capture in RPCS3**, PPU-side, Interpreter decoder, GDB at 127.0.0.1:2345:
   - Break at the import stub for `cellSpursLFQueuePushBody` (0x8A85674D) in-stage.
   - Record the pushed item, the 48-byte header at r3.word3 and the 16-byte block at r3.word2 (EAs from the CreateTask args), and the contents of every input EA the job will GET. Use the D2 list from our run to know which EAs.
   - Break again at the **next** PushBody, by which time the job is done. The completion atomics are ASSUMED to be what the PPU waits on.
   - Record the PUT ranges from D2.
   - Sync point: the PushBody call itself, matched by its job item content, not by frame number.
2. **Replay offline:**
   - Load the captured guest memory plus the cloth ELF into our interpreter in a small harness (box or test copy).
   - Set up the same task registers and push that one job.
   - Diff our PUT output against RPCS3's.
3. **Metrics:**
   - per-vertex distance
   - constraint (edge) length error against rest length
   - sway as the RMS of free-vertex distance to the pinned root, over a short sequence of captured frames
4. **Tolerance:** do not pick a number in advance. Measure the RPCS3-vs-RPCS3 spread by running the same capture with `spu_xfloat_accuracy` = accurate and = approximate (`system_config.h:66`). Our result must sit inside that spread.
5. **Live in-game check:**
   - the D1 counters (the job runs every frame)
   - D5 (the draw reads the buffer we PUT)
   - the side-by-side visual of the same character and stage against RPCS3

---

## 7. Not verified / open
- No full `fix1650_stderr.log` on the box (only `log_extract_1828.txt`, which has no img 9000 lines). Dispatch status in-stage is **unknown** → V1.
- No PPU disassembly (the EBOOT is SCE-wrapped on the box). Creation args and the queue→task mapping come from runtime logs → D0.
- How RPCS3 fills the overlay table when its cellOvis HLE is a stub (`cellOvis.cpp:33-43`) is open. LLE firmware is ASSUMED.
- All S line numbers come from an older snapshot → re-check in Salem's 1650_ovl1 tree.
- The cloth vs ponytail path selection per job is not decoded → D2 shows it.
- A possible link between a dead cloth consumer and PPU freezes (`func_00543DA4` waiting on LFQueues draining) is ASSUMED only.
