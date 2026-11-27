# Root-fix plan: SPURS LFQueue / queue handling for Strikeforce (2026-11-26, ~09:10 UTC+3)

Saud asked for a **root** fix, not more per-queue patches.

Research only. Nothing was built or run, and Saud's PC was not touched.

Pins:
- **P** = ps3recomp `e85647a33ce5f9391788f0e3f52ab395a7fe6a89` (https://github.com/sp00nznet/ps3recomp/blob/e85647a33ce5f9391788f0e3f52ab395a7fe6a89/)
- **DoD3** = soyjxck/dod3-recomp `ab2c53397624486d76d602bc7f89ac1d805c2904` (MIT)
- **DeS** = timboat/demons-souls-recomp `9637b204f031c72839129d49e5b0586d4bcfdeed` (MIT)
- **IF2** = bhuiyah/infamous2-recomp `28b80f1667c40a681021b2557b557250533c74f1`
- **WB** = Saud's Nov 1 Workbench files in `/workspace/sf-shared/event-queue-files/`

## 1. What "the class of bugs" is

Every Strikeforce queue bug so far comes from the same thing: **the guest-memory protocol of a SPURS primitive is hand-guessed on the PPU (HLE) side while the other side is Sony's real code** (the game's lifted SPU code, or libsre's SPU kernel).

Examples:
- **Init layout.** P's `_cellSpursLFQueueInitialize` writes depth at +0x0C (P `libs/spurs/cellSpurs.c#L4168`). DoD3 found the same bug, so did DeS, and so did WB (`run-004/evidence/managed/actual-lfqueue/native-lfqueue.patch`).
- **Missing functions.** P has no `_cellSpursLFQueuePushBody`/`PopBody` (git grep on P).
- **Attach does nothing.** `AttachLv2EventQueue` is a no-op (P `cellSpurs.c#L4191`), so blocking pushes can't park.
- **Wrong waiter token.** The token is `(wid << 8) | taskId`, decoded by libsre's own routine 0x010127CC (DoD3 `src/kernel/spurs_lfqueue.cpp#L226-L231`). The HLE gives every taskset wid 0 (same lines). WB also found the token is built from kernel LS 0x1DC (`strict-native-wid0-only.patch`).
- **Wrong struct entirely.** DeS first wrote the SPURS *queue* as an LFQueue (fix 12), which was wrong. libsre's `cellSpursQueue` has its own layout (fix 19, DeS `docs/NOTES.md#L115-L118`, `#L173-L189`).
- **Scheduler gaps beyond queues.** The Nov 1 WB run stopped at native WAIT_SIGNAL because task context save/restore was missing. `EventFlagWait` was still guarded (`docs/Strikeforce_EventQueue_20261101/RESULT_EN.txt`, `RESULT.json` → `next_step`).
- ps3recomp's own docs say HLE SPURS "has been a source of endless problems on essentially every SPURS title" (P `docs/FIRMWARE_LLE.md#L32-L40`).

So a fix "removes the class" only if the PPU side of these primitives stops being a guess.

## 2. The options

### (A) Faithful hand reimplementation of the LFQueue family, plus a self-test

- **What it means:** correct Init (m_bs = -1, direction, init), PushBody/PopBody, a real Attach (lv2 queue in m_eq_id), waiter rings (push2/m_hs1, pop2/m_hs2), and LS 0x1DC = wid.
- **What the ports actually did** (KNOWN):
  - DeS fix 5 is a "port of RPCS3's cellSync.cpp … GetPushPointer/CompletePushPointer" (DeS `docs/NOTES.md#L81-L84`; `patches/ps3recomp-local.patch` ~L10347-10356). That is **GPL-derived**. ps3recomp forbids it ("Don't port code from GPL projects", P `CONTRIBUTING.md#L260`; README `#L399`), and Saud said no GPL code. **Do not reuse DeS's push code.**
  - DoD3 did **not** hand-port the push. It lifted Sony's own functions (see C below). Only its Init is hand-written, "write for write against libsre's syncLFQueueInitialize" (DoD3 `spurs_lfqueue.cpp#L1-L24`).
- **About the upstream "self-test"** (KNOWN): `runtime/spu/tests/test_lfqueue_main.c` + `gen_test_lfqueue.py` test the **host-native** `libs/sync/cellSync.c` LFQueue (P `runtime/spu/tests/test_lfqueue_main.c#L1-L13`, `test_lfqueue.deps`). Its SPU program only does a plain DMA GET/PUT. It never touches the 128-byte line with GETLLAR/PUTLLC.
  - **It proves nothing about the guest-layout SPURS LFQueue.** A new test would be needed.
- **Does it remove the class?** **No** (ASSUMED, by construction). It fixes the LFQueue family, but the next primitive (SPURS queue, event-flag PPU wait, WAIT_SIGNAL context) is still hand-guessed. WB already hit two of those.
- **Effort:** medium. **Risk:** you are rewriting by hand exactly the kind of code that broke before. Without libsre there is no oracle except RPCS3 run traces, because RPCS3's own HLE for these functions is todo.

### (B) LLE: lift the real `libsre.prx` from Saud's own firmware (what IF2 did)

- **Upstream already supports this** (KNOWN):
  - `runtime/prx/prx_loader.h` loads a relocated, lifted PRX and keeps an export registry (`#L1-L30`, `#L101-L112`).
  - `ps3_hle_call` sends a NID to the lifted libsre export **before** any HLE or ctx override (P `runtime/ppu/ppu_hle.cpp#L156-L161`, `#L477-L490`; ctx overrides come later at `#L775`). Once libsre is loaded, `strikeforce_lfqueue.inc` is simply bypassed.
  - The tools exist at P: `prx_relocate.py`, `lift_prx.py`, `prx_exports.py`, `ppu_lifter.py --raw --base`, `extract_spu_images.py`, `build_spu_workloads.py`.
  - The doc is P `docs/FIRMWARE_LLE.md`.
- **Port evidence** (KNOWN):
  - IF2 `tools/lift_libsre.sh` runs that pipeline. Its pin `a679051` is an ancestor of P.
  - IF2 NOTES L443-444: without libsre "the game ran without libsre (cellSpurs HLE: no gameplay)".
  - IF2 CMakeLists L172-176: the HLE "lacks _cellSpursLFQueuePushBody and stalls inFamous 2's psarc decompressor".
- **Does it remove the class?** **Yes, for everything inside libsre** (KNOWN from design, P `FIRMWARE_LLE.md#L160-L162`). LFQueue, SPURS queue, event flags, taskset/task scheduling, and the SPU-side context switch all become Sony's code. It does not cover other modules: cellOvis (libovis) and the game's own SPU images still need lifting (P `FIRMWARE_LLE.md#L177-L185`).
- **Risks** (KNOWN):
  - "Validated on one title so far (Yakuza: Dead Souls)… treat 'this will fix your SPURS hang' as a hypothesis" (P `FIRMWARE_LLE.md#L164-L175`).
  - Running the SPU kernel exposes SPU lifter bugs (`#L177-L185`).
  - Mixing LLE and HLE breaks things: YDKJ needed `YDKJ_FORCE_HLE` because libsre's EventFlagInitialize returned STAT against partly-HLE state (P `ppu_hle.cpp#L477-L505`).
  - The SPU kernel spawn hook upstream is title-specific (`FLOW_SPURSKERNEL`, P `ppu_hle.cpp#L762-L770`). **Strikeforce needs its own runner glue** (FIRMWARE_LLE Step 4 says this is per-game, `#L140-L158`).
  - Firmware-specific addresses: IF2 notes another libsre build changes kernel LS addresses (IF2 NOTES L289-290, L343).
- **Precondition:** a decrypted `libsre.prx` from **Saud's own** firmware (install firmware in RPCS3, then Utilities → Decrypt PS3 Binaries on `dev_flash/sys/external/libsre.sprx`, IF2 `tools/lift_libsre.sh#L21-L22`).
  - The Nov 1 WB runs deliberately used an empty firmware directory and "no new decryption" (`RESULT_EN.txt`). **This is a decision for Saud.**
- **Effort:** largest up front (runner glue plus SPU-kernel bring-up). After that, the per-primitive fixes go away.

### (C) Targeted LLE: lift only libsre's queue functions (what DoD3 did)

- **How DoD3 does it** (KNOWN):
  - `tools/gen_libsre.py` (170 lines) lifts `_cellSyncLFQueueGetPushPointer`/`CompletePushPointer` (+2 variants) and `_cellSpursQueueInitialize`/`PushBody`/`PopBody`, plus everything they reach, from the user's `libsre.prx` at build time.
  - Calls into libsre internals are hooked back to the HLE: SendSignal, workload → taskset (DoD3 `tools/gen_libsre.py#L1-L50`; `CMakeLists.txt#L245-L270`).
  - The output goes to the build tree and is never committed.
  - `spurs_lfqueue.cpp` (261 lines) is a thin wrapper.
- **Does it remove the class?** Only the **queue-protocol** part, because the line updates are Sony's code. The scheduler, event-flag and WAIT_SIGNAL parts stay HLE. DoD3 itself still blocks by polling because Attach is a stub (`spurs_lfqueue.cpp#L19-L24`), and still sends signals to every taskset because of HLE wid 0 (`#L229-L231`).
- **Effort:** small to medium. Same firmware precondition as B. The libsre addresses in the script are firmware-build specific (ASSUMED; VERIFY against Saud's build).

## 3. Licensing

- **A:** fine only if clean-room, i.e. written from behaviour or from Saud's own libsre disassembly. **Not** from DeS fix 5 (RPCS3-derived) and not from RPCS3. KNOWN from the cited lines.
- **B and C:** no GPL code. The code is Sony firmware lifted locally.
  - ps3recomp: "no output derived from firmware" may be committed (P `FIRMWARE_LLE.md#L55-L64`, `#L212-L221`). A binary that embeds lifted firmware is "legally fraught", so keep it local (`#L198-L206`).
  - The Strikeforce repo (AGPL-3.0, `strikeforce-recomp-repo` commit 2c4c772) can hold the **glue and scripts** but never `generated/` libsre output.
  - DoD3/IF2 tooling is MIT/permissive. Reuse it with attribution. VERIFY IF2's license file before copying scripts.
- Not legal advice.

## 4. Recommendation: **B (full libsre LLE)**

B is the only option that removes the whole class, including the WAIT_SIGNAL/EventFlagWait gaps that WB already hit.

- **Fallback:** if Step 3 below shows the SPU kernel can't be brought up in a reasonable time, use C. It shares Steps 0-1.
- **Do not choose A as the root fix.** If Saud declines to use firmware, A is the only option left. In that case it must be clean-room and gated by the RPCS3-trace check in Step 2b.

## 5. Ordered steps for Salem

Labels: **KNOWN** = from the sources above. **ASSUMED** = my reading, not proven. **VERIFY** = how to check it.

0. **Get Saud's OK and the input.** Saud decrypts `libsre.sprx` from his own firmware (RPCS3 → Decrypt PS3 Binaries). Record the SHA-1 and the firmware version.
   - KNOWN route: IF2 `lift_libsre.sh#L21-L22`.
   - VERIFY: `file libsre.prx` shows ELF64 BE with e_type 0xFFA4 (P `FIRMWARE_LLE.md#L94-L98`).
1. **Lift libsre.** Use IF2's `tools/lift_libsre.sh` steps against P's tools: `prx_relocate.py` → `lift_prx.py` → `ppu_lifter.py --raw --base` → `prx_exports.py` → `extract_spu_images.py` + `build_spu_workloads.py` for the embedded SPU kernel/policy images.
   - Output goes to a git-ignored `generated/prx/`.
   - KNOWN: the script and tools exist.
   - VERIFY: run each P tool's `--help`, because IF2 is pinned to an older ps3recomp (a679051). Check the `lift_prx.py` summary: export count, TOC.
2. **Gate tests before running the game.** This is the "prove the contract first" step, and it is new.
   - a. **Differential LFQueue test.** Build a small host test that loads the lifted libsre image (`prx_load_module`) and calls the real `_cellSpursLFQueueInitialize`/`PushBody` on a 128-byte guest line.
     - Add a scripted consumer that follows the h4/h5 → h1 contract (§1 of `lfqueue-third-queue-researcher.md`, and WB's "SPU reserves h4 against h5, completes h1").
     - Hook SendSignal to record `(eaSignal, token)`.
     - Assert after every operation: the line bytes, full/empty behaviour, AGAIN on full, the waiter ring advancing one head at a time, and tokens decoding to `(wid << 8) | task`.
     - KNOWN: the upstream `test_lfqueue` does not cover this. ASSUMED that this test can be built from `runtime/prx/tests/test_prx_loader.cpp` as a template (VERIFY by reading it).
     - The same test is also an **oracle for options A and C**: any hand-written version must produce identical lines.
   - b. **RPCS3 cross-check.** RPCS3 runs libsre LLE. With the Interpreter decoder, break on the game's PushBody stub and dump the three queue lines (0x14CBB600, 0x14D22680, 0x14D89700) at the first push to each. Use `tools/rpcs3_objsnap.py` (sketch, VERIFY).
     - Expect the local lifted-libsre run to show the same h-counters and pack values for the same push sequence.
3. **Integrate in the port runner.** Load the image and let NID dispatch prefer the exports. That needs no code change: KNOWN, `ppu_hle.cpp#L477-L490`.
   - Spawn the lifted SPURS SPU kernel after `cellSpursInitialize`. Upstream only has the flOw-specific hook (`#L762-L770`), so Strikeforce needs its own. ASSUMED that IF2 `src/stubs.cpp` shows how (VERIFY: read it; 22 libsre references).
   - Turn off the port's SPURS overrides (`strikeforce_lfqueue.inc`, waiter-ring wake, `SPU_INTERP_*` for tasks). They are bypassed anyway, but the runtime's HLE task tables must not fight the real kernel.
   - VERIFY: a log line per LLE call (milestones show `prx:` or no `hle:` for cellSpurs NIDs).
4. **Boot to the same point.** Watch for STAT/assert from libsre entry points that read state the HLE half-built (the YDKJ pattern). Fix the **underlying HLE state** they read, e.g. sysPrxForUser/lv2 syscalls, rather than force-HLE-ing them.
   - `YDKJ_FORCE_HLE`-style exceptions are allowed only as a temporary bisect tool, logged in a list that must end up empty.
5. **SPU kernel bring-up.** Fix the SPU lifter or opcode bugs the kernel exposes (P `FIRMWARE_LLE.md#L177-L185`). Keep `SPU_DUMP_MISS` + `SPU_MISS_FATAL` on, so every unlifted image is lifted rather than interpreted.
   - The cloth image with overlapping overlays is still a separate problem (lifter overlay support). LLE does not fix it. KNOWN.
6. **Success criteria:**
   - All three MOC queues are pushed and popped. In the dumps, h1 = h5 after the work is drained.
   - The main thread leaves func_0011A230.
   - First in-stage frame.
   - No numbers or percentages until this is seen.
7. **Fallback C if Step 5 stalls:** the DoD3 `gen_libsre.py` pattern with Strikeforce's root list: LFQueue Get/CompletePush(2), Pop variants if the game's PPU pops, and `cellSpursQueue*` if imported (VERIFY in `imports.json`).
   - Also fix the HLE side that C still depends on: a real Attach lv2 queue, LS 0x1DC = wid, and token → (wid, task) routing.
   - Gate it with the Step 2a differential test.

## 6. What could not be confirmed

- Whether Strikeforce imports `cellSpursQueue*` (not only LFQueue). Check the port's `imports.json`.
- Whether Saud's firmware libsre matches the builds DoD3/IF2 used. Their addresses are build-specific.
- How much SPU lifter work the libsre kernel will need on this runtime. The only published end-to-end runs are Yakuza: Dead Souls (P doc) and IF2.
