# Strikeforce (BLUS30471) render math spec #1 — viewport, depth clip, fog, vertex fetch, UB256/CMP, stretch check
Written 2026-11-26 ~15:40 (UTC+3) by the math researcher for the graphics advisor (خبير الرسم). Clean-room: own words; RPCS3 cited by file:line only; no GPL code copied.
Nothing was run on Saud's PC and nothing was downloaded to it. All numbers below were computed with python3 on the box:
script `/workspace/sf-shared/math-spec-render-1/vectors.py`, full output `/workspace/sf-shared/math-spec-render-1/vectors-output.txt`.

Pins / sources
- R = RPCS3 0ca5eb0efe50ec4e8aa07892ab86d57842246eb4 (box clone /workspace/ps3-research/rpcs3src). Paths below are under rpcs3/Emu/RSX/.
- R7 = RPCS3 tag v0.0.7 (c4d99f93db05058b34f7be48bb800e96902e754e), a release tag that still had RPCS3's own D3D12 backend (the file was not found at v0.0.8) (fetched from raw.githubusercontent.com/RPCS3/rpcs3/v0.0.7/...). Used to show how RPCS3 itself mapped RSX to D3D12.
- P = ps3recomp master e85647a (box clone). Salem's tree may carry local patches: every "P does X" means master; VERIFY in his tree.
- MS = Microsoft Learn: D3D12_RASTERIZER_DESC page; "Coordinate Systems (Direct3D 10)"; Output-Merger page (fetched this turn).
Labels: KNOWN (source given) / ASSUMED (inference) / UNVERIFIED (needs a run, a capture, or a source I could not get). No percentages are claimed anywhere except plain pixel arithmetic.

---------------------------------------------------------------------
## 1. Viewport transform

### 1.1 Registers (KNOWN)
| Register | Address | Content | Source |
|---|---|---|---|
| SURFACE_CLIP_HORIZONTAL | 0x0200 | bits 0-15 origin x, bits 16-31 width | R gcm_enums.h L561; rsx_decode.h L160-185 |
| SURFACE_CLIP_VERTICAL | 0x0204 | bits 0-15 origin y, bits 16-31 height | R gcm_enums.h L562; rsx_decode.h L187+ |
| CLIP_MIN | 0x0394 | float bits (depth range min) | R gcm_enums.h L617; rsx_decode.h ~L1095-1114 |
| CLIP_MAX | 0x0398 | float bits (depth range max) | R gcm_enums.h L618; rsx_decode.h ~L1118-1137 |
| VIEWPORT_OFFSET | 0x0A20..0x0A2C | 4 floats x,y,z,w | R gcm_enums.h L640; rsx_methods.h L869-886 |
| VIEWPORT_SCALE | 0x0A30..0x0A3C | 4 floats x,y,z,w | R gcm_enums.h L641; rsx_methods.h L849-866 |
| SHADER_WINDOW | 0x1D88 | bits 0-11 height, bits 12-15 origin (0=top,1=bottom), bits 16-19 pixel centre (0=half,1=integer) | R gcm_enums.h L713, L1163-1166; rsx_decode.h L3117-3145 |
Not viewport: 0x0A00 VIEWPORT_HORIZONTAL, 0x0A04 VIEWPORT_VERTICAL, 0x0A0C POINT_CENTER_MODE, 0x0A1C ZCULL_SYNC (R gcm_enums.h L636-639).
Reset values in RPCS3 (KNOWN, R rsx_methods.cpp L472-481, L239): CLIP_MIN 0.0, CLIP_MAX 1.0 (0x3f800000); OFFSET = SCALE = (2048, 2048, 0.5, 0) (0x45000000 = 2048.0, 0x3f000000 = 0.5, checked with python); SHADER_WINDOW 0x1000 (origin bottom, height 0, half-pixel centre).

### 1.2 What RPCS3 does (KNOWN)
- The vertex program's position output is treated as homogeneous clip space (x,y,z,w), not as window coordinates. RPCS3 does not "undo" anything; it appends one affine step to the shader and then lets the host do the w-divide and the host viewport.
  - Appended step: position = position × scale_offset_mat (R GL/GLVertexProgram.cpp L293; VK/VKVertexProgram.cpp L500; R7 D3D12VertexProgramDecompiler.cpp L262 does the same with `mul`). The matrix rows are filled in R Core/RSXDrawCommands.cpp L595-618. In component form: x' = x·sx + w·ox, y' = y·sy + w·oy, z' = z·sz + w·oz, w' = w.
  - The RSX window-space viewport is folded into host-NDC terms relative to the surface clip size (R RSXDrawCommands.cpp L597-611):
    - sx = SCALE.x / (clip_w/2), ox = (OFFSET.x − clip_w/2) / (clip_w/2)
    - sy = SCALE.y / (clip_h/2), oy = (OFFSET.y − clip_h/2) / (clip_h/2); if flip_y then both sy and oy are negated (L607-608)
    - sz = SCALE.z, oz = OFFSET.z (raw, not normalised)
  - Host viewport is always the full surface clip rectangle at (0,0) (R VK/VKGSRender.cpp L1239-1253 "scale_offset matrix already has viewport matrix factored in"; GL/GLGSRender.cpp L77-85; R7 D3D12GSRender.cpp L465-477 uses {0,0,clip_w,clip_h,0,1}).
  - Which flip: Vulkan/GL path passes flip_y = false (R RSXDrawCommands.cpp L623). RPCS3's own D3D12 backend passed flip_y = true (R7 D3D12Buffer.cpp L81). KNOWN.
- So the answer to "identity epilogue or real scale/offset": RPCS3 uses the real scale/offset, folded into the shader, plus an identity full-surface host viewport.

### 1.3 How D3D12 should reproduce it (spec)
- KNOWN (from R7, RPCS3's own D3D12 mapping): host viewport {0,0,clip_w,clip_h}, shader epilogue x' = x·sx + w·ox, y' = y·sy + w·oy with the flip_y=true fold, z' = z·sz + w·oz.
- Why flip_y=true on D3D (ASSUMED by derivation, consistent with R7): D3D NDC y=+1 is the top row; Vulkan NDC y=−1 is the top row. With the usual negative SCALE.y the VK fold gives sy=−1, and the D3D fold gives sy=+1.
- Test vectors (python, 1280×720, flip_y=true):
  | Case | SCALE | OFFSET | D3D sx, ox, sy, oy, sz, oz | ndc (1,−1,1) → pixel | identity x/y would give |
  |---|---|---|---|---|---|
  | typical | (640,−360,0.5,0) | (640,360,0.5,0) | 1, 0, 1, 0, 0.5, 0.5 | (1280,720) | (1280,720) same |
  | left-half viewport | (320,−360,0.5,0) | (320,360,0.5,0) | 0.5, −0.5, 1, 0, 0.5, 0.5 | (640,720) | (1280,720) WRONG, 2× wide |
  | y-up (+SCALE.y) | (640,360,0.5,0) | (640,360,0.5,0) | 1, 0, −1, 0, 0.5, 0.5 | (1280,0) | (1280,720) WRONG, upside-down |
  | RPCS3 reset | (2048,2048,0.5,0) | (2048,2048,0.5,0) | 3.2, 2.2, −5.689, −4.689 | (4096,0) | (1280,720) |
  Homogeneous check: clip (2,−1,3,4) with the left-half fold → (−1,−1,3.5,4) → ndc (−0.25,−0.25,0.875).
- Our backend P (KNOWN at master): epilogue forces x/y identity and uses only the z lane (SCALE.z/OFFSET.z when SCALE.z ≠ 0, else 1/0) (P libs/video/rsx_d3d12_backend.c L3607-3615; formula L1998 and rsx_vp_decompiler.c L694 `pos.xyz = p.xyz*posscale + p.w*posoffset`). `d3d12_set_viewport` is an empty TODO (L6297-6301). So P equals RPCS3 exactly when SCALE.xy = (clip_w/2, −clip_h/2) and OFFSET.xy = (clip_w/2, clip_h/2), and differs otherwise (table above). The z lane already matches RPCS3's sz/oz.
- Fix shape (clean-room): compute sx,ox,sy,oy per draw from 0x0A20/0x0A30 and surface clip 0x0200/0x0204 with the flip_y=true fold; write them into vp_posscale/vp_posoffset; keep the full-surface viewport.

### 1.4 Clip range 0x0394/0x0398
- KNOWN (R): CLIP_MIN/MAX are used as z_near/z_far. In the common path the vertex epilogue remaps window z from [min(n,f), max(n,f)] onto [0,1] per vertex (`apply_zclip_xform`, R Program/GLSLSnippets/RSXProg/RSXVertexPrologue.glsl L7-31, enabled from GL/GLVertexProgram.cpp L181 and VK/VKVertexProgram.cpp L365; fallback variant L32-55). Vulkan then sets viewport minDepth/maxDepth = CLIP_MIN/CLIP_MAX only if the device supports unrestricted depth range, else 0/1 (R VK/VKGSRender.cpp L1255-1264). GL sets glDepthRange from them (R GL/GLDraw.cpp L125).
- Formula: d = (z − n·w) / ((f − n)·w), output z = d·w (w ≠ 0). Vectors (python): n=0,f=1,z=2,w=4 → d=0.5; n=0.1,f=0.9,z=2,w=4 → d=0.5; z=−0.4,w=4 → d=−0.1 (outside → clipped if depth clip on); z=5,w=4 → d=1.25 (outside).
- D3D12 equivalent (spec): do the same remap in the VS epilogue; set D3D12_VIEWPORT MinDepth/MaxDepth to 0/1, or to CLIP_MIN/CLIP_MAX when both lie in [0,1]. KNOWN: R7's D3D12 backend always used 0/1 and did no remap (R7 D3D12GSRender.cpp L468-476), i.e. RPCS3's later backends are stricter than its old D3D12 one.
- P (KNOWN at master): state->clip_min/clip_max are only reset (rsx_commands.c L80-81); no handler writes 0x0394/0x0398 and the backend never reads them.

### 1.5 Y-flip, surface origin, half-pixel
- KNOWN (R): SHADER_WINDOW origin and pixel centre only change the fragment program's WPOS input: wpos.y = ±frag_y + (origin bottom ? window_height : 0); integer pixel centre subtracts 0.5 from both wpos biases (R RSXDrawCommands.cpp L767-799; RSXFragmentPrologue.glsl L59-64). They do not change the position transform.
- KNOWN (R GL/GLDraw.cpp L57-62 comment): RSX face winding is based on the upper-left corner and SHADER_WINDOW origin does not affect it. So on D3D (also upper-left) the front-face sense should not be inverted for origin=bottom. ASSUMED that this carries to D3D12 unchanged; UNVERIFIED for this game.
- Half-pixel: KNOWN (MS "Coordinate Systems (Direct3D 10)"): D3D10+ (so D3D12) pixel centres are at +0.5 from integer, the same as GL/Vulkan, unlike D3D9. RPCS3 adds no vertex half-pixel offset in any backend (no such term in R RSXDrawCommands.cpp L595-618). So: no −0.5 vertex shift on D3D12; only apply the −0.5 WPOS bias for pixel centre = integer.

---------------------------------------------------------------------
## 2. 0x1D78 ZMIN_MAX_CONTROL
- KNOWN bit meanings (R rsx_decode.h L624-654): bits 0-3 depth_clip_enabled (any bit set = true); bits 4-7 depth_clamp_enabled; bits 8-11 depth_clip_ignore_w. Reset 0x1 = clip on, clamp off (R rsx_methods.cpp L523).
- KNOWN RPCS3 use:
  - Host depth clamp (= no near/far clipping) is enabled when clamp || !clip: VK/VKGSRender.cpp L284, GL/GLDraw.cpp L95, RSXDrawCommands.cpp L763 (float-depth emulation path).
  - depth_clip_ignore_w is decoded (rsx_methods.h L1312-1314) but no backend uses it (grep of R finds no consumer). So its real behaviour is UNVERIFIED; RPCS3 ignores it.
  - Cull/user-clip: 0x1D78 has no cull bit in RPCS3's decoder (KNOWN; only the three fields above).
- KNOWN D3D12 semantics (MS D3D12_RASTERIZER_DESC): DepthClipEnable=TRUE clips 0 ≤ z ≤ w; FALSE skips only that z test, the 0 < w test stays. KNOWN (MS Output-Merger page): D3D always clamps the final depth to [Viewport.MinDepth, Viewport.MaxDepth]. So D3D12 "clip off" already behaves as "clamp on".
- Mapping (spec): DepthClipEnable = clip && !clamp, and put it in the PSO key. KNOWN R7 used DepthClipEnable = depth_clip_enabled() only (R7 D3D12PipelineState.cpp L280); the clamp term matches the newer VK/GL rule.
- Decode table (python):
  | 0x1D78 | clip | clamp | ignore_w | DepthClipEnable |
  |---|---|---|---|---|
  | 0x000 | F | F | F | FALSE |
  | 0x001 (reset) | T | F | F | TRUE |
  | 0x010 | F | T | F | FALSE |
  | 0x011 | T | T | F | FALSE |
  | 0x101 | T | F | T | TRUE (ignore_w unused) |
- Clamp in the shader vs MinDepth/MaxDepth: not needed for the plain case because D3D's OM clamp does it (KNOWN, MS). Shader-side clamp is only needed if the FP writes depth and must be clamped to CLIP_MIN/MAX that differ from the viewport range (ASSUMED, same reasoning as Mesa d3d12 cited in gpuweb issue #2100).
- P (KNOWN at master): guest PSO is `pd = {0}` (rsx_d3d12_backend.c L2670), RasterizerState sets FillMode/CullMode/FrontCounterClockwise (L2677-2690) but never DepthClipEnable, so it is FALSE for every guest draw; 0x1D78 is never read.

---------------------------------------------------------------------
## 3. Fog
- KNOWN registers: FOG_MODE 0x08CC, FOG_PARAMS 0x08D0 (p0, float bits) and 0x08D4 (p1, float bits) (R gcm_enums.h L625-626; rsx_decode.h L1048-1090). RPCS3 also resets a third word 0x08D8 to 0 (rsx_methods.cpp L264) but reads only p0/p1.
- KNOWN enum values (R gcm_enums.h L876-881): LINEAR 0x2601, EXP 0x0800, EXP2 0x0801, EXP_ABS 0x0802, EXP2_ABS 0x0803, LINEAR_ABS 0x0804. Reset = 0x0800 EXP, params 0 (rsx_methods.cpp L261-264).
- KNOWN formulas (R Program/GLSLSnippets/RSXProg/RSXFragmentPrologue.glsl L68-102), x = VP fog output (o5.x, R VK/VKVertexProgram.cpp L300):
  - LINEAR: f = p1·x + (p0 − 1)
  - LINEAR_ABS: f = p1·|x| + (p0 − 1)
  - EXP: f = exp(11.084·(p1·x + p0 − 1.5))
  - EXP_ABS: same with |x|
  - EXP2: f = exp(−(4.709·(p1·x + p0 − 1.5))²)
  - EXP2_ABS: same with |x|
  - any other mode: f = 0 (default branch)
  - then f is clamped to [0,1].
- KNOWN FP input: fogc = (x, f, 0, 0), raw value in .x and factor in .y (RSXFragmentPrologue.glsl L70, L77-101; built at VK/VKFragmentProgram.cpp L539-540, GL/GLFragmentProgram.cpp L336-337 only when the FP reads FOGC).
- UNVERIFIED: how the SDK's cellGcmSetFogParams/FogMode turn fog start/end/density into p0/p1. Not checked against SDK docs. Arithmetic only: for linear f = (end − x)/(end − start) needs p1 = −1/(end−start), p0 = 1 + end/(end−start).
- Vectors (python; start 10, end 100 → p0 = 2.111111, p1 = −0.011111):
  | mode | x=10 | x=55 | x=100 | x=−55 |
  |---|---|---|---|---|
  | LINEAR 0x2601 | (10,1,0,0) | (55,0.5,0,0) | (100,0,0,0) | (−55,1,0,0) |
  | LINEAR_ABS 0x0804 | (10,1,0,0) | (55,0.5,0,0) | (100,0,0,0) | (−55,0.5,0,0) |
  | EXP 0x0800 | f=1 | f=1 | f=0.00392 | f=1 |
  | EXP2 0x0801 | f=0.00391 | f=1 | f=0.00391 | f=0 |
  | invalid 0x1234 | f=0 | f=0 | f=0 | f=0 |
  Extra: EXP p0=1.5,p1=−1: x=0.05 → 0.57453, x=0.1 → 0.33009; EXP2 p0=1.5,p1=1: x=0.1 → 0.80112.
- P (KNOWN at master, per gfx-advisor-hypotheses-1 H2a): no 0x08CC/0x08D0/0x08D4 handling; fogc = o5.xxxx. With x=55 P gives (55,55,55,55) where RPCS3 gives (55,0.5,0,0). If the FP does lerp(colour, fogcolour, fogc.y): colour 0.4, fog 0.8 → 0.6 in RPCS3 vs 22.4 in P, which saturates to 1.0 = white. That number is arithmetic; whether the ground FP actually does this is UNVERIFIED.

---------------------------------------------------------------------
## 4. Vertex fetch
### 4.1 Registers (KNOWN)
| Register | Address | Layout | Source |
|---|---|---|---|
| VERTEX_DATA_ARRAY_OFFSET[n] | 0x1680 + 4n | bit 31 location (0 local/VRAM, 1 main), bits 0-30 offset | R gcm_enums.h L664; RSXDrawCommands.cpp L118, L170 |
| VERTEX_DATA_ARRAY_FORMAT[n] | 0x1740 + 4n | bits 0-2 type, 4-7 size, 8-15 stride, 16-31 frequency | R gcm_enums.h L670; rsx_decode.h L4434-4454 |
| VERTEX_DATA_BASE_OFFSET | 0x1738 | u32 | R gcm_enums.h L668; rsx_decode.h L1731-1749; reset 0 rsx_methods.cpp L317 |
| VERTEX_DATA_BASE_INDEX | 0x173C | u32 | R gcm_enums.h L669; rsx_decode.h L1777-1795; reset 0 rsx_methods.cpp L318 |
| FREQUENCY_DIVIDER_OPERATION | 0x1FC0 | bit n = attribute n: 1 MODULO, 0 DIVIDE | R gcm_enums.h L738, L86-87 (MODULO=1, DIVIDE=0); rsx_decode.h L538-552; reset 0 rsx_methods.cpp L216 |
"Enabled array" = size > 0 (R RSXDrawCommands.cpp L106-116).

### 4.2 Address formula (KNOWN as RPCS3 implements it)
- base(n) = (BASE_OFFSET + (ARRAY_OFFSET[n] & 0x7FFFFFFF)) & 0x0FFFFFFF, in the memory selected by bit 31 (R Utils/rsx_utils.h L517-522, used at RSXDrawCommands.cpp L182-186).
- For indexed draws the vertex index is i = (index_from_buffer + BASE_INDEX) & 0x000FFFFF (R rsx_utils.h L524-529; applied as a rebase at GL/GLVertexBuffers.cpp L168-172, VK/VKVertexBuffers.cpp L193-194). For non-indexed draw-arrays RPCS3 does not add BASE_INDEX (VK/VKVertexBuffers.cpp L101-118 returns offset 0). KNOWN for RPCS3; the real-hardware behaviour for arrays is UNVERIFIED.
- element e(i): stride 0 → e = 0 for every vertex ("single_vertex", R RSXDrawCommands.cpp L175-179; descriptor frequency left 0 at L479; shader uses vertex_id 0 when frequency 0, RSXVertexFetch.glsl L191-194). Frequency 0 or 1 → e = i (L484-489; modulo choice L492, division L509). Frequency F > 1 with bit n of 0x1FC0 set → e = i mod F (shader L195-199); bit clear → e = floor(i / F) (L200-203).
  - UNVERIFIED: the exact interaction of BASE_INDEX with divide/modulo. RPCS3's shader subtracts its own base index for divide and adds an index offset for modulo, with the comment that base must be 0 when a modulo is active (RSXVertexFetch.glsl L197-202). Treat "i includes BASE_INDEX" as ASSUMED for divide/modulo.
- byte address of component c = base(n) + e·stride + c·elem_size, values big-endian for 2/4-byte types (RSXVertexFetch.glsl L84-100; single-byte types ignore swap L122-126).
- Vectors (python):
  | BASE_OFFSET | ARRAY_OFFSET | stride | index | BASE_INDEX | i | offset |
  |---|---|---|---|---|---|---|
  | 0x0 | 0x00100000 (local) | 32 | 5 | 0 | 5 | 0x1000A0 |
  | 0x100 | 0x00200000 (local) | 32 | 5 | 0xA | 15 | 0x2002E0 |
  | 0x0FFFFF00 | 0x00000200 (local) | 16 | 0 | 0 | 0 | 0x100 (28-bit wrap) |
  | 0x0 | 0x80001000 (main) | 24 | 3 | 0xFFFFF | 2 (20-bit wrap) | 0x1030 |
  e(i) for F=4: i=0,3,4,6,9 → divide 0,0,1,1,2; modulo 0,3,0,2,1; stride 0 → always 0.
  FORMAT 0x00042044 → type 4 (UB), size 4, stride 32, freq 4. FORMAT 0x00000027 → type 7 (UB256), size 2, stride 0, freq 0 → single element.
- P (KNOWN at master): FORMAT decoded at rsx_commands.c L336-337 and 0x1FC0 stored at L508; 0x1738/0x173C are not applied on the legacy CPU path; stride 0 returns the constant register value instead of element 0 (rsx_vertex_fetch.c L42) (see gfx-advisor-hypotheses-1 H1c, render-bugs-round3 §1).

---------------------------------------------------------------------
## 5. UB256 and CMP decode
### 5.1 UB256 (type 7) and UB (type 4)
- KNOWN (R RSXVertexFetch.glsl L77-78, L122-126, L136-141): element size 1 byte; UB256 scale 1 (value = byte as float, 0..255); UB scale 255 (byte/255); no byte swap; if size < 4, w = 1. RPCS3's old D3D12 path mapped UB256 to R8G8B8A8_UINT (per earlier verified note). UB256 needs size 4 for the host-format path (R Utils/rsx_utils.cpp L387-433, per render-bugs-round3 §1).
- Vectors (python):
  | bytes | size | UB256 | UB |
  |---|---|---|---|
  | 01 80 FF 00 | 4 | (1,128,255,0) | (0.00392,0.50196,1,0) |
  | 00 00 00 FF | 4 | (0,0,0,255) | (0,0,0,1) |
  | 03 02 01 | 3 | (3,2,1,1) | (0.01176,0.00784,0.00392,1) |
### 5.2 CMP (type 6) = 11/11/10 signed
- KNOWN (R RSXVertexFetch.glsl L77-78, L127-134): one 32-bit big-endian word; x = bits 0-10, y = bits 11-21, z = bits 22-31; each field is shifted left (x,y by 5, z by 6) into a 16-bit value, sign-extended as s16, divided by 32767; w = 32767/32767 = 1.
- P (per render-bugs-round3 §1, KNOWN there): sign-extends and divides by 1023 (x,y) and 511 (z). Difference is at most about 0.002 at the extremes (python below); not a stretch-sized error.
- Vectors (python):
  | signed in (x,y,z) | u32 (BE bytes) | RPCS3 | P (/1023,/511) |
  |---|---|---|---|
  | (1023, 0, 511) | 0x7FC003FF | (0.999054, 0, 0.998077, 1) | (1, 0, 1, 1) |
  | (−1024, −1, −512) | 0x803FFC00 | (−1.000031, −0.000977, −1.000031, 1) | (−1.000978, −0.000978, −1.001957, 1) |
  | (512, −512, 256) | 0x40300200 | (0.500015, −0.500015, 0.500015, 1) | (0.500489, −0.500489, 0.500978, 1) |

---------------------------------------------------------------------
## 6. Sanity check: what stretches a ~1 m mesh over half of 1280×720
Assumed projection, for scale only (ASSUMED, not the game's real matrix): vertical FOV 60°, 16:9 → P00 = 0.9743, P11 = 1.7321. Viewport typical (640,−360,0.5,0)/(640,360,0.5,0).
- Correct maths (python): a 1 m wide mesh is 62.4 px at 10 m, 124.7 px at 5 m, 311.8 px at 2 m, 623.5 px at 1 m. It covers half the width (640 px) when it is about 0.974 m from the camera. So a legitimately rendered cape right in front of a close camera can be that big; that alone proves nothing. Compare with RPCS3 at the same frame.
- Case A, wrong x/y viewport scale: to turn the 5 m view (124.7 px) into 640 px needs 5.132× scale, i.e. SCALE.x ≈ 3284.5 instead of 640. Identity-where-the-game-used-a-sub-viewport gives exactly clip_w/(2·SCALE.x), e.g. 2× for the left-half viewport (ndc x=1 → px 1280 instead of 640). Sign: a uniform affine scale/shift about a fixed centre; proportions kept; every draw using that viewport moves the same way, not only the cloth.
- Case B, w near 0 (or a bad matrix): vertex clip x = 0.5 → ndc 0.5/w: w=1 → px 960; w=0.1 → px 3840; w=0.01 → px 32640; w=0.001 → px 320640. Sign: some vertices of a triangle fly out radially from the vanishing point (perspective explosion), long thin spikes/strips to the screen edge; D3D still drops w ≤ 0 (MS D3D12_RASTERIZER_DESC), so they end near the edge rather than wrapping.
- Case C, transform applied twice (window values treated as NDC again): ndc 0 → px 640 → px 410240; ndc 0.195 → 764.8 → 490112: everything off-screen, so this gives a missing mesh, not a half-screen sheet. Twice the normalised fold on a sub-viewport: ndc 1 → 0 → −0.5 (shrinks/moves, does not stretch).
- Case D, bad source positions (cloth job output): object-space positions themselves are wrong; w and matrices are normal. Sign: only the cloth draw is wrong, pinned vertices sit right and free vertices go to one far point or explode; changes over frames.
- How to tell them apart in a capture (spec): dump, for the sheet's draw, attr0 raw positions (first 32), the VP output clip (x,y,z,w) of those vertices, and the registers of §7.
  - A: positions and clip w sane, SCALE/OFFSET differ from (clip_w/2, ±clip_h/2) and the image matches after the §1.3 fold.
  - B: some clip w within about ±0.01 of 0 (or negative) while x,y are ordinary.
  - C: clip values already in the hundreds (pixel-sized) before the epilogue.
  - D: raw attr0 has 0/NaN/huge or clustered values, or differs from RPCS3's buffer at the same address.

---------------------------------------------------------------------
## 7. Capture plan: same-frame register dump  (STATUS: NOT YET DONE)
Goal (Saud): take the real values from the game running in RPCS3 and apply them as-is in our build, not tuned by hand. Salem captures; the graphics advisor compares.
How (KNOWN tools): RPCS3 "RSX Capture" hotkey Alt+C (R rpcs3/rpcs3qt/shortcut_settings.cpp L87) writes an .rrc file under the RPCS3 config folder captures/ (main_window.cpp L740), which can be replayed. This only reads; it changes no RPCS3 files beyond writing the capture. Which per-draw register views the RPCS3 UI shows for an .rrc replay is UNVERIFIED; if not shown, use RPCS3's RSX method log for the same frame (UNVERIFIED option name). In our build, log the same registers at the draw that matches (same VP/FP ucode hash and vertex count).
Pick the draw: the sheet/cloth draw found by the DRAW_LIMIT bisect (gfx-advisor-hypotheses-1 H1a), one ground draw, one building draw.

Registers to dump at that draw (both sides):
| # | Register(s) | Decode | If RPCS3 ≠ ours it means |
|---|---|---|---|
| 1 | 0x0A20-0x0A2C VIEWPORT_OFFSET, 0x0A30-0x0A3C VIEWPORT_SCALE | 8 floats | our method capture is wrong (should be identical raw words; the game wrote them). If identical but not (w/2,±h/2) → our identity x/y is wrong for this draw (§1.3) |
| 2 | 0x0200/0x0204 SURFACE_CLIP | x,w / y,h | wrong clip size → wrong fold; also check which RT is bound |
| 3 | 0x0208 SURFACE_FORMAT (bits 0-4 colour, 5-7 depth, 8-11 type, 12-15 AA, 16-23 log2w, 24-31 log2h; R rsx_decode.h L3330-3363), 0x020C PITCH_A, 0x022C PITCH_Z, 0x0210 COLOR_AOFFSET, 0x0214 ZETA_OFFSET, 0x0220 COLOR_TARGET (R gcm_enums.h L563-570) | ints | different target/format/pitch → the draw goes to a different surface (post/exposure path, round3 §3) |
| 4 | 0x0394 CLIP_MIN, 0x0398 CLIP_MAX | floats | we never apply them (§1.4); values other than 0/1 mean our depth range is wrong |
| 5 | 0x1D78 ZMIN_MAX_CONTROL | clip/clamp/ignore_w | if clip=1,clamp=0 our DepthClipEnable=FALSE is wrong for this draw (§2) |
| 6 | 0x1D88 SHADER_WINDOW | height/origin/centre | WPOS bias wrong (affects shaders that read WPOS) |
| 7 | 0x1738 BASE_OFFSET, 0x173C BASE_INDEX | u32 | non-zero → our legacy fetch reads the wrong vertices (§4) |
| 8 | per enabled attr n: 0x1680+4n OFFSET, 0x1740+4n FORMAT (type/size/stride/freq), 0x1FC0 bit n | ints | stride 0 → we use the constant not element 0; freq/modulo differ → instancing wrong |
| 9 | first 32 attr0 elements (raw bytes at the computed address) | per type | differ → the data itself differs (cloth SPU job, H1a), not the maths |
| 10 | 0x08CC FOG_MODE, 0x08D0 p0, 0x08D4 p1 | enum + floats | non-reset mode/params + FP reads FOGC → our fogc.y is wrong (§3) |
| 11 | VP constants c0-c15 (+ any others the VP reads) | floats | differ → matrices/camera; also check our `[VPFB] fallback proj` |

Side-by-side format (one file per draw, plain text, hex words plus decoded value):
```
draw: frame=<n> draw=<k> vp_hash=<..> fp_hash=<..> verts=<..> prim=<..>
reg     name                 rpcs3_hex   rpcs3_val      ours_hex    ours_val       match
0x0A20  VIEWPORT_OFFSET.x    0x44200000  640.0          0x44200000  640.0          Y
0x0A34  VIEWPORT_SCALE.y     0xC3B40000  -360.0         ...         ...            ?
0x1D78  ZMIN_MAX_CONTROL     0x00000001  clip=1 clamp=0 ...         (not read)     N
...
attr0[0..31]: rpcs3=<hex dump>  ours=<hex dump>
```
Rule: compare raw hex words first. Only identical raw words may be "applied as-is"; never hand-tune a value to make the picture look right.

---------------------------------------------------------------------
## 8. Values from game files (static)
Saud prefers reading values from the game files without running the game. What is and isn't possible:
### 8.1 What the files are (with labels)
- KNOWN (our own run notes, Strikeforce-report-for-AI.md L42, L106-107): the PS3 build reads /dev_bdvd/PS3_GAME/USRDIR/LINKDATA.IDX (and LINKDATA data).
- KNOWN (dbox.tools listing of the Xbox 360 disc KO204205A0X11): LINKDATA.BIN 1.8 GB + LINKDATA.IDX 107.1 KB, plus BGMLink.g1l. The PS3 layout beyond LINKDATA.IDX is UNVERIFIED.
- ASSUMED/UNVERIFIED: the IDX entry layout. Community docs (XentaxWiki "Koei Tecmo LINKDATA BIN IDX"; r/dynastywarriors container docs) describe IDX entries of 8-32 bytes with offset, uncompressed size, compressed size and sometimes a compression flag, with zlib/LZP2 compression and nested subcontainers. Not checked against Strikeforce's file.
- ASSUMED/UNVERIFIED: that Strikeforce models are G1M and textures G1T. Koei Tecmo's later games use G1M/G1T (community docs; Project-G1M, github.com/Joschuka/Project-G1M, commit d69a6d0). Project-G1M's headers (read on the box, GPL, not copied) show:
  - G1MG section header holds a platform id and a bounding box min_x..max_z as 6 floats, byte-swapped for big-endian platforms (Source/Public/G1M/G1MG.h L44-66). KNOWN for the format as parsed there; UNVERIFIED for Strikeforce.
  - G1MG has vertex-attribute, vertex-buffer and index-buffer subsections (G1MGVertexAttributes.h, G1MGVertexBuffer.h, G1MGIndexBuffer.h), so per-mesh stride and attribute types are in the file if the format matches.
  - NUNO/NUNV/NUNS/SOFT sections are cloth/soft-body data (magic values in G1M.h L19-26). ASSUMED: Strikeforce's cape uses one of these, driven at runtime by the SPU cloth job KSG2PS3SPUCloth.
  - G1T platform enum lists PS3 = 0x1 (G1T.h L8-21).
### 8.2 Can come from files (if the containers parse)
- Mesh bounding boxes (cloth mesh size in object units).
- Vertex formats, strides, vertex counts, index counts of each submesh. These should match the 0x1740 FORMAT stride/type the game later programs (cross-check; ASSUMED, the game may repack).
- Texture width/height/format/mip count (G1T), to check the ground/building textures and their formats.
- Bind-pose cloth vertex positions (the rest shape before simulation).
### 8.3 Cannot come from files (computed at runtime by game code)
- VIEWPORT_SCALE/OFFSET (0x0A30/0x0A20), CLIP_MIN/MAX (0x0394/0x0398), ZMIN_MAX_CONTROL (0x1D78), SHADER_WINDOW, surface sizes/offsets, BASE_OFFSET/BASE_INDEX, fog mode/params, VP constants (camera/projection matrices), and the simulated cloth positions. These are written by PPU code (and the SPU job) every frame. Static reading of the PPU code could in principle find constant arguments to the viewport/fog calls, but that is code analysis, not a file value, and is UNVERIFIED for this game.
### 8.4 Plan: cloth size from the file vs the on-screen stretch (not done)
1. Saud decides whether a copy of LINKDATA.IDX / LINKDATA.BIN may be taken off his PC to the box. Nothing is read or copied from his PC without his own words approving it; nothing is installed on it.
2. On the box: parse IDX entries, find G1M-magic entries, read each G1MG bounding box; pick the cloth/cape mesh (submesh with NUNO/SOFT data or the one whose vertex count equals the sheet draw's vertex count from the bisect).
3. Expected size: bbox extent E (object units). Project with the captured VP constants (§7 row 11) and the captured viewport (row 1): expected pixel width ≈ E·P00/depth·(SCALE.x) — same arithmetic as §6.
4. Compare with the sheet's measured pixel width in our build and in RPCS3. Equal to RPCS3 → maths fine. Our width ≫ expected while positions in attr0 lie outside the bbox (by more than the cloth's plausible motion) → Case D (cloth job data). Positions inside the bbox but pixels wrong → Case A/B (transform).

---------------------------------------------------------------------
## 9. What to check in our backend (one line each)
1. Viewport: log 0x0A20-0x0A3C + 0x0200/0x0204 per draw and compare vp_posscale/vp_posoffset with the §1.3 fold (P rsx_d3d12_backend.c L3607-3615).
2. Depth clip: log 0x1D78 per draw and the PSO's DepthClipEnable (P L2670-2690); expect TRUE when value = 0x1.
3. Fog: log 0x08CC/0x08D0/0x08D4 writes and `[FOGFP]` for FPs that read FOGC; compare fogc.y with §3.
4. Vertex fetch: log non-zero writes to 0x1738/0x173C and every enabled attr with stride 0 or freq > 1 (plus 0x1FC0) on the sheet/ground/building draws.
5. UB256/CMP: VP_ATTRS_DUMP on any type-6/type-7 attribute of the sheet draw; compare to §5 tables (CMP rounding difference ≤ about 0.002, not a stretch).
6. Stretch: for the sheet draw dump 32 attr0 raw values and their clip (x,y,z,w); classify with §6 A-D.
7. Clip range: log 0x0394/0x0398 (never applied in P, rsx_commands.c L80-81).
