# Strikeforce in-stage gfx: (1) giant shape, (2) white ground, (3) dark buildings — advisor hypotheses #1
2026-11-26 ~15:20 (UTC+3). Advice only: nothing was run, no project files changed, Saud's PC not touched.
Source read: ps3recomp master e85647a (/workspace/ps3-research/ps3recomp, "P"). Salem's local tree is NOT on the box, so every "P does X" = master; VERIFY against his tree.
RPCS3 0ca5eb0 (/workspace/ps3-research/rpcs3src, "R"), read for behaviour only, nothing copied.
Labels: KNOWN (cited) / ASSUMED / VERIFY. Saud's TV photo path given by the parent does not exist on the box; I used p88/p90/p91/cap82_id/cmp_ref_vs_p88 instead.

## 0. Before anything: the FP_IDCOLOR "nothing changed" result is probably void
- KNOWN: FP_IDCOLOR (P rsx_d3d12_backend.c L2578-2603) only patches when it finds the string `_po.c0 = `. P's FP decompiler never emits that string: it emits `float4 _o = r[0]; return ...` or `_out.tN = ...` (P rsx_fp_decompiler.c L1296-1318). FP_TEX (L2616) and the two hooks at L2497/L2539 use the same lookup.
- KNOWN: p90 (no idcolor) and p91 (idcolor) look identical everywhere, ground and characters too, not just the shape. A working idcolor would have recoloured at least the characters.
- Test: count `[FPID] fp=` lines in the p91 log. 0 lines (or far fewer than the PSO count) = the test never ran, and "the shape comes from an unknown draw path" is unsupported. Fix the hook so it matches `float4 _o = ` / `_out.t0 = ` and rerun once. That run alone tells you which FP paints the shape, the ground and the buildings.

## 1. Giant wide shape (top priority)
What the screenshots show (KNOWN, p88/p90/p91/cap82_id vs RPCS3 cmp_ref_vs_p88 top):
- A huge flat sheet covers the top ~40% of the screen. It has a tan/orange edge, a grey-white interior with a specular sheen, a blue band on its lower edge, and a long pale-teal strip that runs diagonally from the character up to the top-right.
- In RPCS3, Zhao Yun has a pale-teal cloth hanging down his back, and blue trim on his skirt. In our port that hanging cloth is missing from his back. The colours of the sheet and the strip match his cloth parts.
- The shape follows the character/camera.
- ASSUMED reading: these are the character's cloth meshes (cape, tabs, ribbon) with wrong vertex positions, stretched out to far points.

Ranked hypotheses:

H1a. Bad cloth vertex positions from the SPU cloth job (KSG2PS3SPUCloth, image 375200614, unliftable, runs in the SPU interpreter). ASSUMED; it fits best.
Three ways this could happen:
- the job doesn't finish before the draw, so the buffer is stale, zero, or in bind pose (sync);
- the interpreter's float maths differs from the SPU: SPU single precision has no Inf/NaN/denormals and saturates instead, and frest/frsqest/fi are low-precision estimates, so an integrator can blow up;
- only part of the buffer is written: pinned vertices sit right and free vertices fly off to one point (which matches the long diagonal strip).
- Test (one run): bisect with DRAW_LIMIT=N (L4780; keeps the first N ops; DRAW_RANGE does not exist at master, VERIFY in Salem's tree). That finds the draw index or FP of the shape. Then run `VP_ATTRS=1 VP_ATTRS_FP=<its program>` plus `VP_ATTRS_DUMP=0:32` (L6592-6620) to get attr0 offset/type/stride and 32 raw positions.
  - If true: attr0 sits in main memory (offset bit 31 set), in the range the cloth task DMA-writes. Values include 0/NaN/huge, or a cluster all equal to one point, and they change or explode over frames.
  - If false: the positions are sane and close to the character's other vertices. Go to H1b or H1c.
- Root fix if true: correct SPU float semantics or the job/PPU sync in the interpreter (or make the image liftable). Not skipping the cloth draw.

H1b. Wrong transform for that draw: matrices, viewport, or the silent fallback projection.
- KNOWN: the shader epilogue uses identity x/y. VIEWPORT_SCALE/OFFSET (0x0A30/0x0A20) x/y are ignored. Only the z lane is used (P rsx_d3d12_backend.c L3606-3615). `d3d12_set_viewport` is a no-op, and the D3D viewport is the full RT.
- KNOWN: R builds the scale/offset from the viewport registers relative to the surface clip (R Core/RSXDrawCommands.cpp ~L594-616).
- KNOWN: P silently replaces c0-c15 with a fixed projection when those 16 constants are all zero and the VP reads c0-c3 (`[VPFB] fallback proj`, L3639-3660). That draws an object-space mesh locked to the screen, huge.
- Test 1 (free): grep the log for `[VPFB] fallback proj`.
  - If true: lines appear in-stage, and running with `VP_NOFIXPROJ=1` changes or removes the shape.
  - If false: no lines, and no change.
- Test 2 (Saud's idea, measurement only, no rescale):
  - In our port, for the shape's draw (found by the bisect in H1a), log once: viewport offset[0..3] and scale[0..3] (0x0A20/0x0A30), clip_min/clip_max, surface clip w/h, 0x1D78, and c0-c15 plus the VP's other used constants (`RSX_DBG_CB=<tex0>` prints the CB the shader really sees, L3593-3605; `VTX_DUMP=1` prints viewport and positions, L6891-6908).
  - In RPCS3, take an RSX capture (Alt+C) of the same spot. Open the same draw (same VP/FP ucode, same vertex count) and read the same registers and constants.
  - If true: scale/offset are not the full-surface w/2,h/2 values (so our identity x/y is wrong for this draw), or c0-c15 differ: zeros, stale, or a different matrix order.
  - If false: everything matches within float noise, so the transform isn't the cause. The bad input is the vertex data (H1a/H1c).

H1c. Vertex fetch differences on the legacy CPU path.
- KNOWN: P's legacy path never reads VERTEX_DATA_BASE_OFFSET 0x1738 or BASE_INDEX 0x173C. rsx_commands.c has no handler, and rsx_vertex_fetch.c L74 / read_guest_index L6857-6869 add no base.
- KNOWN: the shared engine does apply them (P rsx_dispatch.h L219-241), and so does R (RSXDrawCommands.cpp L188, rsx_utils.h L519).
- KNOWN: an enabled array with stride 0. P's fetch returns early at rsx_vertex_fetch.c L42 (`!a->enabled || a->stride == 0`) and uses the constant register (vertex_data4f, reset (0,0,0,1), rsx_commands.c L75). R treats stride 0 as "single_vertex": it reads one element from memory and uses it for every vertex (RSXDrawCommands.cpp L175-179; RSXThread.cpp L72-74).
  - Enabled means size>0 on both sides (P rsx_commands.c L344).
  - The frequency/divider logic (L54-63, rsx_vertex_formats.h L56-73) only runs for stride>0. Stride 0 never reaches it in P.
  - In R, stride 0 does not depend on frequency at all: it always reads element 0.
  - Fix shape (clean-room): for an enabled array with stride 0, read element 0 from memory with the normal type decode. Don't use vertex_data4f.
- Test (one log line): log any method write to 0x1738/0x173C with a non-zero value in-stage, and from VP_ATTRS any enabled attr with stride=0 on the shape's draw.
  - If true: non-zero base offset or index on the cloth or character draws, or a stride-0 attr feeding a position, blend weight or bone index.
  - If false: both stay 0 and there is no stride-0 attr. Remove H1c.
- Already matching R (KNOWN, P rsx_vertex_fetch.c vs R RSXVertexFetch.glsl L77-141):
  - UB256 (7) is unnormalised and UB (4) is /255;
  - CMP (6) is 11/11/10 with w=1;
  - SF is a big-endian half (P flushes denormals; tiny);
  - a missing w becomes 1.
  - Not suspects on the legacy path.

H1d. Near-plane geometry drawn because depth clip is off.
- KNOWN: the guest PSO is `pd = {0}` (P L2670), so DepthClipEnable is FALSE. 0x1D78 (ZMIN_MAX_CONTROL, reset = clip on) is never read on the legacy path.
- ASSUMED: something between the camera and the near plane, which RSX would cut, gets drawn with clamped depth over everything.
- Weaker here, because the shape carries the character's cloth colours.
- Test (one line, local build): set DepthClipEnable from 0x1D78 (clip = (v&0xF)!=0 && (v&0xF0)==0), and add it to the PSO key. Log the value.
  - If true: the shape shrinks or vanishes and the rest is unchanged.
  - If false: no change. Keep the change anyway as a correctness fix (it is the root behaviour), but it isn't this bug.

## 2. White ground (top priority)
What the screenshots show (KNOWN):
- The near and mid ground is flat white or very pale blue, with no texture detail and no character shadow (p88/p90/p91/cap82_id).
- In RPCS3 the same ground is textured brown/green dirt with a soft character shadow.
- The grass, the characters and the distant hills look right in colour.
- So the problem is one material class. Global exposure doesn't fit, because the characters look correct (ASSUMED).

Ranked hypotheses:

H2a. Fog input is wrong.
- KNOWN: P has no SET_FOG_MODE (0x08CC) or SET_FOG_PARAMS (0x08D0/0x08D4) handling (no match in rsx_commands.c or the backend). The FP's FOGC input is the raw VP o5.x replicated into xyzw (P rsx_vp_decompiler.c L695 `Out.fog = o[5].xxxx`; rsx_fp_decompiler.c L377).
- KNOWN: R feeds FOGC as (raw, factor, 0, 0). The factor in .y is computed from the fog mode and params (linear p1*x+p0-1, exp, exp2, abs variants) (R Program/GLSLSnippets/RSXProg/RSXFragmentPrologue.glsl L68-98, used at VK/VKFragmentProgram.cpp L540). Fog reset is mode 0x800 (R rsx_methods.cpp L261).
- ASSUMED effect: an FP that blends with fogc.y gets a distance-sized number instead of a 0..1 factor, so the lerp overshoots. Bright materials go to white, dark ones go darker. That could also explain (3).
- Test (one log line, at FP compile): print `[FOGFP] fp=0x..` when the HLSL contains `input.fog`. Also log 0x08CC/0x08D0/0x08D4 writes in-stage.
  - If true: the ground FP (and probably the building FP) reads input.fog, the character FPs don't, and the game writes a non-default fog mode/params.
  - If false: the ground FP doesn't read fog. Drop H2a.
- Root fix (clean-room): store the 3 registers, pass mode/p0/p1 in the FP cbuffer, build FOGC = (raw, factor, 0, 0) by the documented formulas, and add the fog mode to the PSO key.

H2b. Shadow-map sampling without the depth compare.
- KNOWN: the legacy backend compiles every FP with `rsx_fp_decompile(...)` (P L2450), i.e. no shadow descriptor and no gamma masks. The shadow-compare and texture-gamma support in rsx_fp_decompiler.c (L476+, L561-600) is never used on this path.
- ASSUMED: the ground is the main shadow receiver. A raw depth value, or a stale RT where the FP expects a 0/1 compare result, gives a constant term. That fits "no shadow at all".
- Test: TEXFMT_ALL=1 plus the H1a-style bisect on a ground draw. Does unit N bind a depth-format texture (z16/z24 fmt) or the shadow RT offset, with a compare func in TEXTURE_CONTROL0?
  - If true: yes, and DRAW_SKIP_TEX=<that offset> (diagnostic only) changes the ground brightness.
  - If false: no depth texture on the ground FP.

H2c. Wrong texture format or remap on a ground texture (lightmap/blend mask).
- KNOWN: unknown formats fall back to R8 (P rsx_texture_layout.h L42). A NULL SRV samples 0.
- ASSUMED: white needs something like remap→ONE or a ×2/×4 lightmap gone wrong.
- Test: `TEXFMT_ALL=1 REMAPDBG=1` on the ground draw.
  - If true: a ground texture shows a fallback format or a remap with ONE in the colour channels. `TEX_REMAP_ID=1` (identity) brings back texture detail.
  - If false: normal ARGB8/DXT with an identity-like remap.

H2d. Missing light/material constants: the inline FP constants or the VP lighting constants.
- ASSUMED. Test: `RSX_DBG_CB=<ground tex0>`, compared with the same draw in the RPCS3 capture (same method as H1b test 2).
  - If true: different or zero lighting constants. If false: they match.

## 3. Dark buildings (secondary)
- KNOWN screenshots: buildings and posts are dark grey and almost unlit. In RPCS3 they are warm brown with sunlight.
- Candidates, in order:
  1. The same fog/FOGC bug as H2a (dark materials overshoot downward). Check: does the building FP also appear in `[FOGFP]`?
  2. The 160x90 post/exposure target at 0x0B010000. Per render-bugs-round3 §3 (KNOWN, P L3758-3828): exact-offset slot, re-created from guest RAM when the size changes, SRV ignores the remap. Check: `RTT_DUMP` shows two sizes on 0x0B010000 in one frame.
  3. No texture sRGB/gamma decode on the legacy path (KNOWN, L2450 passes no gamma masks). Check: TEXTURE_ADDRESS gamma bits (20-23) set on the building textures (TEXFMT_ALL addr field).
  4. Stride-0 colour/normal attribute (H1c). Check: VP_ATTRS on a building draw.

## 4. Already tested or ruled out (don't redo)
Verified fixes, per the playbook and Salem's notes:
- depth-only clear presenting early;
- VB overflow handled with a mid-frame flush;
- depth surface at offset 0 / has_zeta;
- strip restart across 256-index chunks;
- alpha test wired (grass squares are gone in p91 vs p88; the remaining square tufts in cap82_id are an older build, VERIFY).

Disproved:
- subchannel-1/NV0039 colour mask (cmask 0x01010101 in-stage);
- vertex type 7 = CMP (it is UB256);
- 0x0A00-0x0A1C as viewport registers (they are HORIZONTAL/VERTICAL/etc.; viewport offset/scale are 0x0A20/0x0A30).

Tested but invalid:
- FP_IDCOLOR at master (§0).

Open from earlier rounds:
- depth clip / 0x1D78 (H1d);
- stride 0 (H1c);
- 160x90 target (3.2);
- Z16 clear decode (olive-world H5).
