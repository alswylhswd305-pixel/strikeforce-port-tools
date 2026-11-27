# Method writeup (early title-screen campaign)

> **Note (2026-11-27, Asia/Kuwait).** This document is the original method writeup from the first native boot to the title screen ("PRESS START"). Work has continued since then: movies play, the port reaches in-stage gameplay, and tools for voice, lighting, hangs, and testing were added. For the full current method use [GUIDE_A_TO_Z.md](GUIDE_A_TO_Z.md) and [ps3_recomp_playbook.md](ps3_recomp_playbook.md).
>
> The "Status: first frame only" paragraph below is **historical**. It is kept so the early verified chain stays dated and is not rewritten.
>
> The title-screen screenshot that originally lived in this writeup is omitted: this repository does not ship game artwork.

### Strikeforce Recomp (original title): Dynasty Warriors: Strikeforce (PS3, BLUS30471) on PC via ps3recomp

**Author: Saud Alsuwailih (سعود الصويلح)**

This repository documents the method, settings and source overrides that took *Dynasty Warriors: Strikeforce*
(PS3, US release BLUS30471) from a black window to its **title screen ("PRESS START BUTTON") as a native Windows
build**, using the static recompiler [ps3recomp](https://github.com/sp00nznet/ps3recomp) v0.20.0.

> **Status: first frame only.** The title screen renders (1280x720, ~63 FPS, 946 flips in a 90 s run, no crash).
> Input does not work yet (Start does nothing), audio is partial, and nothing past the title screen has been tested.
> This is a research/preservation project, not a playable release.


**No game content is in this repository.** No disc files, no EBOOT/ELF/SELF, no decrypted binaries, no recompiled
game code, no firmware, no keys. The method requires **your own dump of your own original disc** (see [Requirements](#requirements)); the author developed it with a dump of his own original disc.

---

## Contents

| Path | What it is |
|---|---|
| `port/strikeforce_videoout.inc` | **Key fix.** `cellVideoOutGetDeviceInfo` (NID 0x1E930EEF) with the SDK struct layout |
| `port/strikeforce_lfqueue.inc` | Clean-room `_cellSpursLFQueueInitialize` (0x011EE38B) / `_cellSpursLFQueuePushBody` (0x8A85674D) |
| `port/strikeforce_l10n.inc` | Clean-room `UCS2stoUTF8s` (cellL10n, 0x2AD091C6) |
| `port/strikeforce_knobs.inc` | Logging wrappers for `cellGameBootCheck`, `cellGameDataCheck`, `sceNpTrophyGetRequiredDiskSpace` (+ optional knobs) |
| `patches/0001-…stubs….diff` | ps3recomp template `stubs.cpp`: include and register the four overrides |
| `patches/0002-…main….diff` | ps3recomp template `main.cpp`: start the `PS3_SAMPLE` sampler (diagnostic only) |
| `patches/0003-…syscall352….diff` | ps3recomp runtime: syscall 352 reports the real user-memory size |
| `patches/optional-planD-spurs-ef-force-count.diff` | Optional stopgap: `SPURS_EF_FORCE=<N>` waits N×2 ms before faking a SPURS event flag (A/B testing only) |
| `tools/sfauto/` | `sfauto.py`: automated run → findings → explore → feedback loop (stdlib Python) + `shot.ps1` window capture |
| `tools/nid/` | `nid.py` (SHA-1 NID computation and name resolution), `unbound_imports.py` (imports with no HLE handler) |
| `tools/trace/build_table.py` | Builds the numbered code table from RPCS3's cache vs the ps3recomp lift |
| `tools/diagnostics/` | Plan C heap instrumentation (`patch_heap.py`), Plan D function index (`fx.py`) and relocated-rebuild trick (`reloc.py`, `hashtool.cpp`), Plan B RPCS3 watcher (`rpcs3_watch.ps1`, `shotwin.ps1`) |
| `scripts/` | Windows PowerShell: `env.example.ps1`, `setup-work.ps1`, `copy_disc.ps1`, `lift.ps1`, `build.ps1`, `rebuild.ps1`, `run.ps1` |
| `docs/` | `fix-log.md` (verified fix chain), `research-0x003B.md`, `unbound-imports.md`, `trace-table.md`, `roadmap-parts-plan.md` |

All patches are against **ps3recomp v0.20.0, commit `d81c393`** and were checked with `git apply --check`.

---

## Requirements

**You supply (never commit or share any of these):**
- Your own **Dynasty Warriors: Strikeforce (BLUS30471)** disc, dumped by you from a disc you own.
- A **decrypted EBOOT.elf** of that game made by you, e.g. with RPCS3's own "Decrypt PS3 Binaries" on your installed copy.
  This project ships no keys and gives no decryption steps.
- **PS3 system firmware** downloaded from Sony's official site and installed into your own RPCS3 (its `dev_flash` is used read-only).
- Laws on dumping/decrypting your own copy differ by country. Check yours.

**Tools (Windows 10/11 x64, what the working build used):**
- Visual Studio 2022 Build Tools (MSVC 14.44), clang-cl (LLVM 23.1.4), CMake 4.x, Ninja 1.13, Python 3.12 (no pip packages needed), Git.
- A D3D12-capable GPU (tested on an RTX 5080).
- ~10 GB for the disc copy, ~5 GB for the build. Full build ≈ 16 min (8 jobs).
- Optional: [RPCS3](https://rpcs3.net) for differential comparison.

---

## Build and run (step by step)

```powershell
# 0) configure paths (env.local.ps1 is git-ignored)
Copy-Item scripts\env.example.ps1 scripts\env.local.ps1   # edit SF_ROOT, SF_ELF, SF_DEV_FLASH, SF_DISC_SOURCE, SF_VCVARS
. .\scripts\env.local.ps1

# 1) clone ps3recomp @ d81c393, copy its project template, add port/*.inc, apply patches 0001-0003
.\scripts\setup-work.ps1

# 2) copy YOUR disc contents to <work>\vfs\dev_bdvd   (or: -Iso <your own ISO>)
.\scripts\copy_disc.ps1

# 3) lift YOUR EBOOT.elf (ppu_loader -> ppu_lifter -> SPU workloads, 40/41 images with --allow-partial)
.\scripts\lift.ps1

# 4) build  ->  <work>\port\bld\MyGameRecomp.exe
.\scripts\build.ps1          # later edits: .\scripts\rebuild.ps1

# 5) run with the title-screen settings (or use sfauto, below)
.\scripts\run.ps1 -Secs 90
python tools\sfauto\sfauto.py run --secs 90 --env SPU_INTERP_UNLIFTED=1 GCM_FLIPCOUNT=1
```

Expected: a window titled `ps3recomp | FPS: ~63 | draws: 6 | 1280x720` showing the title screen after ~45 s.

Notes:
- The scripts are cleaned-up versions of the exact scripts used on the working machine (paths parameterised).
  `setup-work.ps1` and `lift.ps1` were reassembled from the logs and upstream docs and have not been re-run end to end from a clean folder.
- v0.20.0's automatic SPU discovery (`PORT_SPU_INPUTS`) fails on SPU image 375200614 (overlapping PT_LOAD). `lift.ps1` uses the
  upstream `build_spu_workloads.py --allow-partial` route instead (40/41 images); the missing image was not needed for the title screen.
- The template ignores the optional `[vfs-root]` argument; always set `PS3_VFS_ROOT`.

---

## Settings / environment variables

**Required for the title screen** (set by `scripts/run.ps1` and sfauto's `BASE_ENV`):

| Variable | Value | Why |
|---|---|---|
| `PS3_VFS_ROOT` | `<work>\vfs\dev_bdvd` | **Key.** ps3recomp maps `/dev_bdvd/X` to `<root>/X`. Pointing at `vfs\` made the game poll `/dev_bdvd/PS3_GAME/USRDIR/LINKDATA.IDX` forever on a black screen |
| `PS3_HDD0_ROOT` | `<work>\state\hdd0` | Writable `/dev_hdd0` (game data, saves) |
| `PS3_HDD1_ROOT` | `<work>\state\hdd1` | Writable `/dev_hdd1` (cellSysCache) |
| `PS3_GAMEDATA_ROOT` | `<work>\state\gamedata` | Persists trophy state, so `sceNpTrophyGetRequiredDiskSpace` returns 0 and the "insufficient free space" dialog stops |
| `PS3_DEV_FLASH` | your RPCS3 `dev_flash` | Read only; supplies `flashATRAC.pic` |
| `SPU_INTERP_UNLIFTED` | `1` | Needed for audio: the MultiStream SPU task (image 391227015) jumps into `flashATRAC.pic`, loaded from dev_flash at runtime and not liftable from the EBOOT |

**Port knobs (this repo):**

| Variable | Effect |
|---|---|
| `SF_VIDEO_MODES=1080` | `strikeforce_videoout.inc` also reports a 1080p mode (default: one 720p mode) |
| `SF_FREE_KB=<n>` / `SF_TROPHY_REQ=<n>` | Rewrite reported free HDD space / trophy space. **No longer needed** once `PS3_GAMEDATA_ROOT` persists |
| `SPURS_EF_FORCE=<N>` | Only with the optional Plan D patch: fake a SPURS event-flag pattern after N waits (A/B only; not a fix) |

**sfauto tool:** `SF_ROOT`, `SF_EXE`, `SF_ELF`, `SF_DEV_FLASH`, `SF_RPCS3_CACHE` (see `scripts/env.example.ps1`).

**ps3recomp v0.20.0 diagnostics used during debugging** (all exist in the v0.20.0 source; not needed to run):

| Variable | Use |
|---|---|
| `PS3_HLE_TRACE=<n>` | Trace the first n HLE calls |
| `PS3_CALLTRACE=<n>` | Guest call trace ring |
| `PPU_VCALL_BT=1` | Backtrace on bad indirect (vtable) calls |
| `PS3_HLE_UNRESOLVED=fail` | Return an error instead of faking `CELL_OK` for unhandled NIDs (find which import matters) |
| `PS3_HLE_ARGS=<nid>` | Print r3–r10 for one NID |
| `PPU_NOOP_BAD_VCALL=1` | Turn calls below 0x10000 into no-ops (band-aid, diagnosis only) |
| `PS3_FSLOG=1` | Log file-system access |
| `GCM_FLIPCOUNT=1`, `GCM_DRAINDBG=1`, `GCM_FLIP_BT=<n>` | RSX flip / FIFO diagnostics |
| `PS3_HLE_TOP=<s>` | Periodic top-N HLE call counts |
| `PS3_SAMPLE=<ms>` | PC sampler (with patch 0002) |
| `MSGDIALOG_ANSWER`, `MSGDIALOG_AUTODISMISS_MS`, `PS3_GAME_FREE_SPACE_RAW` | Dialog/space knobs explored by sfauto |
| `LD_FRAME_DUMP` | Dump frames |

---

## The fix chain (what actually got the first frame)

Full details with addresses: [`docs/fix-log.md`](docs/fix-log.md).

1. **SPURS LFQueue** (`strikeforce_lfqueue.inc`): v0.20.0 faked `_cellSpursLFQueuePushBody` as `CELL_OK`, so nothing was pushed and the SPU consumer spun forever.
2. **cellL10n** (`strikeforce_l10n.inc`): `UCS2stoUTF8s` was faked, so dialog text arrived empty.
3. **Syscall 352** (patch 0003): a fixed "192 MB available" made the game's ~126 MB heap request fail with ENOMEM.
4. **cellVideoOutGetDeviceInfo — the root cause** (`strikeforce_videoout.inc`): the v0.20.0 HLE omits the 0x14-byte `colorInfo` block, so the
   mode table lands at +0x0C instead of +0x20 with refresh rate 0. The game's video mode picker found no 720p mode → device init returned 0 →
   heap setup was skipped → the game heap stayed empty → the first allocation returned NULL → a call through a NULL object
   (the "NULL bctr at opd 0x7190" crash). Reporting one 720p / progressive / 16:9 / 59.94+60 Hz mode fixed it.
5. **File system roots**: `PS3_VFS_ROOT` must point at `vfs\dev_bdvd`; writable `PS3_HDD0_ROOT`/`PS3_HDD1_ROOT`.
6. **Audio side-finding**: `SPU_INTERP_UNLIFTED=1` for dev_flash ATRAC SPU code.

---

## The debugging method

1. **Differential comparison with RPCS3.** RPCS3 running the same disc is the reference ("golden") run. Its logs, its PPU/SPU caches and its
   behaviour are compared with the recompiled build to find the first point where they diverge. `tools/diagnostics/rpcs3_watch.ps1`
   runs RPCS3 headless-ish with periodic screenshots and keeps `RPCS3.log`.
2. **Numbered code table.** `tools/trace/build_table.py` parses RPCS3's SPU cache (`spu-safe-v1-tane.dat`: 2,071 SPU programs that really ran)
   and PPU LLVM object symbols (236,598 block labels) and matches them against the ps3recomp lift. Result: no PPU code outside the lift;
   one SPU image (375200614) not liftable by v0.20.0 but heavily used. See [`docs/trace-table.md`](docs/trace-table.md).
3. **NID resolution by SHA-1.** A PS3 function NID is the first 4 bytes (little-endian) of
   `SHA-1(name + 6759659904250490566427499489741A)`. `tools/nid/nid.py` computes it (self-tests: `cellSysmoduleLoadModule` → 0x32267A31,
   `UCS2stoUTF8s` → 0x2AD091C6) and resolves unknown NIDs by hashing identifiers from a local RPCS3 checkout. This named the 78 unbound
   imports ([`docs/unbound-imports.md`](docs/unbound-imports.md)) and sysmodule 0x003B = `CELL_SYSMODULE_SYSUTIL_OSK_EXT`.
4. **Logging stubs / wrappers.** Instead of guessing, each suspicious HLE function is wrapped (`ps3_hle_register_ctx`) so it logs exactly what the
   game received (`[sf-knob]`, `[sf-vo]`, `[sf-l10n]`, `[sf-lfq]`). Temporary instrumentation in the local lifted code (e.g. `patch_heap.py`)
   traced the heap failure back to the video-mode picker. Remove all such instrumentation before sharing builds.
5. **Automated exploration (sfauto).** `sfauto.py run` launches the build, captures screenshots and the window title (FPS/draws), and parses logs into
   `findings.json` (unresolved NIDs, NULL calls, dialogs, threads, flips). `explore` mutates env knobs in doubling rounds (1, 2, 4, 8) with an
   AFL-style novelty signature; `feedback` writes `functions_add.json` / `overrides_todo.md`; `harvest` builds the code table.
   (Repeat `--env` as `--env A=1 B=2`.)
6. **Parallel competing hypotheses.** Four isolated copies of the work folder tested four hypotheses at the same time (see below).
7. **Fast rebuilds.** Incremental `rebuild.ps1` after `.inc` edits; Plan D's `reloc.py` lets a copied work folder reuse a finished Ninja build
   instead of a 16-minute full rebuild (experimental).

---

## How this was made

Saud Alsuwailih designed the method and directed the project. He ran it as a **multi-agent AI workflow**:

- A **research agent** did literature and source analysis only (RPCS3 and ps3recomp source/docs at pinned commits). It identified sysmodule 0x003B
  as the on-screen-keyboard extension (`CELL_SYSMODULE_SYSUTIL_OSK_EXT`, 17 `cellOskDialogExt*` functions), confirmed the SHA-1 NID scheme
  (and that ps3recomp's own NID doc was outdated), and proposed the **NULL-object hypothesis**: 0x7190 is below 0x10000, so it is a field offset
  read from an object pointer that was never filled, not a real function descriptor ([`docs/research-0x003B.md`](docs/research-0x003B.md)).
- An **execution agent** built, ran and instrumented the port on Saud's PC (build scripts, logging wrappers, sfauto runs, screenshots).
- **Four competing hypotheses were tested in parallel**, each in its own isolated copy, sharing nothing but the read-only disc data:
  - **A — main fix path** (follow the crash forward with fixes),
  - **B — differential comparison with RPCS3** (reference run, logs, screenshots),
  - **C — import/NID resolution** (78 unbound imports named; heap instrumentation),
  - **D — instrumented logging stubs** (SPURS event-flag A/B, fast relocated rebuilds).
- The lines of evidence converged on one root cause: **`cellVideoOutGetDeviceInfo` struct layout → no 720p mode → heap not created → NULL object**.
  Plan A applied the fix and reached the title screen first; the other plans were then stopped.

### كيف انسوى المشروع (ملخص بالعربي)

سعود الصويلح هو صاحب المشروع، صمّم الطريقة وأدارها. اشتغل بفريق ذكاء اصطناعي من أكثر من وكيل:
- **وكيل بحث**: يقرأ المصادر بس (كود RPCS3 وps3recomp)، وعرف إن 0x003B هو لوحة المفاتيح على الشاشة، وأكّد طريقة حساب أرقام الدوال (NID) بـSHA-1، واقترح إن العطل سببه كائن فاضي (NULL).
- **وكيل تنفيذ**: يبني ويشغّل ويسجّل على جهاز سعود.
- **أربع خطط بنفس الوقت**، كل وحدة بنسخة منفصلة: A الإصلاح الأساسي، B المقارنة مع محاكي RPCS3، C حل أسماء الدوال الناقصة، D دوال تسجيل للتشخيص.
- كل الخطط وصلت لنفس السبب: دالة معلومات الشاشة (cellVideoOutGetDeviceInfo) كانت ترجع بيانات بترتيب غلط، فاللعبة ما لقت وضع 720p، وما سوت الذاكرة، وصار الكائن فاضي. الخطة A صلّحتها ووصلت لشاشة البداية.

---

## Known issues / next steps

- **Input**: Start does nothing yet; `cellPad` → XInput/keyboard mapping is the next step.
- **Audio**: ATRAC SPU code from dev_flash runs only in the SPU interpreter (`SPU_INTERP_UNLIFTED=1`); cellAtrac has 7 unbound imports; cellSail (FMV) has 16.
- **SPU**: image 375200614 (overlapping PT_LOAD) is not lifted by v0.20.0; RPCS3 shows it is the 2nd most-used SPU image. 276 SPU programs come from outside the EBOOT (firmware SPURS/taskset).
- **RSX**: only the title screen (6 draws/frame) has been exercised.
- `cellGameBootCheck` reports placeholder title ID `BLES00000`; game data goes to `hdd0/game/BLES00000`.
- 5,853 lifted entries have no RPCS3 label (possible false function starts).
- Upstream: ps3recomp master after v0.20.0 fixes a lwmutex/SPURS/Windows-lock regression (commit 316be1d, PR #847). Rebasing onto newer master is untested.
- See [`docs/roadmap-parts-plan.md`](docs/roadmap-parts-plan.md).

---

## Credits and licenses

- **[ps3recomp](https://github.com/sp00nznet/ps3recomp)** by Ned Heller / sp00nznet and contributors — MIT License. The patches here modify
  ps3recomp files and the overrides are built against its runtime; ps3recomp's copyright and license notice apply to those parts
  (see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)).
- **[RPCS3](https://github.com/RPCS3/rpcs3)** — GPL-2.0. Used as a separate program for reference runs, and its public source was read for
  documentation (struct layouts, NID scheme). **No RPCS3 code is copied into this repository.**
- `hashtool.cpp` needs `rapidhash.h` from [Nicoshev/rapidhash](https://github.com/Nicoshev/rapidhash) (MIT), not bundled.
- Dynasty Warriors: Strikeforce is © KOEI TECMO. PlayStation is a trademark of Sony Interactive Entertainment. This project is not affiliated with either.

## License

Copyright (C) 2026 Saud Alsuwailih

The author's own files (`port/*.inc`, `tools/`, `scripts/`, `docs/`, README) are licensed under the
**GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later)**. Full text: [`LICENSE`](LICENSE).

In short: using and changing it yourself is free. If you **distribute** it, or **let others use a modified version over a
network**, you must publish your corresponding source code under the same license.

- Files in `patches/` that modify ps3recomp keep ps3recomp's **MIT** notice (see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)).
- This license covers this code only. It grants **no rights** to the game, its data, PS3 firmware, or any Sony or KOEI TECMO material.

This program is distributed WITHOUT ANY WARRANTY; see the license for details.
