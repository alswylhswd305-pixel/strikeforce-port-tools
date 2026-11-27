# Strikeforce auto play-tester

Test-copy only (`%SF_LOCAL_PATH%
Does not change `PLAY_Strikeforce.bat`. Does not touch RPCS3, Downloads, or
Saud's game files. One `[TEST-SALEM]` window, and only the PID it started
is closed.

A ready-to-use pad replay kit for other agents is at
**`/workspace/sf-shared/replay/`** (README there has the one-command repro).

## What is here

| piece | status (27-Nov 2026, Asia/Kuwait) |
|---|---|
| Teleport at guest `0x008D3800` (`lib/tp_tool.ps1`) | Works. Evidence: 17:25–17:26 test, X=6499.8 → 6799.8, position held, minimap changed. Y+5 on go, same as `TELEPORT_GO.bat`. |
| First-mission checkpoints | **Partial.** Only X=6499.8 is recorded. Y/Z unknown. Do not `goto` until `save-as` fills them. |
| God mode (`lib/godmode.ps1`, hook in `hooks/`) | **Not confirmed.** `hp_hunt` listed 7814 heap decrements; no player HP or knockdown address proven. `mode on` refuses to freeze unconfirmed words. Learn mode is ready for a tester-owned fight. Env hook `SF_GODMODE=1` writes nothing if the addr file is empty. Not shipped in the main launcher. Not compiled in this pass (Saud was playing; other agents were building). |
| Pad driver + movie guard | Usable. Never presses during `[sf-movie] PlayerStart`, or when the state is unsure. In-engine cutscenes may not log `[sf-movie]` — those steps stay no-pad. |
| Coverage (`lib/coverage.py`) | Parses `[hle-lr]` / `[hle-lrc]`, stubs, `[sf-movie]`, PAD_FILE. Table + new-since-last-run. Movie v5 (18:09) does **not** contain `SF_HLE_LRLOG`; a future `1786_autotest` exe should merge that log-only hook (see `hooks/BUILD_NOTES.md`). |
| Runner `tester.ps1` | Waits until: no `MyGameRecomp` for 5 continuous minutes, `sfauto\gfx_runs_DONE.txt` exists, no SFRACE window. Own pad file and `state_autotest`. Closes only its own PID. `-DryRun` exercises the route without launching. |

## Commands (on the PC, after the idle gates)

```
powershell -NoProfile -ExecutionPolicy Bypass -File sfauto\autotester\tester.ps1
```

Replay only (game already running with `PAD_FILE=sfauto\autotester\pad.txt` and `SF_MOVIE_LOG=1`):

```
powershell -NoProfile -ExecutionPolicy Bypass -File sfauto\autotester\replay.ps1 -Seq sfauto\autotester\sequences\boot_to_start.padseq -Log play_logs\<run>_stderr.log
```

Same command and files: `/workspace/sf-shared/replay/README.md`.

Teleport / godmode (tester-owned window only; refuses a title containing `Saud plays`):

```
.\lib\tp_tool.ps1 -mode read
.\lib\tp_tool.ps1 -mode save
.\lib\tp_tool.ps1 -mode go
.\lib\godmode.ps1 -mode status
.\lib\godmode.ps1 -mode learn -Seconds 30
```

Screenshots: `lib/shot.ps1` (PrintWindow, no focus steal). Arabic red-box labels: `lib/annotate.py` (arabic_reshaper + bidi) on the box, from `reports/run_*/annotations_pending.json`.

## Self-test (box, no game)

```
python3 /workspace/sf-autotester/selftest/run_selftest.py
python3 /workspace/sf-shared/replay/selftest_padseq.py
/workspace/tools/pwsh/pwsh -NoProfile -File /workspace/sf-autotester/selftest/run_pwsh_dryrun.ps1
```

## NPC bot (added 2026-11-27 19:19 Asia/Kuwait, beta tester)

New files only; existing scripts were not changed:

- `lib/npc_bot.py` — tactics brain (hard movie gate, reflex, Ollama `qwen3:14b` at `http://127.0.0.1:11434`, pad.txt writer). Design: `/workspace/sf-beta/PLAN.md` and `npc_bot_design.md`.
- `lib/npc_bot.ps1` — PC host (reads proven XYZ at `0x008D3800`, tails stderr, calls the brain). Test-copy `[TEST-SALEM]` window only.

Box self-test (no game): `python3 /workspace/sf-autotester/lib/npc_bot.py --selftest`

Not tested on the game or a real Ollama host from the box. Salem runs it on the test copy after idle gates; see `/workspace/sf-beta/run_spec_for_salem.md`.

Mission mode (2026-11-27 19:46 Asia/Kuwait): `--mission M1` / `-Mission M1` loads `/workspace/sf-beta/missions.json`. See PLAN §2.8. Self-test covers mission load, goal, timeout, and fail paths.
