# Fix log: from black window to the title screen

_Source: the Plan A worker's verified notes (2026-11-26, Asia/Kuwait). PC paths replaced with `<work>`._

Verified run: sfauto run 20261126-064739-c5d2ce (06:47 Asia/Kuwait). 946 flips, 6 draws/frame, 63 FPS, title art on screen,
no crash, no null calls. Screenshot: screens/14_title_screen_87s.png (box). Saud saw "PRESS START BUTTON" himself.
State snapshot: PC <work>\state-title-screen-20261126\ (+ .zip), box saud-prior/state-title-screen-20261126.zip
(port sources and tool only; no game data; the .exe is in the PC folder only).

## Code changes (all in the test folder <work>)
1. port/strikeforce_lfqueue.inc: clean-room `_cellSpursLFQueueInitialize` (0x011EE38B) and `_cellSpursLFQueuePushBody` (0x8A85674D).
   Without them the SPU consumer spun forever.
2. port/strikeforce_l10n.inc: clean-room `UCS2stoUTF8s` (0x2AD091C6). Dialog text was empty without it.
3. port/strikeforce_knobs.inc: logging wrappers for `cellGameBootCheck` (0xF52639EA), `cellGameDataCheck` (0xDB9819F3) and
   `sceNpTrophyGetRequiredDiskSpace` (0x370136FE). The env knobs SF_FREE_KB and SF_TROPHY_REQ are NOT needed any more.
4. **port/strikeforce_videoout.inc (KEY FIX)**: `cellVideoOutGetDeviceInfo` (0x1E930EEF) using the SDK struct layout.
   - The bug: the v0.20 HLE leaves out the 0x14-byte colorInfo block. That puts availableModes at +0x0C instead of +0x20, with refreshRates=0.
   - The chain it caused: PSGL's mode picker (0x52CD60) found no 720p mode, so device init 0x4C9E54 returned 0. 0x4CA508 then skipped
     heap setup 0x4CA260, the game heap (0xC3A79C) stayed empty, the first allocation (0x4BD440) returned NULL, and the code
     called through a NULL object. That is the "NULL bctr at opd 0x7190".
   - The override reports one mode: 720p, progressive, 16:9, refresh 0x0005 (59.94 + 60 Hz).
5. port/stubs.cpp: includes the 4 .inc files and registers them in ps3_load_prx_modules(). Backup: stubs.cpp.orig.
6. ps3recomp/runtime/ppu/ppu_loader.cpp (SDK runtime copy in the test folder):
   - Syscall 352 now returns `sys_memory_get_user_memory_size()` instead of a fixed total 256 MB / available 192 MB.
   - Before this, the 126 MB heap allocation got ENOMEM.
   - Backup: ppu_loader.cpp.orig.
7. port/main.cpp: one line, `ps3_sampler_start()` (sampler for PS3_SAMPLE). Diagnostic only. Backup: main.cpp.orig.
8. port/recompiled/ppu_recomp_002.cpp: TEMPORARY `[sf-dbg]` fprintf lines in 0x4C9E54/0x52EC74. Diagnostic only; revert from
   ppu_recomp_002.cpp.orig before publishing.

## Runtime environment (set by sfauto BASE_ENV, plus the run flags)
- PS3_VFS_ROOT=<work>\vfs\dev_bdvd (**KEY**). ppu_fs maps /dev_bdvd/X to <root>/X. With root=vfs\, the game polled
  /dev_bdvd/PS3_GAME/USRDIR/LINKDATA.IDX every frame (ENOENT) on a black screen.
- PS3_HDD0_ROOT=<work>\sfauto\state\hdd0 and PS3_HDD1_ROOT=<work>\sfauto\state\hdd1 (writable game data and cellSysCache; the game fills cache/BLUS30471/0000..).
- PS3_GAMEDATA_ROOT=<work>\sfauto\state\gamedata. Trophy state persists here (trophies\NPWR01068.json).
  - Verified: with it persisted, GetRequiredDiskSpace returns 0 and the "insufficient free space" dialog no longer appears.
- PS3_DEV_FLASH=<RPCS3 19155 dev_flash> (read only; supplies flashATRAC.pic).
- SPU_INTERP_UNLIFTED=1 (**needed for audio**):
  - The MultiStream task (SPU image 391227015) branches into flashATRAC.pic, which it loads from dev_flash at runtime (LS 0x32A10, plus 0x2FE90/0x2FE98/0x30AC0).
  - That code cannot be lifted from the EBOOT, so it runs in the SPU interpreter.
  - With it, KslMsUpdater's event flag 0x00DBA900 is set every cycle.
- Diagnostics only (not needed): PS3_FSLOG=1, GCM_FLIPCOUNT=1, PS3_HLE_TOP=<s>, GCM_DRAINDBG=1, GCM_FLIP_BT=<n>, PS3_SAMPLE=<ms>.
- No longer needed: SF_TROPHY_REQ, SF_FREE_KB, MSGDIALOG_*.
- Disc data: the user's own disc copied to vfs\dev_bdvd (never distributed; the tool extracts code only).

## Tool fix
sfauto `run --env`: repeated --env flags overwrote each other (argparse). Now `action="extend"`; use `--env A=1 B=2`.

## Known open items (not worked on; waiting for Saud's go)
- Input: Start does nothing yet (next step needs approval).
- cellGameBootCheck reports titleId 'BLES00000' (an HLE placeholder); the game data dir is created under hdd0/game/BLES00000.
- DataCheck returns rc=2 (CELL_GAMEDATA_RET_NONE, i.e. new data); fine for now.
- SPU image 375200614 (overlay image) is still not translated. It was not needed for the title screen.
