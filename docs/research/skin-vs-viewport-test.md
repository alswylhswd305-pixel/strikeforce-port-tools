# Guard NPC face flat/detached: skinning/bone constants vs viewport/clip path. Cheap tests
Written 2026-11-26 ~16:40 (UTC+3) by the math researcher, for Salem and the graphics advisor. Advice only; nothing run, Saud's PC not touched.
Builds on /workspace/sf-shared/math-spec-render-1.md (§1 viewport, §4 vertex fetch, §5 UB/UB256, §7 capture plan).
Pins: R = RPCS3 0ca5eb0 (paths under rpcs3/Emu/RSX/); P = ps3recomp master e85647a (libs/video/). Salem's tree may differ: every "P does X" is master, VERIFY in his tree.
Labels: KNOWN (cited) / ASSUMED / VERIFY. Numbers come from python3: /workspace/sf-shared/skin_vectors.py → skin_vectors_output.txt.

## 0. The two causes, and how they look
- (a) Skinning/bone path: wrong or stale VP constants (bone palette or the head/face world matrix), constants outside the writable range, constant writes landing at the wrong time, or bone indices/weights decoded wrongly.
- (b) Viewport/clip path: the identity x/y epilogue in P (spec §1.3) or a wrong z/clip range.
- Evaluating the idea (ASSUMED reasoning, built on KNOWN facts):
  - KNOWN: P's viewport handling is the same for every draw. It ignores VIEWPORT_SCALE/OFFSET x/y entirely (P rsx_d3d12_backend.c L3607-3615), so it is wrong only when the game's values differ from (w/2, ±h/2), and then it is wrong in the same way for every draw that uses those values.
  - So (b) moves or scales a whole draw, and all draws sharing the viewport, by one affine map. If the face is a separate draw with the same viewport registers as the body, (b) cannot move the face relative to the body. It could only do so if the face draw had its own viewport values, which test T1 shows directly.
  - A face that is detached or flattened on an otherwise correct body is therefore a per-draw or per-vertex difference. That points to (a): the face's own matrix/bone constants, their upload timing, or its bone-index attribute.
  - "Flat" fits all face vertices collapsing onto one bone (index decoded to 0) or onto a matrix with a zero row. ASSUMED; T2/T5 separate these.

## 1. Facts the tests rely on
- KNOWN registers (R gcm_enums.h L736-737): TRANSFORM_CONSTANT_LOAD 0x1EFC sets the start vec4 index. TRANSFORM_CONSTANT 0x1F00..0x1F7C is a 32-word window; word k goes to vec4 LOAD + k/4, lane k%4 (R NV47/HW/nv4097.cpp L22-37).
- KNOWN writable range (R NV47/HW/nv4097.h L213-214, "Only constants [0, 467] are writable. Hardware ignores writes beyond that"): RPCS3 drops writes at index ≥ 468 and trims partial ones (nv4097.cpp L24-36, L118-130), logging "Invalid transform register index".
- KNOWN read range (R): an indexed read is c[(a0 + imm) & 511] (Program/VertexProgramDecompiler.cpp L148), and any index ≥ 468 reads 0 (Program/GLSLSnippets/RSXProg/RSXVertexPrologue.glsl L103).
- KNOWN LOAD does not auto-advance in RPCS3: no code in set_transform_constant::impl increments it (nv4097.cpp L95-165). LOAD changes inside BEGIN/END are queued as a draw-parameter barrier (nv4097.cpp L634-637).
- KNOWN mid-draw constant writes: when a 0x1F00 write arrives inside BEGIN/END with a non-empty draw clause, RPCS3 defers it as a transform_constant_update_barrier, so the sub-draws before and after see different constants (nv4097.cpp L132-140).
- KNOWN ARL: RPCS3 converts with int(x), i.e. truncation toward zero (VertexProgramDecompiler.cpp L627). P uses floor (P rsx_vp_decompiler.c L455-460). They differ only for negative non-integer values.
- P at master (KNOWN):
  - stores 512 constants and accepts writes up to slot 511 (rsx_commands.h L168; rsx_commands.c L387-389). Writes to 468..511 are kept, where RPCS3 drops them;
  - indexed reads use (imm + a) & 511 with no ≥468 → 0 rule (rsx_vp_decompiler.c L96);
  - LOAD is a plain register (rsx_commands.c L478-484) with no auto-advance, which matches RPCS3;
  - constants are snapshotted per draw "at RECORD time" (rsx_d3d12_backend.c L71-75, L3574). VERIFY: whether a 0x1F00 write between two DRAW_INDEX_ARRAY chunks of one BEGIN/END gets its own snapshot (rsx_commands.c BEGIN_END L862-909).
- Bone indices (KNOWN, spec §5): UB256 (type 7) decodes to raw 0..255; UB (type 4) decodes to byte/255. Both match RPCS3 on P's legacy CPU fetch.
  - python: decoding k/255 in float32 and rescaling by 255, 765 or 1020 floors back to the exact integer for all 256 k. So float rounding in P's CPU decode cannot shift a bone index.
  - If a UB256 index were ever decoded /255, every index would collapse: bytes 1, 7, 30 → bone row 0 instead of 3, 21, 90 (with 3 vec4 per bone); byte 255 → 3 instead of 765. The whole skinned part would sit on bone 0.

## 2. Tests (one measurement each)
| # | Measurement (our build, per draw) | If (a) skin/bone | If (b) viewport/clip | Cost |
|---|---|---|---|---|
| T1 | 0x0A20-0x0A3C and SURFACE_CLIP 0x0200/0x0204 for draws 1136-1302 and the face draw | standard (w/2, ±h/2) and identical on face and body draws → viewport ruled out (spec §1.3: P = RPCS3 for standard values) | non-standard values, or the face draw's differ from the body's | one log line per draw |
| T2 | the constants the face VP reads (static c[n] list plus the indexed range), ours vs RPCS3 at the same draw | mismatch in a matrix or bone rows (zeros, the previous draw's matrix, a shifted block) | identical constants | dump only the needed rows |
| T3 | max constant slot written since the previous draw (LOAD + word/4), and the max index read (static max; for indexed reads, base + 3·max bone index + 2) | ≥ 468 on the face draw → P keeps data RPCS3 drops or reads as 0 (diverges); e.g. bone 10 at base c440 needs c470-c472 (python) | all < 468 | counters only |
| T4 | count of 0x1F00 writes and LOAD changes while in_begin_end = 1, per draw | > 0 on the face draw → per-sub-draw constants; RPCS3 honours the barrier, P's per-record snapshot may give a sub-draw the wrong matrix (VERIFY P) | 0 | one counter |
| T5 | the attribute feeding ARL (from the VP ucode: which v[n] reaches ARL), its FORMAT type/size/stride, and the decoded x of the first 16 vertices | UB256 shown as 0..1, or UB whose shader scale doesn't give integer rows; indices all 0; weights not summing to 1 | indices sane integers, weights ≈ 1 | VP_ATTRS dump |
| T6 | any negative a0 input (ARL source < 0) | truncation vs floor differ (minor) | n/a | rare; only if T5 is clean |
| T7 | one diagnostic run: on the face draw only, bind the RPCS3-captured constant rows (raw words, unmodified) | face snaps onto the head → (a) confirmed, constants are the cause | no change → not constants; go to T1/T5 | needs the T2 capture; diagnostic only, not a fix |

Reading the results:
- T1 standard and identical → (b) is excluded for this symptom.
- T2 mismatch plus T4 > 0 → upload timing.
- T2 mismatch plus T3 ≥ 468 → range rule.
- T2 match plus T5 bad → attribute decode.
- T2 match plus T5 good → vertex data itself (compare raw positions with RPCS3, spec §6 D).

## 3. Capture plan (NOT YET DONE)
Our build, one line per draw for draws 1136-1302 and the face draw (find the face draw with DRAW_LIMIT bisect):
```
draw=<k> vp_hash=<..> verts=<..> vp_scale=<4f> vp_offset=<4f> clip=<w,h> load_last=<n>
 const_written=[min..max] const_writes_in_begin_end=<n> load_changes_in_begin_end=<n>
 const_read_static_max=<n> indexed=<y/n> arl_src=v<n> arl_attr_fmt=type/size/stride/off
 bone_idx_first16=<decoded x> weights_first4=<..>
```
- RPCS3: RSX Capture (Alt+C, R rpcs3qt/shortcut_settings.cpp L87) of the same frame. Match the draw by VP/FP ucode and vertex count, and read the same registers, constant rows and attribute formats. Whether the capture viewer shows per-draw constants is VERIFY; if it doesn't, use a replay with logging.
- Compare raw hex words first (spec §7 rule). Apply nothing by hand.

## 4. What to check in our backend (one line each)
1. Log 0x0A20/0x0A30/0x0200/0x0204 per draw (T1).
2. Log min/max constant slot written per draw, and flag any slot ≥ 468 (rsx_commands.c L387-389) (T3).
3. Count 0x1F00/0x1EFC writes while in_begin_end (rsx_commands.c L862-909) and confirm each sub-draw gets its own constant snapshot (rsx_d3d12_backend.c L3574) (T4).
4. Add the RPCS3 range rule as a candidate fix: drop writes ≥ 468; indexed reads ≥ 468 return 0 (rsx_vp_decompiler.c L96). Keep it only if T3 shows the game crosses 467.
5. VP_ATTRS on the face draw for the ARL source attribute and the weights (T5).
