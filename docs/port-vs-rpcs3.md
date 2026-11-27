# Strikeforce: our port (ps3recomp) vs RPCS3 — short comparison
Counted 2026-11-26 from /workspace/ps3recomp-study (ps3recomp v0.20 tree + our notes) and /workspace/recomp-refs/rpcs3.

## Size
| | ps3recomp (our port's SDK) | RPCS3 |
|---|---|---|
| Folders / files (no .git) | 349 / 3,137 | 158 / 2,019 |
| HLE module sources | `libs/`: 12 groups, 228 `.c` + 137 `.h` (114 files export functions) | `Emu/Cell/Modules`: 143 `.cpp` (135 register functions) + 43 lv2 syscall `.cpp` |
| Exported HLE functions | 1,286 | 3,709 (`REG_FUNC`) |
| Of those, stubs | 95 bare `return CELL_OK` stubs (*) | 1,664 short `todo()`/UNIMPLEMENTED ones (*) |

(*) Each side was counted its own way, so these are rough. RPCS3's "stubs" are mostly obscure functions, and RPCS3 can also run the real firmware libraries (LLE) for anything it doesn't implement itself. ps3recomp can't do that: a function it doesn't implement just "returns OK" without doing anything (`[hle] UNRESOLVED NID ... faking CELL_OK`). That is the main reason the game runs fully in RPCS3 and not yet in our port.

## What matters for Strikeforce
| Area | ps3recomp | RPCS3 | Effect on Strikeforce / what we did |
|---|---|---|---|
| SPURS (task SPU programs) | 90 fns. Only programs we've translated (lifted) run natively; the rest drop or run in the slow interpreter. Of the taskset syscalls, only WAIT_SIGNAL actually does its job. | 141 fns. It emulates the real SPU, so any SPU program runs. | The cloth/ponytail physics task (KSG2PS3SPUCloth.elf, fp 0x357AF568…, the "image 375200614" that was never translated) was being dropped. Now it runs in the interpreter (`SPU_INTERP_MISS`). |
| cellOvis (SPU overlays) | Our game's import `cellOvisInitializeOverlayTable` had no implementation, so it "returned OK" without doing anything. `GetOverlayTableSize` used the wrong prototype and returned 0. | Same 4 functions marked todo. | Without this, the cloth task loads empty overlay code. We wrote `strikeforce_ovis.inc` with the real behaviour (copies the overlay segments into the table). Suspected cause of the Now Loading hang; being tested now. |
| cellSail (movie player) | 32 fns. Player slots were never freed. | 124 fns (91 todo). | The 5th movie hung. Fixed: Finalize now frees the slot. |
| OSK (name entry) | 12 fns, 4 stubs. LoadAsync sent no events. | 31 fns, a full dialog. | Name entry hung. Fixed with an auto-confirm override (`strikeforce_osk.inc`). |
| AudioOut / cellAudio / cellAtrac | AudioOut is inside cellSysutil, with a struct layout bug. cellAtrac has 22 fns but no streaming. | AudioOut 10 fns, cellAtrac 24 fns. Real decode, through FFmpeg. | The audio fixes waiting in /workspace/sf-shared/audio-fixes (`strikeforce_audioout.inc`, `strikeforce_atrac.inc`) cover this. |
| cellSysCache (hdd1 cache) | Always answers "CLEARED", even when old cache files are there. | Answers "RELAYED" when an existing cache is reused, and wipes the cache after a crash. | This was the stale-cache title-screen bug. Fixed in `strikeforce_syscache.inc`, which behaves like RPCS3 and moves an unclean cache aside instead of deleting it. |
| cellVideoOut | Struct layout bug. | Correct. | Caused the black screen. Fixed earlier (`strikeforce_videoout.inc`). |
