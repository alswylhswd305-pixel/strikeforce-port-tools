# Building a tester exe (log-only + approved cheats)

Do **not** do this while Saud is playing, while another agent is compiling
`port\bld`, or by overwriting `sfauto\exe_copies\1786_movie_v5`.

Goal: a new folder `sfauto\exe_copies\1786_autotest\` that is movie v5
plus existing `SF_HLE_LRLOG` (from the 1786 voicediag `tail_block.cpp` /
`ppu_hle.cpp` hook) plus optional `strikeforce_godmode.inc`.

Allowed: log-only diagnostics (standing approval) and the approved test-copy
cheats (teleport, god mode). Anything that changes game behaviour beyond
those cheats needs Saud's OK — stop and report.

Steps (when the machine is idle):

1. Copy `1786_movie_v5\MyGameRecomp.exe` sources / working tree, do not take
   his live play exe out from under him.
2. Include `strikeforce_godmode.inc` the same way `strikeforce_movie.inc` is
   included, and call `sf_godmode_start()` next to `sf_voice_mon_start()`.
3. Keep the 1786 HLE LR log (`SF_HLE_LRLOG=1`) so coverage.ps1/py can see
   `[hle-lr]` / `[hle-lrc]` lines. Movie v5 as of 27-Nov 18:09 does **not**
   contain that hook (only `1786_voicediag` / the race log-only tree does).
4. `rebuild.ps1` into `port\bld`, then copy the exe to
   `sfauto\exe_copies\1786_autotest\`. Leave `PLAY_Strikeforce.bat` alone.
5. `SF_GODMODE=1` and `SF_GODMODE_ADDRS=<file>` must be used only on this
   exe. The poke helper `lib/godmode.ps1` works on any tester window without
   a rebuild, and is the default until confirmed HP addresses exist (the
   hook writes nothing if the addr file is empty).

This inc was **not** compiled or deployed in this pass.
