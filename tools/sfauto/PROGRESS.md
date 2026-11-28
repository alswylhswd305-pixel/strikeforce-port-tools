# PROGRESS (generated 2026-11-28 14:56 by sfauto/tools/progress.py)

Test copy only. Numbers are measured by tools, not estimated. Rule: no claim without a measurement or a file.

## Index

| measure | value | how it is counted |
|---|---|---|
| Game functions recompiled | **6444 / 6444 = 100.0%** | functions in out/EBOOT.functions.json that have a definition in port/recompiled (23659 definitions in total, 33 files; the extra ones are additional entry points) |
| System functions implemented | **269 / 346 = 77.7%** | auto-classified NIDs (published baseline: 267) |
| RSX methods the game uses that are handled | **91 / 105 = 86.7%** | methods the game wrote at least once (all 798 known methods: 414 handled = 51.9%) |
| Tracked issues closed | **2 / 9 = 22.2%** | progress_items.json |
| **Status index** | **71.7%** | plain average of the four ratios above; NOT a schedule |

- Game functions: 6444 / 6444 have a recompiled definition (your note said 6444/6444: matches).
Differences from the numbers in your status note (VERIFIED by the tools; the published baselines used older sources/rules):

- System functions: tool says 269 implemented of 346 (note says 268/346 = 77%).
- RSX: tool says 414 of 798 methods handled overall = 51.9% (note says ~80%; the 'used by the game' ratio above is the closer measure).

## System functions still fake or missing (used by the game, sorted by calls)

| NID | module | status | calls |
|---|---|---|---:|

Other stubs never called in the logs: 36 (status counts: {'missing': 36, 'stub': 36, 'implemented': 269, 'uncertain': 4, 'partial': 1}).

## Unresolved NIDs seen at runtime

- last run: 1  | union of the last 10 runs: 6

- 0x0D0C2F0C cellSailDescriptorSetEs
- 0x7EB8D6B5 cellSailSoundAdapterGetFrame
- 0xA8AFA7D4 sceNpBasicGetCustomInvitationEntryCount
- 0xC044FAB1 cellSailDescriptorOpen
- 0xEEC22809 cellSailSoundAdapterUpdateAvSync
- 0xF25F197D cellSailSoundAdapterGetFormat

## RSX methods used but not handled (top)

| method | name | class | writes | draws affected |
|---|---|---|---:|---:|
| 0x0A2C | NV4097_SET_VIEWPORT_OFFSET.w | stored-but-unused | 7122 | 0 |
| 0x0A3C | NV4097_SET_VIEWPORT_SCALE.w | stored-but-unused | 7122 | 0 |
| 0x1EF8 | NV4097_SET_TRANSFORM_TIMEOUT | unhandled | 3559 | 0 |
| 0x020C | NV4097_SET_SURFACE_PITCH_A | stored-but-unused | 3535 | 0 |
| 0x021C | NV4097_SET_SURFACE_PITCH_B | stored-but-unused | 3535 | 0 |
| 0x022C | NV4097_SET_SURFACE_PITCH_Z | stored-but-unused | 3535 | 0 |

## Issues

| id | title | status | verified | next step |
|---|---|---|---|---|
| shadows-static | Static world meshes (well, buildings) cast no shadow | investigating | 2026-11-28 | RPCS3 RenderDoc capture of the same village frame: does its shadow pass contain the well? |
| poly-offset | NV4097_SET_POLY_OFFSET_FILL_ENABLE not handled (depth bias for the shadow pass) | open | 2026-11-28 | Cheap test: log the poly offset factor/units the game sets before the shadow pass. |
| voice | Character voices: Voice.bin never opened | investigating | 2026-11-28 | Needs a rebuild (approval): env-gated entry trace on func_005C73E4 / func_00013350 (print LR, r3..r6), then a run where Voice.bin opens vs one where it does not. |
| lwcond-real | lwcond: real waits for every cond (SF_LWCOND=2 default) | proposed | 2026-11-28 | User approval to apply and rebuild. |
| stage3 | Stage 3 state | unknown | - | Run to stage 3 and screenshot. |
| lighting | Lighting differences vs RPCS3 | open | - | imgdiff against same-camera RPCS3 frames. |
| pacing | Frame pacing | open | - | Log frame times over a 60 s village run. |
| non-real-fn | cellSail and sceNp functions the game calls: audit | done | 2026-11-28 | None for cellSail/sceNp. Next real-gameplay items: Voice.bin trigger, static shadows. |
| coverage-false-positive | Static coverage scan under-counts tagged handlers | done | 2026-11-28 | Keep stubhit_table.tsv from each run; add a check for handlers that return 0 without writing outputs. |

### Evidence

- **shadows-static**: Shadow depth map of captures frame9676/frame12230 holds only character silhouettes (697 / 1524 depth-only draws, 6 pipelines). Port drops almost no draws (upload_empty ~0.4%). Unit 0 of the shadow-caster FPs is a normal DXT5 diffuse (correct). RPCS3 band under the well has a different direction from the player shadow, so it may be a separate decal.
- **poly-offset**: rsx_coverage: game writes it once, no handler; raster state in capture shows depthBias=0. Effect on shadows: UNKNOWN, untested.
- **voice**: Hand-played runs (sys1804 04:22 "saud_0438", b1805 12:28) open Voice.bin right after spawn, then the main thread signals the IMS driver (cond 0x11E54CC0 by tid 1 at 0x208D0) which signals the At3 decoder (0x11E54F50 by tid 20): threads 18/19/20 ARE signalled there. Automated runs (walk/attack/talk probe 14:47, village runs) never open it. lr_diff.py: of 748 call sites tid 1 reaches in the working run, 729 are reached by every failing run and exactly 19 are not: all are lwmutex lock/unlock inside the Ksl IMS objects 0x11E54D18/0x11E54D60/0x11E54CC8 (func_000136E0, func_000140B4, func_0002116C, func_00013350). func_00013350 is called by func_005C69B0 <- func_005C73E4, a vtable thunk (no direct caller). Cause UNKNOWN: some game state/event decides to make that virtual call. Not an lwcond problem (same with SF_LWCOND 1 and 2). Probe presses (SQUARE/CROSS/CIRCLE/walk) in the village did not trigger it.
- **lwcond-real**: Test runs (130 s and a full title->village run) clean: no stall, poll_wait=0, signal_all 1928/s -> 0/s. Patch lwcond_default2_PROPOSED.patch is NOT applied.
- **stage3**: Not run by this workflow. Needs a fresh screenshot before any claim.
- **lighting**: No measurement yet.
- **pacing**: No measurement yet.
- **non-real-fn**: Backup first: sfauto/backups/1807trace_20261128-144231 (exe) and src_audit_20261128-144231 (sources). audit_handlers.py flagged 28 of the 157 imports the last run called; read each flagged handler that matters for gameplay: sceNpBasicGetCustomInvitationEntryCount validates the pointer and writes count=0 (strikeforce_sys1804.inc); cellSail Set*Adapter store the adapter pointer (strikeforce_movie.inc:730); GetFrame/GetFormat/UpdateAvSync have real logic and gating; cellSpursCreateTaskset and cellAtracCreateDecoderExt delegate to real implementations; heap functions return real pointers; cellGcmGetControlRegister returns the fixed control-register address. No defect found, no code changed. Not read in detail: cellKb* (keyboard, not needed for gameplay), _cellGcmSetFlipCommand (rendering works), _cellSpursAttributeInitialize.
- **coverage-false-positive**: sf_coverage.py now overrides the static classification with the runtime handler table: implemented 228 -> 269 of 346.

Next refresh: `python sfauto/tools/progress.py` (add `--fast` to skip the 100 MB logs; ~2 min otherwise).
