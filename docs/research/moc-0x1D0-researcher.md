# MOC job counter: who should write work-area +0x1D0? (2026-11-26, ~09:50 UTC+3)

Research only; nothing was run, and Saud's PC was not touched.

Pins:
- **P** = ps3recomp `e85647a33ce5f9391788f0e3f52ab395a7fe6a89` (https://github.com/sp00nznet/ps3recomp/blob/e85647a33ce5f9391788f0e3f52ab395a7fe6a89/)
- **R** = RPCS3 `0ca5eb0efe50ec4e8aa07892ab86d57842246eb4` (https://github.com/RPCS3/rpcs3/blob/0ca5eb0efe50ec4e8aa07892ab86d57842246eb4/)

Local files:
- **MOC-C** = `/workspace/sf-spu/moc_recomp.c` (sha1 ea5b6c49…)
- **MOC-ELF** = `/workspace/sf-spu/moc_454077064.elf` (sha1 eddf93bb…, entry 0x3050, text vaddr 0x3000 at file offset 0x100)
- Disassembly is from P `tools/spu_disasm.py`.

## TL;DR

- **+0x1D0 is not a SPURS structure field and not the kernel LS area.**
- The task writes it itself, at startup, from **word 1 of its own `CellSpursTaskArgument`** (the 16-byte `argument` the PPU passes to `cellSpursCreateTask`).
- **The decrement path is skipped because the task starts with r3.word1 == 0.**
- So the two candidates are:
  - (a) the game passes a non-zero word1 and ps3recomp's async dispatch hands the task a different r3;
  - (b) the game really passes 0, and the decrement must come from somewhere else.
- One log line at task entry plus the existing `CreateTask arg=` print tells (a) from (b).
- A lifter bug in this chain is unlikely: the lifted C matches the disassembly instruction for instruction at the sites checked (§1).

## 1. What +0x1D0 is (KNOWN from MOC-C + MOC-ELF)

**The data-flow chain:**

1. **Entry `0x3050`.** It keeps r3 (the task argument) in r80 and calls `0x11D98`, which calls the main function `0x30A8` with r3 unchanged (MOC-C L28-44, L16735-16738).
2. **`0x30A8`** (MOC-C L53-75):
   - `r82 = r1+48` is the work area, **a local on the SPU stack**, not a fixed LS address.
   - `rotqbyi r6,r80,4` gives arg.word1, and `rotqbyi r7,r80,8` gives arg.word2.
   - Then `brsl 0xBC60(r3=work, r4=0x14900, r5=0x29200, r6=w1, r7=w2)`.
   - Disassembly confirms: `3F812806 rotqbyi $r6,$r80,4`, `3F822807 rotqbyi $r7,$r80,8`, `1C0C00D2 ai $r82,$r1,48`.
3. **`0xBC60`** (constructor, MOC-C L9711-9806): `r5 = r7` (L9748), `r4 = r6` (L9754), `r3 = work+464 (0x1D0)` (L9758), then `brsl 0x11160` (L9805). It writes r6/r7 nowhere between entry and this call (checked).
4. **`0x11160`** (MOC-C L15819-15860):
   - `stqd r5 → +0x1E0` and `stqd r4 → +0x1D0`, so **word0 of +0x1D0 = arg.word1** and +0x1E0 holds arg.word2.
   - If r4 != 0, it DMA-GETs 32 bytes from EA arg.word1 (tag 10) and merges one word of that block into +0x1D4.
   - Disassembly: `24004405 stqd $r5,0x10($r8)`, `24000402 stqd $r2,0x0($r8)`, `20000E04 brz $r4,…`.
5. **The per-job paths** (`0x10DF0`, MOC-C L15600-15626 and L15692-15700):
   - `lqd r80,0x1D0(r83)`, then `brnz r80 → 0x10F80` (the "start" path).
   - At job end (`0x10F20`): `lqd r2,0(r86=work+0x1D0)`; if word0 != 0, `rotqmbyi r4,r2,-4` and `brsl 0x11C18`.
6. **`0x11C18`** (L16624-16690) is a GETLLAR/PUTLLC loop that decrements the u32 **at EA = word0 of +0x1D0 = arg.word1**. The EAH comes from the zero-extended upper word.
   - Disasm `3FBF0104 rotqmbyi $r4,$r2,-4` matches. `rotqmbyi … -4` zero-extends word0 to a 64-bit EA; this is not a bug.

**Conclusions:**
- The guarded −1 (and the matching +1 path) target **the u32 at the EA in CellSpursTaskArgument word1**, which points at a 32-byte object. Nothing else in the image computes work+0x1D0 (grep of MOC-C for `+464`/`0x1D0`: only L9758 and L15613/15625). ASSUMED that nothing rewrites it through another pointer later. VERIFY with the watch in §3.
- **It is not the SPURS kernel context.** Absolute LS 0x1D0 is `SpursKernelContext.wklCurrentAddr` (R `rpcs3/Emu/Cell/Modules/cellSpurs.h#L1207`). LS 0x1DC is `wklCurrentId` (`#L1210`). This work area sits at r1+48 on the task stack, so the number 0x1D0 is a coincidence.
- **It is not a task-info field either.** In real SPURS, `CellSpursTaskArgument` is opaque user data `u32[4]` (R `cellSpurs.h#L949-L953`), stored at `TaskInfo+0x00` (`#L1040-L1048`). The taskset policy passes it **by value in r3**: `spu.gpr[3] = v128::from64r(taskArgs._u64[0], taskArgs._u64[1])` (R `rpcs3/Emu/Cell/Modules/cellSpursSpu.cpp#L1395-L1403`), so r3.word1 = arg._u32[1].
- **Therefore the only writer is the game's PPU**, through `cellSpursCreateTask(…, argument)`.

## 2. What ps3recomp does with the argument (KNOWN, P)

- `cellSpursCreateTask` reads the 16-byte argument from `argument_ea` (r9) and stores it into the guest TaskInfo through `spurs_taskset_add_task` (P `libs/spurs/cellSpurs.c#L1217-L1306`; `libs/spurs/spurs_taskset.c#L75-L80`).
- It prints `[cellSpurs] CreateTask(id=…, arg=w0 w1 w2 w3 …)`.
- With `SPURS_TASKSET_TRACE=1` it also dumps 64 B at each arg word that looks like an EA (`[argdump]`, `#L1308-L1320`).
- It then dispatches the task ELF **async** with `args_ea = context` (not the argument!) (`#L1368-L1378`).
- **How r3 is built at entry** (`runtime/spu/spu_lifted_job.h#L204-L250`, function starts at L157), in priority order:
  1. **`r3_override`** is used when the 16 bytes at **context_ea+0x10** start with a `0x0040xxxx` marker (captured at dispatch, `runtime/spu/spu_workload.c#L1657-L1670`). That is a CRI/YDKJ heuristic, and it also replaces word1 with `args_ea` if it is 0.
  2. **`taskset_ctx`** (the generic path, `#L240-L247`): r3 = the TaskInfo args the HLE copied to LS 0x2780 when it built the context (`spu_workload.c#L843-L863`, default on unless `LBP_NO_TASKSET`). This matches RPCS3.
  3. **Fallback**: r3 = {0x00400000, args_ea, 0, 0}.
- So the r3 a MOC task gets depends on **what happens to sit at context+0x10** and on whether the context build ran. ASSUMED that Strikeforce takes path 2. VERIFY with the log in §3.
- If Salem's port uses a local native-task path (the Nov 1 Workbench files had `strikeforce_native_task.inc`, which wrote r3 from `task_args`), check that one instead.

## 3. Fastest checks: HLE argument vs. lifter (in order)

1. **Existing log.** Find the three `CreateTask(... arg=w0 w1 w2 w3 ...)` lines for tasks 7902-7904. **Is w1 non-zero?** Salem called 0x14C546C8 "arg 2" — say which word (0-based) that is.
   - If w1 = h+0x38 (or another non-zero EA), candidate (a) is likely.
   - Run once with `SPURS_TASKSET_TRACE=1`: `[argdump] arg[1]` shows the 32-byte object the task will GET.
2. **One log line at entry** (local, temporary). In `spu_run_lifted_job_abi`, just before the entry call (P `runtime/spu/spu_lifted_job.h`, after the r3 block ~L250), print `image_id`, which branch was taken (override/taskset_ctx/fallback), and `ctx.gpr[3]._u32[0..3]`.
   - **Decision:** CreateTask w1 != 0 but entry r3.w1 == 0 or different → HLE r3 delivery bug. The root fix is "generic taskset tasks always get TaskInfo.args, byte for byte, as RPCS3 L1401 does". Do not hand-set the counter.
3. **Confirm in RPCS3** (Interpreter decoder; PPU breakpoints only work there, R `rpcs3/Emu/Cell/PPUThread.cpp#L1251-L1256`).
   - Break on the game's `cellSpursCreateTask` import stub (NID 0xBEB600AC). Read 16 B at r9 for the three MOC tasks; identify each by comparing r5's ELF bytes with MOC-ELF. `tools/rpcs3_objsnap.py stubs` does this; it's a sketch.
   - If RPCS3's w1 == ps3recomp's w1 != 0, the argument is correct and the problem is delivery (step 2).
   - If RPCS3 also has w1 == 0, the −1 is not meant to come from this path. Then look for another writer of h+0x38 (step 4).
   - SPU watchpoints: the RPCS3 GDB stub exposes PPU threads only (R `rpcs3/Emu/GDB.cpp#L581-L582`), so an LS watch through GDB is not possible. ASSUMED the Qt debugger's SPU breakpoints could stop at `0x11160` in RPCS3 (VERIFY). From there, read r4 = arg.w1.
   - **PPU-side alternative:** watch the guest word h+0x38 with RPCS3's memory viewer / periodic dumps and see when it goes 3 → 0 and how fast. Then breakpoint the PPU code around `func_005447CC`.
4. **Lifter A/B, only if step 2 shows the correct r3.w1 != 0 and the −1 still doesn't happen.**
   - Upstream has **no switch to interpret a lifted SPURS task**. An async MISS drops the program (P `runtime/spu/spu_workload.c#L1612-L1642`). `SPU_INTERP_UNLIFTED` only runs code at targets with no lifted function (P `runtime/spu/spu_channels.c#L2955-L2966`). `RD_SPU_INTERP` covers raw SPU thread groups, not SPURS tasks (P `runtime/syscalls/lv2_register.c#L864`).
   - So the A/B needs a local patch: skip this fp in the registry loop (`spu_workload.c` ~L1614, e.g. `SPU_SKIP_FP=0x…`) and let Salem's local SPU_INTERP_MISS path run it.
   - Compare `work+0x1D0` after `0x11160` and the decrement count (SPU_ATOM_EA on h+0x38).
   - Before that, a cheaper static check: the chain in §1 already matches the disassembly.

## 4. Which API pattern is this?

- **ASSUMED: it is the game's own job system, not a SPURS job API.**
  - KNOWN: the EBOOT imports from cellSpurs only `_cellSpursAttributeInitialize`, `InitializeWithAttribute`, `Finalize`, `Attach/DetachLv2EventQueue`, `CreateTaskset`, `CreateTask`, `ShutdownTaskset`, `JoinTaskset`, the EventFlag family, `_cellSpursSendSignal`, and `_cellSpursLFQueueInitialize`/`PushBody`.
  - From cellSync it imports Mutex Init/Lock/Unlock and LFQueueSize.
  - These NIDs were matched by hashing names from R `cellSpurs.cpp`/`cellSync.cpp`, against `/workspace/sf-shared/progress-src/out/EBOOT.imports.json`.
  - **No JobChain, JobQueue or JobGuard.**
- The shape is the usual "outstanding-work counter": the command handler adds the job count (+3), and each job does −1 at its end on a counter whose EA is passed in the task argument; the PPU waits for 0.
- `CellSpursJobGuard` (R `cellSpurs.h#L572-L584`) is 128-byte aligned with `ncount0` at +0. This object is fetched as 32 bytes, so it is ASSUMED not to be a JobGuard.

## 5. Black frame at 8 fps with SF_MOC_UNSTICK

- **8 fps is probably the unstick timer itself.** `SF_MOC_UNSTICK=60` waits 60 ms per stuck counter, and a 125 ms frame is about 2×60 ms. ASSUMED. VERIFY: change it to 20 and see if fps rises.
- **Black is probably downstream** (ASSUMED). The PPU waits on that counter because the jobs' output is consumed next: for example transformed or skinned geometry, matrices, visibility lists, or per-frame constants that the draws read.
  - Forcing 0 lets the PPU draw before (or without) that output, so the 874 draws can read zero or old buffers, which would give zero-area triangles or black or zero constants.
  - Precedent: Demon's Souls' "black 3D world = exposure 0": geometry was drawn but a constant was 0 (DeS `docs/NOTES.md`, fixes 20-21, timboat/demons-souls-recomp 9637b204).
- **Quick checks:**
  1. Fix r3 delivery first, then retest without UNSTICK. If the counter drains naturally, black may go away.
  2. Count job executions per frame (start/end hits at `0x10DF0`/`0x10F20`) against pushes. If jobs run but their −1 is skipped, the work is done. If jobs don't run, the work is missing.
  3. RSX side: set a debug clear colour (e.g. magenta). If the frame stays black rather than magenta, the draws write black over it. Also check that the flipped buffer is the one drawn to.
  4. Dump one draw's vertex buffer, or a constant used by most draws: all zero points to missing SPU output; non-zero points to an RSX/shader problem.

## 6. Open

- Which word index 0x14C546C8 is in Salem's `CreateTask arg=` line.
- Which r3 branch Strikeforce tasks take in his build. His port may carry local SPURS dispatch changes.
