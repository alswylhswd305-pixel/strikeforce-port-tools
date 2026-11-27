# Strikeforce black screen after Now Loading: MOC job counter (09:30 Kuwait time, UTC+3)

Runs: play19-play27, all on the test copy.

## Earlier claim about the third queue
"q3 (0x14D89700) is never pushed" was a side effect of the 24-line push-log cap. q3 has no jobs while the PPU is stuck. With uncapped logging (`[sf-lfq2]`), q1 and q2 each get 3 pushes in the first frames. After that the main thread waits.

## What the main thread actually waits on
- **Wait loop.** `func_000F89C8` (the per-frame MOC update) calls `func_0011A230`.
  - That function runs `func_005447CC(h)` for the three job handles at `*(toc-0x5B6C)` = 0x00BE19F0.
  - The handles are h0=0x14C54690 (q1), h1=0x14CBB6B0 (q2) and h2=0x14D22730 (q3).
- **What `func_005447CC` waits for**, yielding with sys 0x2B until each is zero:
  1. `*(P + idx*56 + 0x1C)`, where P = h+0xC;
  2. **`*(h+0x38)`**.
  - h+0x38 is task arg 2: `CreateTask arg=... 14C546C8 ...` for task 7902.
- **Who changes h+0x38.**
  - The PPU only ever stores 0 there (PPU_WWATCH).
  - The MOC SPU image 454077064 (lifted, `spu_b10aa881…`) does an atomic add of 3 (SPU_ATOM_EA with full line: STORE shows +0x48 = 00000003). The call path is 0x114B8 ← 0xB300/0xB440, command handlers of the task's command-list interpreter (loop at 0xACE4). The add itself sits at 0x11B58/0x11BB0.
  - No matching atomic decrement ever happens. The decrement helper is 0x11C18, called only from 0x10F20 at the end of each job in 0x10DF0. It runs only when task-ctx+0x1D0 word0 != 0, and its EA is ctx+0x1D4.
- **Result.** The counter stays at 3 and the main thread spins.

## Debug-only test (SF_MOC_UNSTICK)
Zeroing a counter that has been stuck for N ms lets frames advance:
- q3 gets pushed, and h2's counter goes to 4;
- the window title shows `draws: 874` per frame at 0.25 fps with a 2 s threshold;
- the screen stays black.

So the stage is running and issuing draws. What still blocks it:
1. the missing SPU decrements;
2. most likely, the work those decrements stand for (black output).

## Next
- Find why ctx+0x1D0 is never set, or why the decrement path is skipped, in image 454077064.
  - Compare against an interpreter run: is a lifter bug possible? SPU_INTERP for this image does not exist yet.
  - Read the 0xACE4 command dispatcher (command byte → handler).
- Check whether the decrement is meant to come from another task: the add of 3 vs 3 MOC tasks.

## play27 (SF_MOC_UNSTICK=60)
- The game runs at 8 fps with 874 draws per frame. The screen stays fully black for about 75 s of stage frames.
- So the black screen is not only a slow fade-in.
- Either the draws render nothing (data the MOC/other SPU work never produced, or an RSX-side problem), or the missing decrements also stand for missing work.
- Screenshot: /workspace/sf-shots/play27_225s_1280.png
