# New GitHub / web tools (2025–2026) for the Strikeforce port

2026-11-26, ~14:40 Asia/Kuwait (UTC+3). Research only; nothing was installed or run on Saud's PC.

This list is **additive** to `github-tools-researcher.md`. Tools already covered there are skipped: RenderDoc, NVIDIA FLIP, odiff, envytools, PSL1GHT, Demon's Souls `test_subchannels.c` / `GCM_SUBCH_LOG`, `rpcs3 --rsx-capture`, `parse_rrc.py`, Ascension-R `rsxcap_check.py`, MotorStorm `lift_ms_plugins.py` / `bmpdiff.py`, GT5 `lift_spu_jobs.py`, ps3kit (as a whole), pixelmatch, PIX, GhidraSPU.

Every URL below was opened this turn (HTTP 200, or the GitHub API plus the raw file). Licences come from each repo's LICENSE / GitHub licence field. "Last activity" is the last push, converted from the GitHub UTC timestamp to Asia/Kuwait (UTC+3).

Pins unchanged:
- **P** = ps3recomp e85647a33ce5f9391788f0e3f52ab395a7fe6a89
- **R** = RPCS3 0ca5eb0efe50ec4e8aa07892ab86d57842246eb4

## Immediate facts (not just tools)

**KNOWN — the six previously unnamed Strikeforce cellSail / cellPamf NIDs.** Names were first found in `zecoxao/sce_symbols` `nids.txt`, then **verified independently** by computing `NID = first 4 bytes of SHA-1(name + 16-byte suffix 67 59 65 99 04 25 04 90 56 64 27 49 94 89 74 1A), little-endian`, which is the algorithm already documented in P's `tools/nid_database.py` / `docs/PPU_RECOMP.md`. All six matched:

| NID        | Name                                      |
|------------|-------------------------------------------|
| 0x0D0C2F0C | `cellSailDescriptorSetEs`                 |
| 0x15FD6A2A | `cellSailDescriptorClose`                 |
| 0xC044FAB1 | `cellSailDescriptorOpen`                  |
| 0xD1D55A90 | `cellSailPlayerSetPaused`                 |
| 0xDDEBD2A5 | `cellSailAviMovieGetStreamByTypeAndIndex` |
| 0x28B4E2C1 | `cellPamfReaderSetStreamWithTypeAndIndex` |

The AVI-named call is still a NID in cellSail; it does **not** by itself prove Strikeforce's movies are AVI rather than PAMF. The game has a cellPamf import (`cellPamfReaderSetStreamWithTypeAndIndex`) and 34 cellSail imports, so PAMF remains the expected container (ASSUMED until `pamf_probe.py` or PAMFtool is run on a real `.pam`).

The same `nids.txt` (9,100 lines, 182 `cellSail*` names, 23 `cellPamf*` names) is the right lookup table for the 72 unresolved NIDs. Do **not** vendor that file into the port: the repo has no LICENSE file (see #1).

## Ranked by usefulness now

| # | Tool | Licence | Last activity (Asia/Kuwait) | Windows |
|---|------|---------|-----------------------------|---------|
| 1 | `zecoxao/sce_symbols` `nids.txt` + `ps3_names2nid.py` | **no LICENSE** (all rights reserved). Lookup only; do not copy the file into the port | 2026-11-12 14:14 | yes (text + a few dozen lines of Python) |
| 2 | ravenDS/PAMFtool (external exe only) | **GPL-3.0 — reference / external tool only, no code copy** | 2026-11-10 19:43 (created 2026-05-26) | yes (.NET 8) |
| 3 | WinDbg Time Travel Debugging (`ttd.exe`) | Microsoft, closed, free | current WinDbg docs (page live this turn) | Windows only |
| 4 | rust-minidump `minidump-stackwalk` 0.27.0 | MIT | 2026-11-03 17:22 | yes (`cargo install` or a release binary) |
| 5 | MSVC / clang-cl AddressSanitizer | Microsoft / LLVM, in the compiler | live MSVC docs this turn | yes (clang-cl is already the P CI compiler on Windows) |
| 6 | RoyalAce22/CellGov (oracle / checkpoints, not a game runner) | MIT OR Apache-2.0. The `bridges/rpcs3-patch/` tree is **GPL-2.0-only** and is not linked into CellGov | 2026-11-26 04:05 | yes |
| 7 | undecuple/project-helghast (Killzone 3) tooling: `tools/pad/`, `kz3_metrics.py`, `tools/perf/mission0.ps1` | MIT | 2026-11-25 20:53 | yes (PowerShell + Python) |
| 8 | gustavomorinaga/project-vekta (Killzone HD) `tools/trace_frames.py`, `tools/spu_capture.py` (sail.cpp was already covered in the cutscene note) | MIT | 2026-11-26 04:13 | yes |
| 9 | tekulvw/mag-recomp tools (`movie_picture_hooks.py` is title-pinned) | MIT | 2026-11-26 14:13 | yes |
| 10 | Redgrave961/Vajra (`port/lift_firmware.py`) | MIT | 2026-11-25 14:58 | yes |
| 11 | N64 save-state *design* in N64ModernRuntime / CBFD-Recompiled | **GPL-3.0** runtime (N64ModernRuntime). CBFD-Recompiled's GitHub licence is MIT, but the save-state code lives in the vendored runtime — **reference only, no code copy** | 2026-11-03 09:41 / 2026-11-19 05:26 | yes |

---

### 1. `zecoxao/sce_symbols` — NID name database (lookup only)

**Links (live):**
- https://github.com/zecoxao/sce_symbols
- https://github.com/zecoxao/sce_symbols/blob/main/nids.txt
- https://github.com/zecoxao/sce_symbols/blob/main/ps3_names2nid.py

**Verified:** GitHub API + README + directory listing + a local download of `nids.txt` (9,100 lines) this turn. Last push 2026-11-12T11:14:02Z = 14:14 Asia/Kuwait.

**Does:**
- `nids.txt` is `0xXXXXXXXX name` lines. That is the fastest way to name the 72 unresolved Strikeforce NIDs.
- `ps3_names2nid.py` hashes a name list with the same suffix P already uses. You can also just use P's `tools/nid_database.py`.
- Once a name is proposed, **verify it yourself** with the SHA-1 formula (as done above). A hit in `nids.txt` is a lead, not a licence to copy the file.

**Can't / caveats:**
- **No LICENSE file** in the repo root, and the GitHub licence field is empty. Treat the collection as all-rights-reserved. Look names up; do not vendor `nids.txt`, `ps3.xml` or `ps3_names.txt` into the port.
- The file also covers PS4/PS5/Vita/PSP symbols we do not need.
- Related: `Fancy2209/Cell-Headers` (https://github.com/Fancy2209/Cell-Headers, created 2025-08-20, last push 2026-04-29 14:31 Asia/Kuwait) also has a `nids.txt` of almost the same size and a `nidreader.py`. It also has **no LICENSE**. Prefer sce_symbols as the more recently pushed copy, still lookup-only.

---

### 2. ravenDS/PAMFtool — external PAMF probe / demux (GPL, do not copy)

**Link:** https://github.com/ravenDS/PAMFtool (live)

**Verified:** GitHub API (licence GPL-3.0, created 2026-05-26, last push 2026-11-10T16:43:36Z = 19:43 Asia/Kuwait) plus the README.

**Does:**
- A .NET 8 muxer/demuxer for `.PAMF`/`.PAM`, with `-info` and `-demux`.
- Streams it claims to handle: AVC (H.264), MPEG-2, ATRAC3 Plus, LPCM, and experimental AC-3. Windows, macOS and Linux.
- From v1.3 the README claims a demux-then-remux of a genuine PAMF is byte-identical to the original (author's claim; VERIFY on a Strikeforce file).
- This is the right **external** check for Step 0 of the cutscene plan: coding type and, after demux, the AVC `profile_idc` / `level_idc`, without copying any GPL into the port. It complements `sf-shared/tools/pamf_probe.py`.

**Can't:**
- **GPL-3.0.** No code, headers or format tables may be copied into ps3recomp or the Strikeforce tree. Running the published exe / `dotnet` build as a separate process is fine.
- It is a file tool, not a cellSail player.
- No MIT or BSD PAMF demuxer was found this turn (see "Checked and rejected").

---

### 3. WinDbg Time Travel Debugging — intermittent 0xC0000005

**Links (live):**
- https://learn.microsoft.com/en-us/windows-hardware/drivers/debuggercmds/time-travel-debugging-overview
- https://learn.microsoft.com/en-us/windows-hardware/drivers/debuggercmds/time-travel-debugging-ttd-exe-command-line-util
- Recorder download: https://aka.ms/ttd/download
- WinDbg install: `winget install Microsoft.WinDbg`

**Verified:** the Microsoft pages returned HTTP 200 this turn. This is a Microsoft tool, not a GitHub project.

**Does:**
- Records a user-mode process and lets you replay the exact run forwards and backwards to the faulting instruction.
- That is the right tool for an **intermittent** access violation after about five minutes, where a live debugger may miss the first bad write.
- `ttd.exe -out C:\dumps -attach <pid>` or launch the port under TTD, then open the `.run` in WinDbg.

**Can't:**
- Closed source, Windows only. Recording is heavy (disk and slowdown); use it on the crash repro, not on every graphics A/B run.
- It will not by itself tell you which guest NID or RSX method was active; pair it with the existing milestone / HLE logs.

---

### 4. rust-minidump `minidump-stackwalk` 0.27.0 (MIT)

**Link:** https://github.com/rust-minidump/rust-minidump (live)

**Verified:** GitHub API (MIT, last push 2026-11-03T14:22:53Z = 17:22 Asia/Kuwait). `minidump-stackwalk/Cargo.toml` in that tree depends on `minidump = { version = "0.27.0", ... }`.

**Does:**
- Turns a Windows `.dmp` into a human-readable or JSON stack, with optional symbol paths.
- Fits the auto-loop: if the port writes a minidump on 0xC0000005 (Windows Error Reporting `LocalDumps`, or an in-process unhandled-exception filter), the loop can stackwalk it without opening WinDbg.

**Can't:**
- It analyses a dump; it does not record one. Enable dump creation first.
- Symbols (PDB / a debug build) are needed for useful frames in lifted code.

---

### 5. AddressSanitizer on the Windows clang-cl build

**Link:** https://learn.microsoft.com/en-us/cpp/sanitizers/asan (live this turn)

**Does:**
- clang-cl (already used by P's Windows CI) can build the runtime + port with `-fsanitize=address`. Heap use-after-free and out-of-bounds often show up as 0xC0000005; ASan reports the first bad access and the allocation site.
- MSVC docs also mention `ASAN_SAVE_DUMPS` to keep a dump with sanitizer metadata.

**Can't:**
- ASan is slower and uses more memory. Use it on a crash-repro build, not the 90 FPS graphics loop.
- It will not catch a pure guest-logic bug that never touches invalid host memory.
- VERIFY that the lifted 23k-function binary still links and runs under ASan on Salem's machine before relying on it.

---

### 6. RoyalAce22/CellGov — deterministic Cell oracle (not a drop-in runtime)

**Link:** https://github.com/RoyalAce22/CellGov (live)

**Verified:** GitHub API + full README this turn. MIT OR Apache-2.0. Last push 2026-11-26T01:05:02Z = 04:05 Asia/Kuwait. The README states `bridges/rpcs3-patch/` is GPL-2.0-only and is **not** compiled or linked into any CellGov crate; RPCS3 is invoked only as a separate process.

**Does:**
- A Rust interpreter for PPU/SPU that records replayable traces and compares state hashes to RPCS3 observations. The README's own words: it is "the oracle layer for static recompilation", and "CellGov does not run games. There is no rasterisation, vblank, audio, networking, input, JIT…"
- `cellgov boot run --title <name>` boots to a **manifest checkpoint** (a named boot/compare point), not a mid-stage HLE snapshot of a ps3recomp process.
- `cellgov dev prx-imports` inspects PRX / SPRX / EBOOT imports (another NID/import view, under a real licence).
- Developed on Windows; Windows and Linux are supported.

**Can't:**
- It will not replace ps3recomp, will not render, and will not load our in-stage save.
- Retail boots need an operator-supplied key vault and the default-off `decrypt` feature. That is the operator's own keys; nothing in this research supplies or asks for one.
- Useful as a licensed design reference for "checkpoint + hash against RPCS3", and as a PRX-import inspector, not as tonight's savestate.

---

### 7. project-helghast (Killzone 3) — pad routes, crash-aware metrics, profile seeds

**Links (live):**
- https://github.com/undecuple/project-helghast
- https://github.com/undecuple/project-helghast/blob/main/tools/README.md

**Verified:** GitHub API (MIT, last push 2026-11-25T17:53:37Z = 20:53 Asia/Kuwait) plus the tools README.

**Does (the parts that transfer, as patterns, not drop-in scripts):**
- `tools/pad/` — scripted `.pad` files that drive menus and levels. We already have `PAD_SCRIPT`; their routing and "invalidate the run on a crash / timeout / late event" rules are worth reading.
- `tools/kz3_metrics.py --benchmark-v1` — treats `[HardExit]`, `[fatal]` and undrained-SPU markers as failures, and emits pass/fail JSON. A good model for the auto-loop's `report.json` once we start hunting the 5-minute crash.
- `tools/perf/mission0.ps1` — copies a profile, **clears the Continue record**, and gives each run a fresh seed so the measured window starts in-mission. That is the closest published pattern to Saud's approved "test-only in-stage save", using a *game save / profile* rather than a full HLE snapshot. It does not skip cutscenes in the shipped game; it starts a *benchmark session* from a prepared profile.

**Can't:**
- The scripts are wired to `kz3.exe`, Proton, and their launcher. Port the ideas, don't paste the paths.
- Clearing Continue / starting from a profile is only valid for tests, per Saud's rule.

---

### 8. project-vekta (Killzone HD) — frame and SPU capture scripts

**Link:** https://github.com/gustavomorinaga/project-vekta (MIT, last push 2026-11-26T01:13:23Z = 04:13 Asia/Kuwait)

**Already known (do not treat as new):** `port/kz1hd/sail.cpp`, the cellSail GetFrame protocol notes, F12 Vulkan pass capture (rejected earlier as Vulkan-only).

**New this pass, verified by a tools-directory listing:**
- `tools/trace_frames.py` — small frame-trace helper (MIT). Worth reading as a model for the planned offline RSX replay, not a FIFO replay itself.
- `tools/spu_capture.py` — SPU capture helper, same class as `SPU_DUMP_OVL` / the MotorStorm and GT5 lift scripts already listed.

**Can't:** no new standalone `.rrc` or GCM FIFO replay tool appeared in this repo either.

---

### 9. tekulvw/mag-recomp — large MIT tool chest, mostly MAG-specific

**Link:** https://github.com/tekulvw/mag-recomp (MIT, last push 2026-11-26T11:13:43Z = 14:13 Asia/Kuwait)

**Verified:** GitHub API + tools directory (62 entries) + the header of `tools/movie_picture_hooks.py`.

**Does:**
- Many graphics/SPU assessors (`draw_outcomes_assess.py`, `check_render_frontend_d3d12_gpu.py`, `graphics_trace_hooks.py`, WWS job lift). Patterns only; they are written against MAG's lifted names and ELF hash.
- `movie_picture_hooks.py` is **pinned to MAG retail v1.0** (`RETAIL_ELF=0089f0d6…` and two hard-coded `func_009841FC` / `func_00E14D48` sites). It is not a PAMF decoder and will not apply to Strikeforce as-is. It shows one way a port hooks movie-texture delivery after the decoder has already produced a picture.

**Can't:** do not splice those hooks into Strikeforce. Useful as a read, not as a patch.

---

### 10. Redgrave961/Vajra — firmware lift on a cutscene-heavy title

**Link:** https://github.com/Redgrave961/Vajra (MIT, last push 2026-11-25T11:58:52Z = 14:58 Asia/Kuwait)

**Verified:** GitHub API + README + `port/` listing.

**Does:**
- A shipping-style Asura's Wrath port (Windows / Linux, Vulkan) on ps3recomp.
- `port/lift_firmware.py` and `port/lift.py` are a public firmware-module lift path, the same *class* of work as the approved local libsre LLE track. Worth reading as a procedure, not as something to run against Saud's firmware from this box.
- `port/tools/` is packaging (`prxgen.py`, AppImage, icons), not a movie demuxer.

**Can't:**
- No `sail.cpp` / PAMF tool showed up in `port/`. VERIFY how Vajra actually plays its cutscenes before treating it as a decoder template (ps3kit / KZ1 sail.cpp remain the known MIT templates).
- Firmware bytes are not in the repo; lifting still needs the operator's own firmware.

---

### 11. N64 static-recomp save states — design only (GPL runtime)

**Links (live):**
- https://github.com/N64Recomp/N64ModernRuntime (GPL-3.0, last push 2026-11-03T06:41:20Z = 09:41 Asia/Kuwait)
- https://github.com/sciaschi/CBFD-Recompiled (GitHub licence MIT, last push 2026-11-19T02:26:14Z = 05:26 Asia/Kuwait)

**Does (design, from the CBFD `recomp/README.md` description, not copied here):**
- Record each thread's last wait point (native-stack hash plus wait values).
- Save/load guest memory, thread contexts, clocks/timers and event state only when every thread is waiting at a matching call site.

That is still the right *shape* for a test-only in-stage snapshot of a static recomp, and it matches Saud's approval (tests only; the retail path still plays cutscenes).

**Can't:**
- **N64ModernRuntime is GPL-3.0.** Do not copy `save_states.cpp` or the runtime into the port. Reimplement under MIT, in our HLE, if Salem's feasibility check says the state can be serialised.
- A GitHub code search for `savestate` / `save_state` / `SaveState` in ps3recomp-related C/C++ returned **zero** hits this turn. No ps3recomp port publishes one yet.
- XenonRecomp / UnleashedRecomp do not offer emulator-style savestates. ReXGlue's SDK is reported to have **removed** its save-state code in a 0.11.0-dev nightly (secondary web source; VERIFY against the current rexglue-sdk tree before repeating that as a hard fact). Either way, there is no licence-safe drop-in to take.

---

## Checked and rejected, or not what we need

- **No MIT/BSD PAMF demuxer found.** Official FFmpeg was not found to ship a PAMF demuxer. `librempeg/librempeg` added a `pamf` demuxer (Changelog, version 8.0); that project is **GPL v3-or-later** (https://github.com/librempeg/librempeg, https://github.com/librempeg/librempeg/blob/master/LICENSE.md). Reference only. The licence-safe path is unchanged: write a small MPEG-PS / PAMF header reader (ps3kit `mpegps.h` / `sail.cpp` as the MIT model) and feed AUs to P's existing run-time FFmpeg loader + `at3_standalone`.
- **TeamPBCN/pmftools** is MIT but is for **PSP PMF**, not PS3 PAMF.
- **scribam/ps3-fnids-db** — archived, last push 2019-04-28, no licence. Too old for this 2025–2026 pass; sce_symbols supersedes it as a lookup source.
- **TeamFAPS/PS-RE-tools** (`ps-nids-extract`) — GPL-3.0, last push 2023-09-29. Not recent, and not copyable.
- **No new standalone RSX/GCM FIFO replay tool** and still **no standalone `.rrc` viewer** beyond RPCS3 itself and P's `parse_rrc.py` / `RSX_CAP` (already listed). CellGov traces are CPU-side and have no rasteriser.
- **Jolly-Baron/JB-PS3Recomp**, **maceeek/AnyPS3** (GPL-2.0), and most of the other 2026 game-port repos are ports, not reusable tools, or they lack a licence.
- **eth-man/ps3-cell-re-tools**, nucleus, dssim, spu2c: already rejected in the earlier tools note.

## Suggested use (Salem, Windows)

1. **NIDs today:** look up the 72 unresolved NIDs in `nids.txt` (do not copy the file into the tree). Confirm every hit with P's `nid_database.py` or the SHA-1 formula. Wire the six verified cellSail/cellPamf names into the local NID table.
2. **Movies:** run PAMFtool `-info` / `-demux` **or** `pamf_probe.py` on a real Strikeforce `.pam` (external GPL exe is fine). Then keep the MIT path: ps3kit-style cellSail + P's FFmpeg runtime + `at3_standalone`.
3. **0xC0000005:** turn on a minidump on crash; `minidump-stackwalk` it in the loop. For the next repro, record with TTD. Optionally build one ASan clang-cl variant.
4. **Test-only in-stage start:** borrow Killzone 3's "private profile copy, Continue cleared, pad route into the window" pattern if a full HLE snapshot is not ready. Retail cutscenes stay intact. If a snapshot is built, reimplement the N64 "all threads at a wait point" idea in MIT code; do not copy GPL.
5. **RSX replay:** no new off-the-shelf tool. Keep RSX_CAP + `parse_rrc.py` + `rpcs3 --headless --rsx-capture`, and build the planned offline replay if it stays cheap.
