# 1791_spursfix — stage-change hang root fix (TEST COPY ONLY)

Saud approved 19:56 Kuwait (widget): «إي ابن تصليح علّقة المراحل وجربه بنسخة التجربة».

- Exe: `sfauto\exe_copies\1791_spursfix\MyGameRecomp.exe`, MD5 `9E2E235895147354FDE053465CCE8018`, 189,293,056 bytes, built 20:00 Kuwait (UTC+3).
- Base: bundle1787 sources (= 1786_movie_v5 + [sf-lc] lifecycle + LFQ watch + ATRAC fields + RSX census). Isolated tree `sfauto\spursfix1791\src\`; build script `build_spursfix.ps1`; shared tree md5 before == after. PLAY_Strikeforce.bat and originals untouched.
- Launchers: `PLAY_Strikeforce_SPURSFIX1791.bat` (automation, state_spursfix) and `PLAY_Strikeforce_SPURSFIX1791_PAD.bat` (real pad, Saud's state_ringwatch). A/B switch: `SF_SPURSFIX=0` = old no-op behaviour. `SF_SPURSFIX_JOIN_MS` (default 3000).

## Evidence for the cause (CONFIRMED, SFRACE stderr 19:01 run)
Stage end calls `cellSpursShutdownTaskset` + `cellSpursJoinTaskset` (NIDs 0xA789E631 / 0x9F72ADD3) on 0x16FA2000 (lr 0x0058F994), 0x14C7C800, 0x14C02A80 (lines 175118-175132). Our HLE had both as no-ops. Tasks parked in WAIT_SIGNAL stayed parked; 0x14C02A80 is then re-created at the same EA with the same args block, so the old task 0 and the new task 0 share one signalled bit (duplicate waiter, lost wake).

## Fix (our own code; idea in the spirit of ps3recomp PR #809 / Folklore's teardown notes, no code copied)
- Shutdown: mark the taskset "down", wake parked tasks. A task parked (or parking) in a down taskset leaves via the normal task-exit landing pad (`spu_halt`), so the usual task_exited bookkeeping runs.
- Down tasksets start no new tasks.
- Join / Destroy: wait (bounded) until no host thread of that taskset is alive; log `[sf-lc] taskset_join_done ... left= waited_ms=`.
- Create at an EA with live tasks: same teardown first, then clear the down mark, running bits, wake latch and round state for that EA (`[sf-lc] taskset_flush`).
- New log lines: `[sf-lc] taskset_down`, `task_kill`, `taskset_join_done`, `taskset_recreate_live`, `taskset_flush`, `[sf-fix] SF_SPURSFIX=`.

Diffs: `spu_workload.diff`, `cellSpurs.diff`, `spu_channels.diff` (base = bundle1787).
