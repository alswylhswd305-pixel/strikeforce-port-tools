# gfx_bisect

Clean-room helper for Salem. Two jobs:

1. **Bisect** the draw index of one Strikeforce in-stage frame (ps3recomp D3D12
   backend) to find which draw is tied to a visual bug, then dump that draw's
   RSX state and write a markdown report.
2. **Diagnose** open graphics issues against an RPCS3 reference screenshot
   (or a cutscene capture): align the frames, score each issue with a numeric
   ours / ref / verdict, and write annotated images plus `report.md` /
   `report.html`.

**Draw skipping is a diagnostic only, never a fix** (playbook L4 / L8 / L12).
Do not land `DRAW_RANGE` / `DRAW_DUMP` in a keep build. After the culprit
index is known, fix the real state (viewport, clip, attributes, constants,
target) and change one thing per rebuild.

Every detector number is a **KNOWN measurement**, never a guessed cause, and
never a success rate.

This folder does not duplicate `../sfdiff.py`. Use `img_compare.py` here
for the older white/dark fractions; use `diagnose.py` for alignment,
per-issue detectors, batch reports, and cutscenes.

## Install (Saud's Windows 11 PC)

Copy this folder (or unzip `gfx_bisect.zip`) anywhere convenient, e.g.
`<TEST_COPY>\sfauto\gfx_bisect`.

Keep `fonts/NotoNaskhArabic-Regular.ttf` next to the scripts (SIL OFL 1.1;
license in `fonts/OFL.txt`). Arabic labels need those glyphs.

```
cd <TEST_COPY>\sfauto\gfx_bisect
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python gfx_bisect.py self-test
python test_gfx_bisect.py
python test_diagnose.py
```

Dependencies (all permissive except as noted):

| Package | License | Role |
|---|---|---|
| pillow | MIT-CMU | images, labels |
| numpy | BSD | metrics |
| mss | MIT | Windows screenshots (bisect) |
| psutil | BSD | process helper (bisect) |
| opencv-python-headless | Apache 2.0 | align, crop, FFT/Laplacian |
| arabic-reshaper | MIT | Arabic fallback shaping |
| python-bidi | **LGPL** | Arabic fallback bidi; **import the installed package, do not copy its source into this folder** |

Pillow's RAQM (HarfBuzz / FriBidi) is used for Arabic when the wheel includes
it (official Windows wheels usually do). If `PIL.features.check("raqm")` is
false, labels fall back to reshaper + python-bidi (joining is weaker). Do not
vendor python-bidi.

## Diagnose one pair (ours vs RPCS3)

```
python gfx_bisect.py diagnose path\to\ours.jpg path\to\ref.png --out diagnose_out
python diagnose.py compare path\to\ours.jpg path\to\ref.png --out diagnose_out
```

Optional: `--photo auto|yes|no` (default `auto`), `--crop-ours x0,y0,x1,y1`,
`--w 1280 --h 720`. Phone / TV photos are EXIF-rotated, then the game window
is perspective-cropped (Canny quad, or the largest bright `minAreaRect` if
the edges are soft) and the title / taskbar is trimmed.

Output in `--out`:

- `annotated.png` — ours, red boxes, Arabic labels, bilingual caption
- `side_by_side.png` — ours | RPCS3 | heatmap
- `heatmap.png`
- `result.json` / `report.md` / `report.html`

## Batch folder of pairs

`pairs.json` (see `example_pairs.json` / `testdata/box_pairs.json`):

```
{
  "pairs": [
    {"name": "p88_vs_rpcs3", "ours": "p88.jpg", "ref": "ref.png", "photo": "no"},
    {"name": "tv_photo", "ours": "tv.jpg", "ref": "ref.png", "photo": "yes"}
  ]
}
```

Or a folder with `ours/` + `ref/` and matching filenames, or
`name.ours.png` + `name.ref.png`.

```
python gfx_bisect.py batch --pairs pairs.json --out diagnose_batch
python diagnose.py batch --pairs pairs.json --out diagnose_batch
```

Writes `diagnose_batch/report.md`, `report.html`, `results.json`, and
`pairs/<nn>_<name>/annotated.png`.

## Cutscene / frame sequence

Sync two videos or frame folders on scene cuts and frame similarity, then
run the same detectors on matched frames.

```
python gfx_bisect.py cutscene --ours port_capture.mp4 --ref rpcs3_capture.mp4 --out diagnose_cutscene
python diagnose.py cutscene --ours frames_ours --ref frames_ref --out diagnose_cutscene --every 2
```

`--every N` diagnoses every Nth ours frame at the sync stage; `--max-frames`
caps how many frames are read. Output: `timeline.csv`, worst-frame
`annotated.png` under `frames/`, plus `report.md` / `report.html`.

## Detectors (KNOWN measurements)

Each row is **ours / ref / verdict**. Thresholds are documented in
`diagnose.py` (`THRESH`); they classify the number, not the cause.

| Key | Arabic label | What is measured |
|---|---|---|
| `shadow_acne` | حبوب الظل | high-frequency (FFT + Laplacian) energy on lit tiles, ours/ref ratio |
| `dark_roofs` | أسطح داكنة | mean luma of the darkest named roof/building region, ours/ref ratio |
| `haze` | ضباب أو غشاوة | far-band contrast vs near-band (missing or excess veil) |
| `faces` | الوجوه | dark-hole fraction, eye-band variance, (B−R) hue; auto skin-tone boxes on the ref, or `face_boxes` in the pair config |
| `face_dark` / `face_eyes` / `face_blue` | وجه أسود / عيون ناقصة / زرقة الوجه | the three face scores, usable as a bisect metric |
| `white_ground` | أرض بيضاء | fraction of ground pixels with luma ≥ 0.85, ours − ref |

If alignment is only a resize (ORB/ECC rejected), face boxes from the
reference are **not** projected onto ours. The face row is marked
`قياس بلا تطابق للكاميرا` / unmatched, and the bisect score stays 0.
A close-up of a face versus a full in-stage ref is this case — it is not
a same-place comparison.

Alignment is automatic (ORB affine, then ECC). Wild warps are rejected.
Do not hand-tune a matrix.

## Bisect (fully automatic)

Default mode never asks y/n. A screenshot metric decides "artefact present?",
then one more launch dumps the culprit draw and writes `culprit_report.md`.

The oracle `metric` may be any detector key above, or the older
`mae` / `brightness` / `histogram` / `white_frac` / `dark_frac`.

1. Add the two snippets in `diagnostic_snippets.c` to
   `libs/video/rsx_d3d12_backend.c` and rebuild the diagnostic exe.
   **`DRAW_RANGE` and `DRAW_DUMP` do not exist in the port yet** (verified
   against the box study copy of ps3recomp master `e85647a`, 2026-11-26).
   Closest knob: `DRAW_LIMIT=<N>` at `rsx_d3d12_backend.c:4775-4781`.
2. Copy `example_config.json`, set `PAD_SCRIPT` to the same script that
   already reaches Lou Sang Village, and point `oracle.reference` at the
   RPCS3 in-stage shot (`sfauto\ref_rpcs3\ref_instage_start_130501.png`).
3. Set `oracle.metric` to the issue you are chasing, for example
   `"white_ground"` or `"shadow_acne"`.
4. Run:

```
python gfx_bisect.py auto --config <TEST_COPY>\sfauto\gfx_bisect\example_config.json
```

`python gfx_bisect.py --config cfg.json` is the same as `auto`.

Test folder (from `sfauto`): `<TEST_COPY>`.
The exe name and env live in the config (`port\bld\MyGameRecomp.exe` plus
`PS3_VFS_ROOT` / `PS3_HDD0_ROOT` / `PS3_DEV_FLASH` / `PAD_SCRIPT`). Leave
them as config; do not hard-code a different exe in the script.

Optional:

```
python gfx_bisect.py auto --config cfg.json --draw-lo 0 --draw-hi 843 --parallel 2
python gfx_bisect.py auto --config cfg.json --resume
python gfx_bisect.py interactive --config cfg.json
python gfx_bisect.py report --log dump\run.log --rpcs3 rpcs3_values.json --out culprit_report.md
python gfx_bisect.py self-test
```

`--parallel K` runs K range buckets at once, each in its own folder with
cloned `PS3_HDD0_ROOT` / `HDD1` / `GAMEDATA` (L10). Stage boot is ~70 s
after the PRESS START idle was cut; default `wait_secs` is 160. Time one
cycle before quoting a rate.

## Pick a region (older img_compare path)

`img_compare.py` resizes both shots to the same size (default 1280x720),
writes `side_by_side.png`, `heatmap.png`, and `regions_overlay.png` (labelled
boxes). Open the overlay and adjust fractions in the config until the box
sits on the bug:

| Bug | Config region | What to look at |
|---|---|---|
| Giant wide shape above the character | `tent` (default) | `mae` vs the RPCS3 ref, or `brightness` |
| White ground | `ground` | `white_frac` (fraction of pixels with luma >= 0.85) |
| Dark buildings | `buildings_left` / `buildings_right` | `dark_frac` (luma <= 0.18) |

```
python img_compare.py ours.jpg ref.png --out compare_out --w 1280 --h 720
python img_compare.py ours.jpg ref.png --out compare_out --crop-ours 0,32,1280,680
python img_compare.py --split-stack cmp_ref_vs_p88.jpg --out compare_out
```

Window captures that include the title bar or the taskbar should set
`screenshot.crop` / `oracle.crop_ours` to the client rectangle
(`x0,y0,x1,y1`). If window grab fails, set `screenshot.dump_glob` to a
file the game already dumps (for example a `CELLMARK_DUMP` path).

Oracle keys (`example_config.json` → `oracle`):

- `metric`: `mae` | `brightness` | `histogram` | `white_frac` | `dark_frac`
  | `shadow_acne` | `dark_roofs` | `haze` | `faces` | `face_dark` |
  `face_eyes` | `face_blue` | `white_ground`
- `threshold`: artefact present when the metric is above this (`artifact_if:
  "above"`, the default vs an RPCS3 ref). Use `"close_to_bad"` / `"below"`
  when comparing to a known-bad shot.
- `region`: one of the names in `regions` (fractions `x0,y0,x1,y1` in 0..1,
  or pixel boxes). Used by the older img_compare metrics.

A first **baseline** run uses the full `draw_lo..draw_hi` range. If the
oracle does not see the artefact, the tool stops and tells you to retune
the region, crop, or `PAD_SCRIPT` — it will not bisect a clean picture.

## How to read the bisect results

- `steps.csv` / `state.json` — every launch, the range, the metric, the
  screenshot path. Worst case is `ceil(log2 N)` range runs plus the
  baseline and the dump (N = 843 → 10 range runs).
- The last `DRAW_RANGE=a-a` (or `lo == hi` in `state.json`) is the culprit
  **index**, not a fix. A missing draw (white clear showing through) and an
  extra bad draw (the tent) both show up; read the dump before proposing a
  patch.
- `dump_draw_<N>/run.log` — `[DRAWDUP]` block for that index.
- `culprit_report.md` — viewport scale **0x0A30** / offset **0x0A20**, clip
  range, vertex attribute type/stride/offset (type 7 = UB256, 6 = CMP),
  fragment program id, render target, and transform constants c0–c15, with
  an RPCS3 column. Fill `example_rpcs3_values.json` from the RSX capture of
  the same camera and pass `--rpcs3-values` (or re-run `report`); mismatches
  are marked **MISMATCH**.

Existing knobs `VP_ATTRS`, `VTX_DUMP`, and `VP_MVP` are turned on during
the dump launch as a fallback, but they are capped or deduped and do not
replace `DRAW_DUMP`. If the report says "no `[DRAWDUP]` block", the snippet
is not in the exe.

## Self-test (no game, works on the box)

```
python gfx_bisect.py self-test
python test_gfx_bisect.py
python test_diagnose.py
```
