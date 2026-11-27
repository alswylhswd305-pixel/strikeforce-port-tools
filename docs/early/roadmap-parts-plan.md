# Strikeforce port: plan by parts (finish each before the next)
Status 2026-11-26 06:00 (Kuwait time UTC+3). Test folder: <work>

## Part 1: Graphics, first frame (CURRENT)
Done criteria: the game issues a flip with real draws (window title draws > 0), and a screenshot shows game pixels.
- [x] D3D12 window up on the RTX 5080. RSX FIFO runs: CLEAR_SURFACE commands, semaphore releases advancing. Window black, draws: 0.
- [x] SPURS LFQueue push and init overrides (strikeforce_lfqueue.inc): graphics SPU image 437063289 consumes work.
- [x] cellL10n UCS2stoUTF8s (strikeforce_l10n.inc): the dialog text now reads correctly.
- [x] Disc copied to vfs\dev_bdvd (8.74 GB, 67 files).
- [~] Boot dialog "insufficient free space… at least 1MB". sfauto found that SF_TROPHY_REQ=0 gets past it.
  Raising the reported free space (SF_FREE_KB) does not help. Root cause still open: trophy-install accounting. Each sfauto run has a fresh cwd, so the trophy-installed state never persists between runs.
- [ ] NEXT BLOCKER: main thread loops on `bctr to NULL from func_0007C008+0xD30, opd=0x00007190`.
  This is a call through a table that was never filled, right after `LoadModule(0x003B)` and the DrmIsAvailable/RegisterTrophy threads start.
  Find what fills 0x7190: an unknown sysmodule 0x003B, or an HLE call that fakes success without writing.
- [ ] Then: the first flip, draws > 0, and a screenshot.
- [ ] Lift SPU image 375200614 (overlapping PT_LOAD). RPCS3 ran 226 programs from it, the 2nd most-used image. Likely needed for real rendering and game logic.
## Part 2: Audio (after Part 1)
- cellAudio port and mixing. ATRAC3plus (cellAtrac) and Sail (movies). Point flashATRAC.pic at dev_flash. RPCS3 cache shows the SPU images in use.
## Part 3: Input
- cellPad mapped to XInput/keyboard. Plus sfauto input scripts, so later runs can reach menus and battles.
## Part 4: CPU/SPU completeness
- 78 missing NIDs (ranked by sfauto hits), 276 SPU programs from outside the EBOOT (firmware SPURS/taskset), and the 5,853 lifted entries RPCS3 has no label for (possible false starts).

## Tool: sfauto (test folder \sfauto, source on box /workspace/ps3recomp-study/sfauto)
Works: `run` (one run, parsed into findings.json), `explore` (doubling rounds 1,2,4,8 with an AFL-style corpus and novelty signature),
`feedback` (functions_add.json, insn_patches.json, overrides_todo.md), `harvest` (RPCS3 cache table).
Port knobs: SF_FREE_KB and SF_TROPHY_REQ (strikeforce_knobs.inc). Existing runtime knobs are also used.
Not yet: in-tool screenshots (file not written), lift_hooks coverage stage (needs a re-lift plus a 16-min rebuild),
file/function-level fuzzing (only env/override knobs so far), the `ai` step (needs a local OpenAI-compatible server, for example LM Studio; skipped when unreachable),
and automatic re-lift with --functions / --insn-patches (the files are produced, but the re-lift is still manual).

## Progress log 2026-11-26 06:00-06:50 (Asia/Kuwait)
Plan change (Saud t1292u): get every subsystem minimally working toward the FIRST REAL FRAME; sfauto generalisation deferred.

Root cause of the "NULL bctr at opd 0x7190" (VERIFIED by runs):
1. syscall 352 reported a fixed 192 MB; the 126 MB heap allocation failed -> fixed in ppu_loader.cpp (runtime copy in test folder).
2. The real blocker: cellVideoOutGetDeviceInfo (v0.20 SDK HLE) writes the mode table at +0x0C with refreshRates=0; the SDK layout has a 0x14-byte colorInfo
   so modes start at +0x20. PSGL's mode picker (0x52CD60) found no 1280x720 mode -> device setup 0x4C9E54 returned 0 -> 0x4CA508 skipped
   heap setup 0x4CA260 -> game heap 0xC3A79C empty -> first alloc NULL -> object NULL -> vtable call through NULL+0x7190 region.
   Fix: port/strikeforce_videoout.inc (ctx override NID 0x1E930EEF, SDK layout, one 720p mode @59.94/60 Hz).
   Result: null calls/writes gone, heap set up, PSGL device OK, main loop flips ~62/s (FIFO drains, flip words decoded).
3. Next wall: game polls cellFsStat('/dev_bdvd/PS3_GAME/USRDIR/LINKDATA.IDX') every frame -> ENOENT, because PS3_VFS_ROOT
   pointed at vfs\ (ppu_fs maps /dev_bdvd/X to <root>/X). Fix: PS3_VFS_ROOT=vfs\dev_bdvd (sfauto BASE_ENV). Game now reads LINKDATA.
4. Then: /dev_hdd1 (cellSysCache) and /dev_hdd0 had no writable roots -> added PS3_HDD0_ROOT/PS3_HDD1_ROOT = sfauto\state\hdd0|hdd1.
Audio side-finding: MultiStream SPU task (image 391227015) jumps into flashATRAC.pic loaded from dev_flash at runtime (not liftable from
EBOOT) -> SPU_INTERP_UNLIFTED=1 runs it in the SPU interpreter; KslMsUpdater then cycles normally.
sfauto bug fixed: repeated --env flags overwrote each other (argparse) -> action="extend".
