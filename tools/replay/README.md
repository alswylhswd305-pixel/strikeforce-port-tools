# Strikeforce pad replay (test copy only)

Closed-loop `PAD_FILE` driver plus a one-command replay entry point.
Built for the play-tester; the physicist and math researcher can put a
first-divergence finder on top of it.

Canonical sources live in `/workspace/sf-autotester/`. This folder is a
stable copy of the replay pieces only.

## One command: replay one repro

The game must already be running on the test copy with:

```
PAD_FILE=<TEST_COPY>\sfauto\autotester\pad.txt
SF_MOVIE_LOG=1
```

Window title must contain `[TEST-SALEM]`. Do not point `PAD_FILE` at
`sfauto\ringwatch_work\pad.txt` (that file is reserved for Saud's own play).

From the test-copy folder, or any copy of these scripts on the PC:

```
powershell -NoProfile -ExecutionPolicy Bypass -File sfauto\autotester\replay.ps1 -Seq sfauto\autotester\sequences\boot_to_start.padseq -Log <TEST_COPY>\play_logs\<run>_stderr.log
```

Dry run (parses the sequence, writes events, does not touch the pad file):

```
powershell -NoProfile -ExecutionPolicy Bypass -File sfauto\autotester\replay.ps1 -Seq sfauto\autotester\sequences\boot_to_start.padseq -Log <stderr.log> -DryRun
```

`replay.ps1` does not launch the game. Use `tester.ps1` for a full gated
launch. `-Launch` is refused unless the idle gates pass, and is not wired
to start a window from this script.

## What the driver does

- Writes one line to `PAD_FILE` (`mask hold [lx ly]`), then waits until the
  game empties the file (cellPad admission) and for `hold * 16.7 ms`.
- Button masks are the usual CELL_PAD bits (`START=0x0008`, `CROSS=0x4000`,
  …). `0x10000` is stick-only; optional `lx ly` (0–255, 128 = centre) use
  the test-copy `PAD_FILE` extension in `cellPad.c`.
- **Never presses during a movie.** It tails the stderr log for
  `[sf-movie] PlayerStart` / `PlayerStop` / `PlayerFinalize`. If a movie is
  active, or the state is unsure (no log, log unreadable, or no `[sf-movie]`
  lines yet), the press is skipped and recorded as `press-blocked`.
- In-engine story cutscenes often do **not** emit `[sf-movie]`. Treat those
  steps as no-pad waits unless you have a positive gameplay/menu check.
- Every event is appended as JSONL to `sfauto\autotester\pad_events.jsonl`
  (and printed). That stream is the hook for a first-divergence finder:
  compare timestamps, admitted presses, blocked presses, and wait outcomes
  across two runs.

## `.padseq` format

One command per line. `#` comments. `meta ...` is recorded, not executed.

| command | example | meaning |
|---|---|---|
| `wait_movie_end [sec]` | `wait_movie_end 180` | wait until a movie has started and then stopped; fail (do not press) on timeout |
| `wait_log PATTERN [sec]` | `wait_log PlayerStop 120` | wait until the stderr tail matches a regex |
| `wait_title PATTERN [sec]` | `wait_title PRESS 60` | needs `-ProcId`; window title regex |
| `sleep SEC` | `sleep 1.5` | wall-clock wait |
| `press NAME\|0xMASK [hold] [lx ly]` | `press START 8` | digital press, default hold 40 reports |
| `stick lx ly [hold]` | `stick 128 0 45` | left stick only (`0x10000`) |

Example sequences (copied here and in `/workspace/sf-autotester/sequences/`):

- `boot_to_start.padseq` — wait for the three opening movies, then START
- `menu_cross.padseq` — CROSS on a known menu only
- `combat_step.padseq` — short walk + square + triangle

## Files in this folder

| file | role |
|---|---|
| `replay.ps1` | one-command entry |
| `lib/pad_driver.ps1` | closed-loop driver |
| `lib/movie_guard.ps1` | `[sf-movie]` state machine |
| `lib/buttons.json` | name → mask |
| `sequences/*.padseq` | example repros |
| `selftest_padseq.py` | parser + guard unit tests (box, no game) |

Parser (box or any Python 3):

```
python3 /workspace/sf-shared/replay/selftest_padseq.py
```

## Safety

- Test copy only: `<TEST_COPY>`
- Never change `PLAY_Strikeforce.bat`
- Never touch RPCS3, Downloads, or Saud's game files
- One `[TEST-SALEM]` test window at a time; do not write another process's pad file
- Do not drive input while Saud is playing (pid / window "Saud plays")
