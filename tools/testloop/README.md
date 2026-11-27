# sfauto\testloop — Strikeforce one-click test loop

**Double-click `RUN_ALL_AR.bat`** (Arabic menu) or run `RUN_ALL_AR.bat all --build latest --route village`.
One entry point (`testloop.py`) does it all in one go:

1. **Tracker** — `status.json` + `STATUS_AR.md` / `STATUS_AR.html`: shadows 1780, Now Loading freeze, scarf, voices 1773,
   white ground, light shaft, faces. `state_ar` is set by people (`testloop.py status set <id> <text>`);
   `last_build / last_test / last_result / last_run` are written after every run (measured values only).
2. **Run** — waits until no other `MyGameRecomp` runs for 30 s (never kills another pid; Saud's own game also
   makes it wait unless `--alongside-saud`), copies the save state (`state_template` ← `sfauto\state_faces`, once)
   to `state_work`, launches ONE window titled `[TEST-SALEM] ps3recomp` with `PAD_NO_XINPUT=1`, pushes it to the back
   (`sfauto\winplace.ps1`), plays the route through `PAD_FILE`, refuses to press while a cellSail movie is open or
   the frame is letterboxed, takes PrintWindow shots (`sfauto\shot.ps1`, never CopyFromScreen), asks the exe for one
   frame's draw list through `FACES_CTL` (`list`, read-only diagnostic) at every checkpoint, samples the window every
   20 s for hang detection, then kills only its own pid.
3. **Compare** (`analyze.py`) — per checkpoint and per **section** (`sections.json`: shadows, sky, ground, characters,
   effects, UI): draws per section (fp/vp hashes, draw ranges), measured checks (passed/total), image match % against
   `golden\<route>\<checkpoint>.png` (only if it exists, else «ما ينقاس بعد»), the same against the previous run of
   the route (labelled, not a reference), heat-maps, frozen-frame and run-level hang flags, and a milestone-log diff with
   ps3recomp `tools\regress.py` (imported read-only) against `golden\<route>\milestones.txt`.
4. **Marks** (`mark.py`) — red/green/yellow boxes with Arabic + English labels, per-section crops,
   `annotations.json`.
5. **Report** (`report.py`) — `report.md` + `report.html` in Arabic with big pictures, then updates the tracker.

Run folder: `runs\<yyyymmdd-hhmmss>_<build>_<route>\` → `shots\` (raw png, `_marked.jpg`, `_sec_<section>.jpg`,
`_fcl.txt` draw list, heat-maps), `live\`, `stdout.log`, `stderr.log`, `env_used.txt`, `timeline.csv`, `run_log.txt`,
`run.json`, `analysis.json`, `annotations.json`, `milestones.txt`, `report.md`, `report.html`.

## Adding a route
Copy `routes\village.json` to `routes\<name>.json`. Steps run in order:
- `{"do":"wait","secs":N}`
- `{"do":"press","mask":"0x4000","n":40,"why":"..."}` — PAD_FILE mask (DIGITAL1: SELECT 0x01, L3 0x02, R3 0x04,
  START 0x08, UP 0x10, RIGHT 0x20, DOWN 0x40, LEFT 0x80; DIGITAL2 <<8: L2 0x0100, R2 0x0200, L1 0x0400, R1 0x0800,
  TRIANGLE 0x1000, CIRCLE 0x2000, CROSS 0x4000, SQUARE 0x8000). `n` = guest reports to hold. Every press is guarded
  (no press during a movie/letterbox) unless `"guard": false` — never turn it off around cutscenes.
- `{"do":"walk","lx":128,"ly":0,"n":240,"repeat":6,"until_draws_below":60}` — left stick only (mask 0x10000).
- `{"do":"wait_draws","min":150,"hold":10,"timeout":420}` / `{"do":"wait_draws_below","max":60,"timeout":20}` —
  uses the `draws:` number in the window title.
- `{"do":"shot","name":"cp","title_ar":"...","issues":["white_ground",...]}` — a checkpoint; `issues` decides which
  tracker rows the result updates.
Optional `annotations\<name>.json` adds extra boxes per checkpoint. Section rules/checks live in `sections.json`.

## Golden (reference) images
None yet. `testloop.py promote <run folder>` copies a run's shots to `golden\<route>\` — only after Saud says so.
RPCS3 references (same checkpoint, same camera) need Saud's OK for an RPCS3 run; put them in as
`golden\<route>\<checkpoint>.png`.

## Self-contained
Everything is relative to this folder except the exe copies (`..\exe_copies`), `..\shot.ps1`, `..\winplace.ps1`,
the ELF path and dev_flash path (constants at the top of `testloop.py`). `report.html` / `STATUS_AR.html` are static
files with relative image links, so the folder could be hosted later — nothing is uploaded anywhere.

Third-party (MIT): see `third_party\SOURCES.md`.

## RPCS3 references (`reference\rpcs3\`)
`reference\import_rpcs3_existing.py` copies the RPCS3 shots taken earlier today (`sfauto\ref_rpcs3`, read-only source),
crops them to the game area and writes `manifest.json`. They are a different camera than our checkpoints, so they feed
the per-section **colour match with RPCS3 %** (HSV histogram intersection, 9×3×3 bins; calibration: two RPCS3 village shots score 86–99% against each other) and the "same box, ours vs
RPCS3" brightness/saturation/mean-colour lines, not a pixel match. Still missing (needs a new RPCS3 run while the PC is
free, because RPCS3 only takes keys when its window is in front): snow battlefield, fight → Now Loading, battle face
close-up. Add new ones to `manifest.json` (`routes`, `sections`).

## Reports
`reports\rpcs3_vs_port_functions.md` — functions the game calls in RPCS3 vs the port (from logs, read-only; paraphrase only).
