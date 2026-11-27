# Strikeforce: automatic "convert while playing" loop (2026-11-26, ~12:15 UTC+3)

Research and a skeleton only. Nothing was run on Saud's PC.

- The skeleton `sf-shared/tools/auto_convert_loop.py` has **never been run against the game**.
- On the box I tested only two pieces, with a fake log and a 16-byte raw SPU blob:
  - log parsing;
  - the raw-SPU-job lift step, which ran upstream `find_spu_functions.py` and `spu_lifter.py` and produced a registration file.
- The ELF-dump branch (`build_spu_workloads.py --images`), the build step, the watchdog and the frame diff are **untested**.

Pins:
- **P** = ps3recomp `e85647a33ce5f9391788f0e3f52ab395a7fe6a89`. Links are written as `P/<path>#L..`, where `P/` = https://github.com/sp00nznet/ps3recomp/blob/e85647a33ce5f9391788f0e3f52ab395a7fe6a89/

## 0. Bottom line

- **KNOWN:** P already has every *capture* hook the loop needs except a PPU dynamic-code dump. The pieces are:
  - SPU miss dumps;
  - an unresolved-NID list with call counts (bucketed);
  - PPU indirect-call, null-call and stuck reports;
  - D3D12 drop stats;
  - BMP frame dumps;
  - PAD_SCRIPT / PAD_FILE input;
  - an RPCS3 capture parser.
- **What the loop can fix on its own:** only **missing SPU programs** (dump, lift, register, rebuild). Everything else it can only **find and count** for a person or agent.
- **ASSUMED:** the real blockers so far (event-flag `isIwl`/`addr`, the LFQueue contract, the 0x1D0 slot, the D3D12 present gate) are all of the second kind. The loop speeds up *finding* them; it doesn't remove the need to reason them out.

## 1. Switches verified in P (each one exists; this is where it's read)

| Need | Env var / tool | Where (P) | Notes |
|---|---|---|---|
| SPU job/PM image the runtime has no lift for | `SPU_DUMP_MISS=<dir>` → `spujob_<fp16>_<size>.bin` | `libs/spurs/cellSpurs.c#L2062` (PM), `runtime/spu/spu_workload.c#L1085` (sync job), `#L1623` (async) | Bytes are exactly what was fingerprinted. Deduped, max 64 per path per process. The drop itself is always logged once: `[spu_workload] ERROR … (fp=… size=… owner=…)` (`#L364-L385`). |
| Stop on the first SPU miss | `SPU_MISS_FATAL=1` | `spu_workload.c#L375` | Useful for "one miss per run" mode. |
| Unlifted address *inside* a lifted SPU image | log only: `[spu] img=N branched into unlifted LS 0x…` | `runtime/spu/spu_channels.c#L2931` | Fix is `build_spu_workloads.py --extra-funcs IMAGE=ADDR` (`tools/build_spu_workloads.py#L114-L122`). `SPU_INTERP_UNLIFTED=1` (`#L2966`) runs it in the interpreter instead; `SPU_INTERP_STATS=<s>` (`runtime/spu/spu_interp.c#L401`) ranks interpreted hot spots. |
| Unresolved NIDs that are called | `PS3_MILESTONE_OUT=<file>`: key `hle:unresolved:0x…` with a **bucketed** count (`1`, `2-9`, `10-99`…) | key `runtime/ppu/ppu_hle.cpp#L804`; file `runtime/milestone.c#L104`, counts `#L248-L252` | The always-on stderr line `[hle] UNRESOLVED NID 0x…` is printed once per NID (`ppu_hle.cpp#L233`). Exact counts exist internally (`#L225-L230`) but are **not printed**. |
| First N HLE calls with args | `PS3_HLE_TRACE=<N>` | `ppu_hle.cpp#L416` | Heavy log and changes timing. Not used by default in the loop. |
| A/B whether an unresolved NID matters | `PS3_HLE_UNRESOLVED=fail` | `ppu_hle.cpp#L218` | The default `ok` **fakes CELL_OK**, so a missing function can fail silently (see §4). |
| Top resolved HLE calls | `PS3_HLE_TOP=<sec>` | `ppu_hle.cpp#L873` | |
| PPU indirect call to an unlifted target | log `[ppu] unresolved indirect call -> 0x…` | `runtime/ppu/ppu_loader.cpp#L3176` | Loop writes these as seeds for `find_functions.py --seed-json` (`tools/find_functions.py#L849`; filter in `load_external_seeds` keeps 4-aligned in-exec addresses). |
| PPU stuck on one target | `PPU_STUCKMAX=<n>` (default 2000) → `exit(3)` | `ppu_loader.cpp#L3148-L3175` | Crash with a reason the watchdog can record. |
| PPU null call | on by default; `PS3_NULL_CALL=0` turns it off | `ppu_loader.cpp#L2932-L2960` | |
| Recent indirect targets per thread | `BCTRL_RING=<file>` | `ppu_loader.cpp#L2676` | |
| RSX dropped draws, deferred flips, fallback PS | `D3D12_DROP_STATS_EVERY=<n>` | `libs/video/rsx_d3d12_backend.c#L4574-L4590` | stdout. Also `[FP] PSO FAIL` (`#L2762`). |
| Frame dumps | `CELLMARK_DUMP=<n>`, `CELLMARK_DUMP_DIR`, `CELLMARK_DUMP_EVERY`, `CELLMARK_DUMP_MINDRAWS`, `CELLMARK_DUMP_SKIP` | `rsx_d3d12_backend.c#L7960-L7967`, `#L1495`, `#L5807-L5832` | BMP of the **backbuffer**. While the present gate from the geometry report is unfixed, these will show the clear (magenta). |
| Scripted input | `PAD_SCRIPT="<sec>:<mask>,…"` (max 256 events), `PAD_CLOCK=flips`, `PAD_AUTOPRESS`, `PAD_STICK` | `libs/input/cellPad.c#L999-L1055` | Masks: START 0x0008, CROSS 0x4000, etc. (comment `#L1008-L1015`). |
| Closed-loop input | `PAD_FILE=<path>` (write `0x4000 40` into it) | `cellPad.c#L1057-L1100` | Lets a driver react to what is on screen. |
| Regression gate / milestone diff | `tools/regress.py` | `tools/regress.py#L1-L36`, `#L272-L398` | Already runs a port with a timeout, `PS3_MILESTONE_OUT`, and `--shots` frame dumps. |
| RPCS3 frame ground truth | `tools/parse_rrc.py <capture.rrc.gz>` | `tools/parse_rrc.py#L1-L19` | Draw-list manifest from an RPCS3 RSX capture (Alt+C). |
| NID → name | `tools/nid_database.py --lookup 0x…` | `tools/nid_database.py#L16`, `#L639` | |
| NID table regen | `tools/gen_hle_nids.py --all --out …` | `tools/gen_hle_nids.py` | Only registers handlers **that already exist** in `libs/`. It does not write new ones. `generate_stubs.py` writes log-and-return-0 stubs, which is the same risk as the default fake. |

**Asked for but NOT in P (KNOWN, `git grep` at P):**
- **PPU JIT or dynamic-code dump:** none. There is no PPU interpreter fallback; the only "interpreter" mention is `runtime/ppu/ppu_vmx.h#L7`, a comment. Unlifted PPU code shows up only as `unresolved indirect call` / `stuck` lines, and the fix is an offline re-lift.
- **Headless mode on Windows:** none. The backend is chosen at compile time: D3D12 on Windows; null/headless only on non-Windows/non-Apple builds without Vulkan (`templates/project/main.cpp#L123-L159`). `PS3_HEADLESS` exists only in a GT5 port's own code (§5).
- **Runtime hang watchdog:** none in the port template. `WATCHDOG_AT` exists only in the test harness `runtime/ppu/tests/boot_main.cpp#L1016-L1034`. So the loop's watchdog is external: no log or milestone growth for `--stall` seconds means a hang.

## 2. The loop (what `auto_convert_loop.py` does)

1. **Run** the exe with these set:
   - `SPU_DUMP_MISS`, `PS3_MILESTONE_OUT`, `D3D12_DROP_STATS_EVERY=60`;
   - `CELLMARK_DUMP*` (frames);
   - `BCTRL_RING`, `PS3_VERBOSE=0`;
   - `PAD_SCRIPT` or `PAD_FILE`.

   stdout and stderr both go to `run.log`.
2. **Watchdog** (external): `timeout`, `crash` (exit code ≠ 0) or `hang` (no output growth for `--stall` s). It records:
   - the last milestone key, i.e. how far the run got;
   - the last 25 log lines.
3. **Parse** the misses: SPU fingerprints, unlifted SPU PCs, NIDs and their buckets, PPU indirect targets, stuck target, null calls, PSO fails, and the last `[D3D12 drops]` line.
4. **Lift new SPU dumps.** Each dump is checked first: size and FNV-1a must match its file name.
   - **ELF dumps:** copied to a folder, then `build_spu_workloads.py --images … --constructor`, which registers by the same FNV (`tools/build_spu_workloads.py#L16-L23`).
   - **Raw job blobs:** `find_spu_functions.py --raw --base 0`, then `spu_lifter.py --symbol-prefix …`, then a registration file built the way Tornado does it (§5).
5. **Report** (`runs/run_NNN/report.json`):
   - new keys and totals per category;
   - SPU lifted this run, lifted in total, still missing, failed;
   - NID names and buckets;
   - D3D12 counters;
   - frame checks.
6. **Rebuild** (your incremental command) only if something was lifted. Stop if the build fails.
7. **Stop** after `--stable N` runs in a row with nothing new, or after `--max-iter`.

**Progress number for Saud:** counts, not percentages.
- "SPU programs seen X, lifted Y, still missing Z";
- "unresolved NIDs called K (top by bucket)";
- "new this run M".

No percentage is given, because nobody knows the total that a full playthrough would reach.

**Frame check (ASSUMED method, thresholds need tuning):**
- **Flat-frame flag:** fewer than 16 unique colours in a 160×90 thumbnail. This is the same idea as `regress.py report_shots`, which notes a non-black test lies (`tools/regress.py#L186-L215`).
- **RPCS3 comparison:** for each RPCS3 reference PNG (Saud approved RPCS3 captures at 11:46), take the best-matching port frame and compute the mean absolute difference of 64×36 greyscale thumbnails. Above `--diff-threshold` (default 40) counts as a mismatch.
- **Why best-match and not frame-to-frame:** timing differs between the port and RPCS3. regress.py deliberately does no pixel diff for the same reason ("would only ever cry wolf").
- **Stronger, non-visual check (manual for now):** RPCS3 RSX capture (Alt+C) → `parse_rrc.py`, then compare draw counts and targets against `VP_SUBMIT` `[PRESENTGATE] targets`.

## 3. What Salem must still edit (TODOs in the script)

- Add `src/spu_dumped/` and `src/spu_dumped_jobs/` to the port's CMake sources.
- Choose `--first-image-id`. It must not collide with existing `spu_begin_image` ids.
- Raw job base address: 0 is ASSUMED.
  - Tornado used 0 (relift.sh L55-L59).
  - One GT5 blob needed `0xA00` (MauricioRSJ98 `lift_spu_captured.py` L23).
  - Override per fingerprint with `--raw-base '{"FP":"0xA00"}'`.
- An input script that reaches new content. A fixed `PAD_SCRIPT` wanders in menus; `PAD_FILE` plus a driver is better (GT5 `autodrive.ps1`).
- PPU seeds are only written to `ppu_seed_candidates.json`. Re-lift by hand: `find_functions.py --seed-json …`, then `ppu_lifter.py`. It is slow, and a target can be a garbage OPD or a leaked host pointer (`PS3_HLE_PTRCHECK`, `ppu_hle.cpp#L892-L900`).
- `[spu] img=N … unlifted LS` lines need N mapped to the image name used by `--extra-funcs`. This is not automated (VERIFY the registration names).

## 4. Limits: what cannot be automated (KNOWN from this project)

- **Semantic HLE bugs produce no "miss".** The event flag created without a taskset (`isIwl=0`, `addr=0`), the LFQueue push/pop contract, the 0x1D0 argument slot and the D3D12 `rt_off==0` present gate: every one of these ran "successfully" with wrong values. No log line says "wrong struct layout". A person or agent had to compare against the PS3 contract (RPCS3 as an oracle).
- **`PS3_HLE_UNRESOLVED=ok` (default) returns CELL_OK for missing functions**, so the game continues on a wrong path. `generate_stubs.py` stubs do the same. Auto-stubbing makes the miss list shorter, not the game more correct.
- **Coverage = where the input reaches.** A miss on a path the script never visits is never seen. "No new misses in N runs" means "nothing new on *this route*", not "done".
- **Only the first problem per path shows up.** After a hang, later content is never reached; the loop records where it hung and stops finding more.
- **Logging changes timing.** regress.py sets `PS3_VERBOSE=0` for this reason (`tools/regress.py#L335-L337`). Keep `PS3_HLE_TRACE` and the `SPU_*TRACE` switches out of the loop.
- **Frame diff:** fails if the image never reaches the backbuffer, which is the current case (`rt_off==0` gate). It also can't tell "wrong" from "different timing".
- **Lift quality:** `spu_lifter` reports `unsupported` instructions. The loop records the count but can't fix them.
- **Licensing:** lifted SPU code and dumps come from Saud's copy and must stay local. Don't commit them.

## 5. Published ports that use parts of this loop (pinned)

None of them publishes a fully closed "run → lift → rebuild → rerun until clean" loop. Each one automates one or two pieces (KNOWN for what I read; ASSUMED for the rest of their trees).

- **Tornado Outbreak** (sp00nznet `2cc6c0f`): `PAD_SCRIPT` + `SPU_DUMP_MISS` capture run, then a script lifts every `spujob_*.bin` and writes the registration TU.
  - https://github.com/sp00nznet/tornado/blob/2cc6c0fb660b62aab235e06ac8e0fa64106ec265/tools/relift.sh#L38-L74
- **Simpsons Arcade** (sp00nznet `5371f25`): `drive.ps1` presses keys and screenshots each step.
  - https://github.com/sp00nznet/simpsonsarcade-ps3/blob/5371f2575b9dc9d2a7d2c3c615e4072bb85a9800/tools/drive.ps1#L1-L40
- **Demon's Souls** (timboat `9637b20`):
  - fix 2 is the manual capture→lift→rebuild cycle (`SPU_DUMP_MISS`, `lift_spurs_jobs.py`);
  - fixes 3, 5 and 6 (GCM layout, LFQueuePushBody, JOBLIST opcode 6) are semantic fixes that no loop would have found.
  - https://github.com/timboat/demons-souls-recomp/blob/9637b204f031c72839129d49e5b0586d4bcfdeed/docs/NOTES.md#L64-L90
- **God of War Ascension** (bc160201983 `f4f19dc`):
  - bulk lift up front: `ascension/scripts/windows/prepare.ps1#L100-L136`;
  - carries ps3recomp's regression gate: `ps3kit/tools/regress.py`.
  - https://github.com/bc160201983/GoW-Ascension-Recomp/blob/f4f19dc05840222668e4469241ac9ecd9178c56f/ascension/scripts/windows/prepare.ps1
- **GT5, MormonFTP-hub** (`d1c160f`):
  - `autodrive.ps1` drives menus through `PAD_FILE`;
  - `build_run.ps1` retries crashed or damaged compiles.
  - https://github.com/MormonFTP-hub/gt5-recomp/blob/d1c160fd619106d338faf0c8b0f148466b5ae32d/GT5/scripts/autodrive.ps1
  - https://github.com/MormonFTP-hub/gt5-recomp/blob/d1c160fd619106d338faf0c8b0f148466b5ae32d/GT5/scripts/build_run.ps1
- **GT5, MauricioRSJ98** (`0559a61`): the closest to this design.
  - `run_native.py` is a bounded run with a timeout, `SPU_DUMP_MISS` and an archive per run. Its `PS3_HEADLESS` and `PS3RECOMP_VK_*` are that port's own switches.
  - `lift_spu_captured.py` lifts every dump, with a fingerprint check and a cache.
  - https://github.com/MauricioRSJ98/gt5-native-recomp/blob/0559a614d4df8d586237eb343f8c8ba167a4ea79/scripts/run_native.py
  - https://github.com/MauricioRSJ98/gt5-native-recomp/blob/0559a614d4df8d586237eb343f8c8ba167a4ea79/scripts/lift_spu_captured.py

## 6. Fastest first use

1. **Fix or work around the present gate first** (geometry report). Otherwise every frame check flags magenta.
2. **First pass, one miss per run:**
   ```
   py auto_convert_loop.py --ps3recomp <P> --exe build\strikeforce.exe --exe-args "<eboot>" --build "cmake --build build -j 8" --pad-script "<your title→stage presses>" --timeout 600 --stall 90 --extra-env SPU_MISS_FATAL=1 --stable 2
   ```
3. **Then drop `SPU_MISS_FATAL`** and add `--rpcs3-ref refs\` with RPCS3 F12 screenshots of the same checkpoints.
4. **Read `runs/run_NNN/report.json`.** Anything under `nids`, `null_call`, `ppu_stuck` or a `hang` is work for a person or agent, not for the loop.
