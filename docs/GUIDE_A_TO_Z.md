# A-to-Z guide: convert your own PS3 game to a native PC build

This guide describes the method we used, and the tools in this repository, so you can convert **a PS3 game you legally own** to a native Windows PC build with [ps3recomp](https://github.com/sp00nznet/ps3recomp) (static recompilation). RPCS3 is used only as a behaviour reference, not as the runtime.

The examples come from real work on one title (Dynasty Warriors: Strikeforce, BLUS30471, 2026-11). The steps themselves are generic. Where a fact was measured on that title, it is labelled as a worked example, not as a promise that every game will do the same thing.

Labels used in our notes: **KNOWN** = read in a cited source or confirmed by a run. **ASSUMED** = reasoned, not verified. **VERIFY** = a concrete test that would confirm or kill a claim. Do not invent a success rate or an "X% done" figure.

---

## 0. Legal first (read this before anything else)

- You must already own the game. This repository contains **no game files**, no EBOOT, no ISO, no firmware, no keys, and no recompiled/lifted game code.
- Dump and decrypt **your own** copy, on **your** machine. Keep disc images, `EBOOT.elf`, `dev_flash`, and lifted output local and out of git.
- A practical, legal-leaning path many ports use is: install [RPCS3](https://rpcs3.net), install **official** PS3 system software obtained from Sony's own firmware page into that RPCS3, then use RPCS3's built-in **"Decrypt PS3 Binaries"** on *your* installed copy. This project ships no keys and no decryption steps.
- Laws on dumping a disc you own differ by country. Check yours.
- Do not copy code from RPCS3 or other GPL trees into your port. Read RPCS3 for layouts and behaviour (file:line), then write a clean-room handler, or lift firmware modules from *your* `dev_flash` and keep that output private.
- Our patches in this repo are our own changes, published as diffs against ps3recomp. Upstream ps3recomp has its own license; follow it when you clone and build that project.
- This repository itself has **no license file** (all rights reserved) unless the owner later adds one.

---

## 1. Prerequisites

**Hardware:** a 64-bit Windows 10/11 PC with a Direct3D 12 GPU. Plan on roughly 10 GB for a disc copy plus about 5 GB for a build (our working build used this order of magnitude).

**Toolchain (what the working Windows build used):**

| Tool | Role |
|---|---|
| Visual Studio 2022 Build Tools (MSVC) | Windows C/C++ toolchain; `vcvars64.bat` |
| clang-cl (LLVM) | compiler used by the ps3recomp port build |
| CMake 4.x | generates the Ninja build |
| Ninja | actually compiles the port |
| Python 3.12 | lifting scripts, NID tools, and the tools in this repo (most need no pip packages) |
| Git | clone ps3recomp and keep your own work tree |

Optional but strongly recommended: RPCS3, as a reference only (same scene, same input script).

Pin and record the ps3recomp commit you build against (we started from v0.20.0 / `d81c393`, then moved toward later master). Re-check upstream docs before treating any flag or commit as current.

---

## 2. Get your own legal dump and a decrypted EBOOT

1. Copy the filesystem of **your** disc or digital install so that you have a folder containing `PS3_GAME` (this becomes `/dev_bdvd` later).
2. Produce a decrypted `EBOOT.elf` of *that* copy. Point at RPCS3's official "Decrypt PS3 Binaries" flow, or another method you already use legally. **No keys are provided here.**
3. Install official firmware into your own RPCS3. You will later point the port at that RPCS3 `dev_flash` **read-only** (needed at runtime for firmware pieces such as `flashATRAC.pic` that cannot be lifted from the EBOOT).
4. Never commit or share the dump, the ELF, or `dev_flash`.

---

## 3. Set up ps3recomp and a work tree

1. Clone [ps3recomp](https://github.com/sp00nznet/ps3recomp) at a recorded commit. Copy its project template into a work folder.
2. Parameterise paths in a **local**, git-ignored env file (see `scripts/env.example.ps1` in this repo):

   - `PS3_VFS_ROOT` — the directory that makes `/dev_bdvd/X` map to `<root>/X`. This is usually the folder that **contains** `PS3_GAME`, not its parent. A wrong root can leave the game polling a missing index on a black screen (worked example: `LINKDATA.IDX` when the root was `vfs\` instead of `vfs\dev_bdvd`).
   - `PS3_HDD0_ROOT`, `PS3_HDD1_ROOT`, `PS3_GAMEDATA_ROOT` — writable.
   - `PS3_DEV_FLASH` — your RPCS3 `dev_flash`, read-only.
   - Path to **your** `EBOOT.elf`.

3. Apply only the patches you need from `patches/` (our changes, against a recorded ps3recomp commit). Apply with `git apply --check` first. One change per behaviour build.

This repo's `scripts/setup-work.ps1`, `copy_disc.ps1`, `lift.ps1`, `build.ps1`, `rebuild.ps1`, and `run.ps1` are a Windows starting point. They were cleaned up from a working machine; treat a first clean-folder run as something you verify.

---

## 4. Lift your EBOOT (do this on your machine)

Typical PPU pipeline (ps3recomp tools, names as of our campaign — confirm with `--help`):

1. `ppu_loader.py` — load your ELF and write import / function metadata **locally**.
2. `ppu_lifter.py --hle-stubs` — emit host C for the PPU code.
3. `gen_hle_nids.py --all` — regenerate the HLE NID table.
4. SPU: `extract_spu_images.py` then `build_spu_workloads.py`. If an image has overlapping `PT_LOAD` (including BSS), the lifter may refuse it. Use the upstream `--allow-partial` route and leave that image on the interpreter. Firmware images loaded from `dev_flash` at runtime also cannot be lifted from the EBOOT — keep `SPU_INTERP_UNLIFTED=1` and `PS3_DEV_FLASH` for those.

Lifted C, SPU output, and `EBOOT.*` JSON stay on your machine and out of git.

---

## 5. First boot

Build the template exe (our full build was on the order of 15–20 minutes with several jobs) and run it with the env vars above.

**What to watch for first:**

- Window appears, or it crashes immediately.
- Unresolved NIDs (`PS3_HLE_UNRESOLVED=fail` makes a fake `CELL_OK` obvious).
- NULL `bctr` / `PPU_VCALL_BT=1` / `PS3_EXIT_CHAIN=1`.
- Files not found (`PS3_FSLOG=1`).

**Boot crashes are often HLE struct layout bugs, not "the lifter failed."** If the C struct the HLE writes is not the SDK / RPCS3 *guest* layout, the game reads zeros or stale fields and then calls through a NULL object.

Worked example: `cellVideoOutGetDeviceInfo` missing `colorInfo` put `availableModes` at the wrong offset; PSGL saw no 720p mode and boot died on a NULL `bctr`. The fix is to write SDK-sized fields and unit-test the layout (`clang -Xclang -fdump-record-layouts`).

Other first-boot classes we actually hit and fixed (patterns, not a checklist you skip to):

- `sys_memory_get_user_memory_size` (syscall 352) reporting a fake fixed "available" size, so a later heap request got `ENOMEM`.
- On-screen keyboard / savedata hanging because Windows OSK stubs sent no sysutil events (LoadAsync must broadcast LOADED / FINISHED / UNLOADED).
- "Not enough space" dialogs until `PS3_GAMEDATA_ROOT` persisted.

Use `PPU_NOOP_BAD_VCALL` only as a diagnostic bandage, never as the fix.

---

## 6. HLE stubs and NID auto-link

A **NID** is the 32-bit id of a PS3 export. **KNOWN** (psdevwiki + ps3recomp `nid_database.py` + an RPCS3 `REG_FUNC` sanity check): NID = the first 4 bytes, read **little-endian**, of SHA-1(`name` ‖ the 16-byte suffix `6759659904250490566427499489741A`). Do not trust older docs that say a 4-byte suffix or a big-endian read.

Unresolved NIDs in ps3recomp default to faking `CELL_OK` and leaving out-params untouched (`PS3_HLE_UNRESOLVED`). That hides missing handlers as "success." A registered handler is also not necessarily a *complete* handler.

**Tool in this repo:** `tools/nid-autolink/nid_autolink.py`

- Reads the game's imported NIDs, computes names, and classifies each as linked, stub, partial, missing, or conditional.
- Can emit logging skeletons behind an explicit flag (they still return the current `CELL_OK` — they are probes, not fixes).
- Run `python nid_autolink.py --selftest` first.
- It is read-only toward your source tree; output goes to a fresh `--out` folder.

Also useful: `tools/nid/` (`nid.py`, `unbound_imports.py`) and the 48-stub census scripts under `tools/stubs48/`.

---

## 7. Movies / cutscenes

If the Nth movie hangs or a loading screen never ends after several clips, look at **cellSail** slot lifetime. Worked example: `cellSailPlayerFinalize` was unresolved, so player slots were never freed; re-initialising the same player still consumed a new slot, and the 5th movie found the table full.

See `patches/sf_local_patches_vs_d81c393.diff` (cellSail reuse + Finalize) and `port/strikeforce_movie.inc` plus `tools/movie/` helpers (`probe.py`, `pes.py`, build scripts). PAMF error-code ranges must not collide with ATRAC codes (we found a header mismatch in one tree; verify yours against psdevwiki: PAMF is `0x806105xx`).

Do not skip cutscenes as a "fix."

---

## 8. Controller (pad)

ps3recomp can feed a scripted or file-backed pad. This repo's pad tools:

- `autotester/lib/pad_driver.ps1` and `tools/replay/` — replay a recorded button sequence (`.padseq`).
- `tools/replay/sequences/` — example sequences such as boot-to-start (title-specific; write your own).
- Launchers may set `PAD_FILE` / `PAD_SCRIPT` / `SF_PADMAP`. Keep those paths local.

Get a repeatable path to the same screen before you debug anything that only happens "sometimes."

---

## 9. Audio (ATRAC) — character voice first

Streaming voice and music usually go through **cellAtrac** / ATRAC3plus, plus libmixer and `cellAudio`.

Patterns we confirmed:

- Unresolved streaming NIDs (`GetStreamDataInfo`, `AddStreamData`, second-buffer helpers) that fake `CELL_OK` and leave buffers unset.
- Remain-frame must not always be `-1`.
- Some titles use 6-channel BGM; an HLE that rejects `channels > 2` will break that path. Channel-unit errors we saw were on the 6ch BGM handle, not automatically on every voice hang.
- `cellAudio` / mixer: `SetNotifyEventQueue(0)` must remap to the documented magic key (`0x8000CAFE02460300`). Key 0 is not "no queue." Without the remap you can get silence (`AUDIO_PEAK=0`).
- Mixer SPU work can overrun its ring if a per-pass page index has no bound — that can zero a nearby table and later halt a different SPU task. Diagnose with a ring watch and a hang watchdog; do not "unstick" the halt and call it fixed.

**Tool:** `tools/atrac-validator/atrac_validator.py` (stdlib only). It reads logs and bytes, writes derived numbers (hashes, offsets, counts), and does not modify the game. Subcommands: `selftest`, `header`, `hashfile`, `hostcmp`, `analyze`. Keep raw tracks on your PC.

Our working rule: **character voice is the first audio milestone**, then music and effects.

Patches and clean-room includes: `patches/audio-fixes/`, `port/` audio `.inc` files.

---

## 10. RSX / graphics debugging

Healthy FPS with hundreds of draws and a black (or clear-colour) window is a present / target / depth / upload problem more often than "nothing was lifted."

Diagnose in this order (legacy D3D12 backend, which is the usual Windows template default):

1. `D3D12_DROP_STATS_EVERY=60 VP_SUBMIT=3` — present-gate, `upload_empty`, dropped draws.
2. Look at the **GPU** offscreen colour target, not guest RAM.
3. Then one knob at a time: `DEPTH_OFF=1`, `CULL_OFF=1`, `VTX_DUMP=1`. Leave `VP_NOFIXPROJ=1` while diagnosing (an automatic projection fix can hide missing matrices).

Verified patterns from our campaign (worked examples):

- A depth-only clear must not start or Present a new frame.
- When the vertex/index upload heap is full, flush the recorded batch **mid-frame without presenting**, and keep recording the same frame.
- Offset 0 can be a real depth surface. Do not treat `offset == 0` as "no depth."
- Vertex-program address-register (ARL) bugs can distort characters (bones read from the wrong register).

**Tools:**

- `tools/rsx_census/` — hook + report of RSX methods actually issued (apply with `apply_census.py`; hook source is ours).
- `tools/gfx_bisect/` — compare a port shot to an RPCS3 shot of the **same camera**, with an alignment score. Unaligned pairs cannot confirm a cause. (A Noto Arabic font is used for annotations; download it yourself — it is not shipped here.)
- `patches/branch-bits/` — our VP branch-bit diffs + `apply_branch_bits.py`.

---

## 11. SPURS hangs and stage transitions

"Now Loading" forever, or a later stage that never starts, often means a SPURS task waiting on a signal that will never come.

Check, in order:

1. Uncap logs. A short log cap can lie ("this queue was never pushed").
2. Event-flag and taskset state (`SPURS_EF_STATS=1`, `PS3_WAITBT=1`). An event flag created with no taskset (`isIwl=0`, `addr=0`) makes `SendSignal` fail silently.
3. Workload id (`wid`) delivery and waiter tokens. Token 0 can be a valid (wid 0, task 0) token, not "empty."
4. Overlay tables (`cellOvis`) — a fake init with size 0 loads empty SPU overlays.
5. Shutdown / join of an old stage's tasksets **before** you reuse the same addresses for a new stage. We confirmed a black hang where old-stage SPURS tasks never returned, and a taskset was re-created at the same address while the old run was still open.

Force flags (`SPURS_EF_FORCE`, `SF_*_UNSTICK`) are diagnostics. They can move the game forward with unfinished work still missing (we have seen "stage runs, frame still wrong"). The fix is the missing writer or the missing HLE state.

**Tools:** `tools/voicefreeze/lifecycle/sf_lifecycle.py`, `tools/voicefreeze/watchdog/` (`sf_hang_watchdog.ps1`, `watchdog_logic.py`), `patches/spursfix-1791/` (diffs + apply scripts only — not a copy of upstream C files).

---

## 12. The test loop (reusable tools)

Once the game boots, stop clicking at random. Use a loop:

1. **Watchdog** — detect a hang (no flip, blocked event flag, SPU halt) and write a report folder.
2. **Lifecycle** — log stage/taskset create and teardown so a transition leak is visible.
3. **Census** — what RSX methods ran in that session.
4. **Teleport** — `autotester/lib/tp_tool.ps1` (and the smaller `tp_find.ps1` helpers) to jump to a known world position *after* you have saved one yourself. This is a diagnostic, not a substitute for playing the real route.
5. **Replay** — `tools/replay/` to replay a pad sequence to the same milestone.
6. **NPC / mission bot** — `autotester/lib/npc_bot.py` + `npc_bot.ps1` can walk a mission script with a local model. Define goals carefully. A cache-file open is not automatically "you reached the gate."
7. **Auto convert loop** — `tools/auto_convert_loop.py` can help with miss → lift → rebuild **reporting**. It cannot invent a correct new HLE body. Read every TODO before a real run; the original skeleton was untested against a title.

`autotester/` is the kit (tester, pad driver, movie guard, screenshot helper, coverage). `tools/testloop/` is a one-click Windows loop with an Arabic menu. `tools/progress/` gathers counts, not a single percentage.

---

## 13. RPCS3 as reference only

- Use RPCS3 to see what the same scene, same pad script, and same SPURS objects look like when they work.
- Turn **GDB server** on and use the **Interpreter** PPU decoder when you need breakpoints (LLVM decoder may accept a breakpoint and never fire).
- Compare *the same objects* (tasksets, event flags, a single draw), not all of memory. Addresses will differ.
- A graphics claim needs a same-spot, same-resolution RPCS3 shot and an alignment score from `gfx_bisect`.
- **Never** paste RPCS3 source into the port.

---

## 14. How to measure progress

Give **counts with sources**, plus a yes/no milestone table. Do not invent one percentage.

Useful counts (recompute from the current build and a current log): imported NIDs; NIDs in the generated table; NIDs filled only by your port `.inc`; unresolved NIDs actually *called*; SPU images extracted / lifted / unliftable / dispatch HIT vs MISS; PPU functions emitted; null-call hits (want zero at a healthy milestone).

Milestones (yes/no, with a log line or a screenshot you keep locally): boot, savedata, title / PRESS START, menus, movies, loading finished, in-stage running, scene visible, character voice, music, input working, stage transition.

When a milestone moves, append a dated row; do not rewrite history.

---

## 15. Standing rules we actually used

1. Disc data, firmware, and lifted code stay on the owner's machine.
2. Fakes are guilty first (`CELL_OK` with empty out-params).
3. Guest layout is the ABI.
4. Log caps lie.
5. An unstick is a diagnosis, never the fix.
6. Zero is often a valid offset, key, or token.
7. Do not Present a half-built frame.
8. One behaviour change per build; keep a known-good snapshot.
9. Character voice before other audio work.
10. Root fixes only — no skipping content, no shipping clamps.

The longer checklist, with evidence and diagnostic flags, is `docs/ps3_recomp_playbook.md`. The early title-screen method writeup is `docs/METHOD.md`.
