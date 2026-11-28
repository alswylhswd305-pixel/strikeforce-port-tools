# sfauto/tools -- workflow tools (test copy only)

All tools are read-only on the project sources. None installs anything (Python 3 + Pillow + numpy are already present).
Outputs go to `tools/sfauto/out/`.

| command | what it does | typical time |
|---|---|---|
| `python tools/sfauto/rdc_passes.py CAP.rdc` | every render pass: target, depth target, draw/vertex counts, pipelines, depth bound on which slots, slot-0 texture, viewport/scissor, shadow-copy freshness | ~3 s |
| `python tools/sfauto/rdc_export.py CAP.rdc --pixel x,y` | opens the capture in qrenderdoc (script mode): exports the shadow/depth map PNG, the main colour target PNG and pixel history (which draws wrote the pixel, with depth) | ~1-2 min |
| `python tools/sfauto/imgdiff.py OURS.png REF.png` | luminance diff vs an RPCS3 frame, red boxes, side-by-side, "ours brighter/darker" label per region; warns when the frames are not comparable | ~2 s |
| `python tools/sfauto/sf_coverage.py [--fast]` | runs the existing coverage tools and lists fake/missing system functions and RSX methods sorted by use | 1.5-3 min |
| `python tools/sfauto/progress.py [--no-coverage]` | regenerates `PROGRESS.md` from measured counts | 3 s (+ coverage) |
| `python tools/sfauto/sf_pipeline.py status\|backup\|build\|run\|capture\|compare\|all\|passes` | one command for backup -> (approved) build -> run test copy -> RenderDoc capture -> screenshot -> compare | run time |
| `python tools/sfauto/audit_handlers.py` | finds the HLE handler of every import the last run called and flags ones that look fake (heuristic) | ~10 s |
| `python tools/sfauto/lr_diff.py WORKING.log FAILING.log ...` | first call sites (SF_HLE_LRLOG) the working run reached that every failing run did not | ~10 s |
| `python tools/sfauto/callers.py 0x5C69B0` | static direct-caller tree of a recompiled function (function-pointer callers are not visible) | ~10 s |
| `python tools/sfauto/sf_voice_probe.py ...` | harness run whose play phase walks/attacks/talks (voice-line probe) | ~7 min |
| `python tools/sfauto/rdc_capture_burst.py` | the RenderDoc burst-capture harness used by `sf_pipeline.py capture` | ~5 min |

## Rules built in
- Test copy only; no deploy step. `build` needs `--approve-build` and backs up the current exe first.
- The game is never started while another MyGameRecomp.exe runs; only processes the tool started are closed.
- Names guessed from state (e.g. "shadow pass") are labelled ASSUMED in the output.

## Known limits
- `imgdiff.py` only means something when both frames show the same spot, camera and time of day.
- The RenderDoc capture key (F12) still lands 1-2 frames after the press: pick the frame you need from the
  `rdc_passes.py` output of the burst captures instead of trusting the frame number in the file name.
- `sf_coverage.py` classifications are automatic (ASSUMED); the published 267/346 and 376/798 used older rules.

All of these tools are dual-licensed: AGPL-3.0-or-later, or a commercial licence from Saud Hamad Alsuwailih.
