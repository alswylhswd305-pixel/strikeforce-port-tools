# Strikeforce faces and shading after the ARL fix: graphics advisor hypotheses #2 (27 Nov 2026)

Rules: box only, no messages, no builds, no RPCS3 code (RPCS3 behaviour is described in my own words with file:line), no percentages.
Labels: KNOWN = measured or read in source/dump. ASSUMED = inference. VERIFY = needs a test.
Measurements: /workspace/faces/diag2611/ (gfx_bisect `diagnose.py batch`, report in out/report.md; per-box script meas.py → meas_bs_1784.json, boxes.jpg).

## 1. Fixed vs left, per face (measured)

| Bug | Image (build) | RPCS3 ref | Camera match | Result |
|---|---|---|---|---|
| #8 Zhao Yun scarf/head | MARKED_1 (1760 ARL), MARKED_1784 | ref_instage_start_130501 | **NOT matched**: same village spot, but the RPCS3 "City" dialog covers him (ECC 0.42) | KNOWN fixed: the scarf sheet is gone and the head sits on the body. LEFT: in 1784 the eye-band contrast is 0.0080 vs 0.0198 in the ref, but **not comparable** (different frame). Eyes present or not: VERIFY with a matched close-up |
| #5 merchant | pair_merchant (1760) | none (ref_midstage is another place) | **NOT matched** | KNOWN fixed by eye: the body and robe are no longer exploded. Face dark-hole 0.26 on our side only: no reference, so no verdict |
| #4 guard/soldier | pair_soldier_head (1760) | none | **NOT matched** (and no RPCS3 close-up exists) | Helmet and body are KNOWN fixed. **The face is still a black oval with only the chin lit**, which contradicts the "face intact" label in MARKED_3. Whether that is a visor in the real game: VERIFY with RPCS3 |
| #9 blue tint | blacksmith (1784) | testloop_sbs/village_blacksmith.png | Camera matched (ORB 371, ECC 0.89); **pose differs** (idle anim) | KNOWN: no blue shift. Blue−red is −0.13 ours vs −0.11 ref on the face box, and −0.27/−0.24 auto. Not reproduced here |
| Blacksmith face/body | 1784 vs ref | same | matched camera, pose differs | Face box luma 63.5 vs 63.3 (box partly on hair, pose-dependent). Earlier 1784 annotation: 69.7 vs 94.4. Jacket 56.5 vs 119.1 (×0.47) |

The 1760 AFTER shots (white ground, pre-cull) align badly against every ref (ECC 0.15-0.29). Use them only as before/after evidence, not as RPCS3 measurements.

**Shading on the matched blacksmith pair (1784 vs RPCS3), KNOWN:**

| Surface | Port luma | RPCS3 luma | Ratio R/G/B |
|---|---|---|---|
| Thatch roof | 78.6 | 130.9 | 0.60 / 0.60 / 0.65 |
| Stone sign | 56.5 | 104.3 | 0.53 / 0.54 / 0.61 |
| Noticeboard | 62.0 | 101.1 | 0.59 / 0.61 / 0.71 |
| Shadowed back wall | 40.6 | 45.0 | 0.9 |
| **Lit ground** | 120.1 | 117.8 | 1.0 |
| Sky | 189 | 191 | 1.0 |

The tool's dark_roofs reading is ×0.68 and haze ×0.93 (close). Shadow acne is ×1.12 (close).

So:
- KNOWN: the lit-surface loss is **per-material, not global**. The ground and sky match while props and buildings are about half as bright.
- ASSUMED: the loss is a roughly uniform multiply, a little smaller in blue, so a warm (sun) term is missing or scaled. Ambient survives.

## 2. H1-H7 re-ranked (post-ARL)

1. **H1, stale baked FP constants (PSO keyed on code hash only).** Promoted to the top for the remaining shading problem.
   - KNOWN: the hash skips constants (P rsx_fp_decompiler.c L1753-1768). The constants are baked as literals (P backend L2450).
   - KNOWN: identical code with different literals exists (0x0E9FF381/0x0E9FE401; blur 1/322 vs 1/162).
   - Per-material darkening with the ground correct is the expected look. ASSUMED.
   - The old FP_CONSTBUF=0 negative was taken before the cull fix, so it is invalid. VERIFY on 1786.
2. **Lighting/shadow term (H3 polygon offset plus the shadow compare).** Lowered as the main cause.
   - KNOWN (1780, pre-cull): forcing the shadow result to 1 moved the roof only 63.5→71.3 against about 122 needed.
   - KNOWN: acne is close to the ref.
   - The missing 0x0A68/0x0A78/0x0A7C decode is still a real gap (RPCS3 decodes them, gcm_enums.h L642-649, and applies them, VK/VKDraw.cpp L215-236).
   - Expected to show as acne or edge peter-panning, not ×0.55. ASSUMED.
3. **H2 + H6, texture formats, enable bit, gamma/expand.** Middle.
   - A missing sRGB/gamma would not be a near-uniform multiply. ASSUMED.
   - Format 0x90-0x93 was fixed in 1780.
   - Still VERIFY with TEXFMT_ALL/TEX_BINDDBG on the prop draws.
4. **H5, VP constants ≥468 / mid-draw upload.** Middle.
   - Light colour/direction may live in VP constants. Wrong values would also give per-material darkening.
   - VERIFY with `TCONST_DBG=1` rows on a prop draw vs a ground draw.
5. **H4, stride-0.** Low. KNOWN ruled out for the main-pass draws dumped.
6. **H7, h/r aliasing.** Low. No evidence.
7. The "geometry" part of the old H5 (skinning) is **largely explained by ARL**. KNOWN visually for #8 and #5, and for #4's body.

## 3. Does ARL explain other symptoms?

- **KNOWN, from a dump of the pre-fix build:** /workspace/faces/faces_vp_D5208C20.hlsl (skin VP, draw 453 era) has L243/L250 `a0.xyzw = ...` but L244/L247/L291-300/L338 read `vp_c[285 + a1.*]`.
  - a1 is never written, so those bones read constant row 285 (the first palette entry). That is exactly the stretched-sheet signature.
  - Master's bug: rsx_vp_decompiler.c L455-463 picks the destination from the read selector (D0 bit 24).
  - RPCS3 sends ARL to the dst_tmp register (VertexProgramDecompiler.cpp L42-46, L627) and reads through addr_reg_sel_1 (L337-341, indexed fetch L148).
- **Shadow pass:** fcl1.txt has 515 draws with VP 0xD54F73A6 plus 6 with 0xDB176E03 (rt=0, z=0x3A0000).
  - If these skin, the pre-ARL character shadows were wrong, and the fix should also have corrected character shadow shapes. VERIFY: `VP_DUMP` for D54F73A6 and grep for `int4 _a`.
  - Static-geometry shadows are unaffected. ASSUMED.
- **Lit props:** the main VPs 0x3F083BFF (330 draws) and 0x6A46C9BA (265) have no dump on the box.
  - Static props rarely index constants, so ARL is unlikely to explain the ×0.55. ASSUMED. VERIFY with the same grep.
  - If they do index light arrays through the other a-register, the ARL fix already changed them, and 1786 vs 1784 would show it.
- **The cloth SPU task running normally:** this was reported by the physics agent and is not verified here. ASSUMED.

## 4. Next tests (env-only first, one change per run: playbook L12)

All on 1786_movie_v5, blacksmith tour stop plus the four face spots below.
- **Run A (env only):** `FP_CONSTBUF=0`. If the roof, sign and noticeboard move toward ×1.0 while the ground stays, H1 is confirmed.
  - Root fix: buffered FP constants (`rsx_fp_decompile_buffered_ex`, P L1463), a code change that needs Saud's approval.
  - The env flag is a diagnosis only (L4).
- **Run B (env only):**
  - `TEXFMT_ALL=1 TEX_BINDDBG=400`: list the t0-t7 formats for the prop draws vs the ground.
  - `DRAW_LIST`: list the full-screen passes (bloom/blur/tone), since haze is ×0.63 on the partly matched village pair and the blur FPs share a PSO under H1.
- **Run C (env only):** `TCONST_DBG=1 TCONST_MAX=4000` on one frame. Compare the prop vs ground VP constant rows, looking at light colour/dir and rows ≥468.
- **Run D (env only):** `VP_DUMP` for 0xD54F73A6, 0x3F083BFF and 0x6A46C9BA, to check ARL use (section 3).
- **Census (CODE CHANGE, Saud approves first):** the unhandled-method counter from tool-ideas/gfx.md idea 1.
  - A static handled-method table plus a counter in rsx_process_method behind an env var, logging only.
  - Do it after Run A. It shows whether 0x0A68/0x0A78/0x0A7C, fog (0x1D78…) or others are written per frame.
- **Not needed now:** draw skipping, except as a bisect if Run A is negative.

## 5. Exact same-spot captures needed (1786_movie_v5 and RPCS3, both 1280×720 client area, no window chrome, HUD on)

1. **Blacksmith tour stop**, the same as village_blacksmith.png. Take 3 shots about 1 s apart on each side so the idle pose can be matched.
   - Port: baseline, Run A, Run B.
2. **Gatekeeper/Noticeboard soldier (#4)**, a frontal close-up at the same tour stop, with the camera not rotated. The RPCS3 shot is mandatory: it settles visor vs black face.
3. **Merchant "Exchange" stop (#5)**, the same framing as after_merchant_full.
4. **Zhao Yun face (#8)** at the village start after the "City" dialog is dismissed (RPCS3 ref_instage_start has it on screen).
   - Use the same camera reset (no stick input), then a close zoom if available.
5. **The blue-tint case (#9)** at the spot where Saud saw it. It is not reproduced on the blacksmith.
6. **Village start wide**, with no dialog, for haze/bloom and the ground.

For each port shot, also save the FACES_CTL list / FCL log of the same frame, so every box can be mapped to a draw number.

> Update 2026-11-27 18:48: #4 closed. Saud says the soldier's face looks normal in the current build (relayed by عالم الفيزياء); the black-oval note above came from older captures.
