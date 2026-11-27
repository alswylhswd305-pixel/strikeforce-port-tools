# Strikeforce faces (#4 guard, #5 other faces missing, #8 player, #9 blue tint): graphics advisor hypotheses #1
Written 2026-11-26 ~19:40 Asia/Kuwait by the graphics (RSX) advisor. Advice only. Nothing was built or run, Saud's PC was not touched, and nobody was messaged.
Labels: KNOWN = read in a cited source or dump. ASSUMED = reasoning. VERIFY = a test. No success rates.
Pins:
- P = ps3recomp master `e85647a` (/workspace/ps3-research/ps3recomp, still HEAD after a fetch at 19:30).
- S = Salem's tree as copied to /workspace/faces/src (15:29 copy, CRLF). It is P plus local patches. Line numbers below are P, with S in brackets where they differ.
- R = RPCS3 `0ca5eb0`, paths under rpcs3/Emu/RSX/.
- Dump = /workspace/faces/fp_dump_1448.hlsl, 31 compiled FPs from S at 14:48.

## 0. What the shots show (my reading)
- Guard (guard_crop.jpg, gL_300.jpg): the helmet, plume and armour are fine. Where the face should be there is an opaque black oval. Below it is a strip of skin with a mouth line (the "chin").
- Player (player_face_1826.jpg, look_1826): the hair is fine. There is a dark band across the eye line, then flat skin with a white patch over the nose and mouth and a brown mouth line. There are no eyes or brows.
- Woman in red (look_1826 crop): flat skin with no eyes or mouth.
- Every face looks the same: the body and base head render, the face-detail layer (eyes, brows, mouth) is missing or black, and the shading is flat.
- HUD portraits are fine (gL_seq), so this is a 3D-path problem, not the face art.
- I could not see the blue tint in any capture (#9 stays unconfirmed). There is no RPCS3 close-up of a face on the box; one is needed (§4).

## 1. Ranked hypotheses
### H1. One FP pipeline is shared by materials whose inline constants differ (stale per-object constants)
- KNOWN:
  - The legacy path keys the FP PSO on `rsx_fp_code_hash` (P rsx_d3d12_backend.c L2351-2366 [S L2360-2367]; key compare at L2375-2387). That hash skips every inline-constant slot (P rsx_fp_decompiler.c L1753-1768).
  - The shader is compiled with `rsx_fp_decompile` (P L2450 [S L2453]), which bakes the constants into the HLSL as literals. Every program in the dump has literals and no fp_k[]/cbuffer reads.
  - The backend still fills fp_k[] per draw (P L3545 [S L3606]), but nothing reads it.
  - The result: the first material compiled for a given code+VS+blend+RT key fixes the constants for every later material with the same code.
- KNOWN, this game: the dump has identical code with different literals.
  - 0x0E9FF381 vs 0x0E9FE401: per-RGB exp2 coefficients (-1.58696,-1.65879,-2.16981) vs (-1.1152,-1.46489,-2.16404); additive colours (0.017562,0.0110,0.00462) vs (0.01785,0.01132,0.00460); and (0.2604,0.3115,0.2381) vs (0.2529,0.3029,0.2387).
  - 0x0E9FCF81 vs 0x0E9FCB01: blur texel offsets of 1/322 vs 1/162.
  - So per-object lighting or scattering terms live in the FP constants.
- R does what P intended: its hash skips constants (Program/ProgramStateCache.cpp L540-565), and the constants come from a per-draw buffer (ProgramStateCache.h L405-414).
- Why it fits faces (ASSUMED):
  - Face and skin materials share code with other character materials. Lit with another object's extinction, in-scatter and mask constants, they come out flat or washed, or tinted (#9).
  - If a face-detail material keeps an alpha or mask threshold in an FP constant, the alpha test (S L2676-2710) can discard the eyes.
  - This is also a candidate for the white ground (#7) and the dark buildings, because the same mechanism applies to every material.
- Test T1 needs no code: the same build with `FP_CONSTBUF=0`. That puts the constants into the hash (P L2357-2362), so each constant set gets its own correctly-baked PSO.
  - Confirmed if eyes, brows or mouth appear, skin shading or tint changes, or the ground changes.
  - Expect extra compiles and stutter. It is diagnostic only.
- Root fix, needs Saud's approval: compile with the decompiler's buffered-constant mode (`rsx_fp_decompile_buffered_ex`, P rsx_fp_decompiler.c L1463) and feed the slot the backend already fills.
  - First, unify the b1 layout. The decompiler declares fp_constants[N]+fp_alpha, master assumes texscale[4]+alphatest+fp_k[64] (P L77-79), and S's alpha patch declares texscale_b1[4]+rsx_alphatest.
  - Do not keep FP_CONSTBUF=0 as the fix.

### H2. Face textures hit the backend's format whitelist: unsupported formats get a NULL SRV (black) or keep the previous draw's texture
- KNOWN:
  - `d3d12_bind_texture` records a unit only for 0x81, 0x85, 0x86-0x88, 0x8B, 0x94, 0x95, 0x9A, 0x9C and 0x9F (P L7769-7782 [S L8108-8116]).
  - For any other format the unit is not updated. `.set` is only ever set to 1 (P L7842 [S L8176]) and never cleared, so the draw samples the PREVIOUS texture on that unit.
  - A unit that was never recorded gets a NULL SRV (P L5072-5082 [S L5225]), which samples (0,0,0,0): black, alpha 0.
  - Missing formats include 0x82 A1R5G5B5, 0x83 A4R4G4B4, 0x84 R5G6B5, 0x8F, 0x97, 0x98/0x99 HILO8, 0x9B, 0x9D D1R5G5B5, 0x9E D8R8G8B8, 0xAD/0xAE and the depth formats 0x90-0x93.
  - The enable bit (CONTROL0 bit 31) is not checked either. R binds a null view for a disabled unit (VK/VKDraw.cpp L681-729).
- Why it fits (ASSUMED): a black face oval is a black NULL sample, and flat skin with no detail is a stale texture from the previous draw.
- Test T2 needs no code. Run the logging flags `TEXFMT_ALL=1 TEX_BINDDBG=300` (P L7697-7711, L5075-5080).
  - Confirmed if a draw in the head range binds a format outside the whitelist, or prints `[TEXBIND] null SRV`.
  - With the FACES_CTL diag build, `list` prints t0-t7 format/size/remap per draw, which gives the same answer per draw.
- Root fix: decode the missing formats (rsx_texture_layout already knows most classes), and clear or rebind a unit on every bind and on a disabled unit, as R does.

### H3. No polygon offset: the eye, brow and mouth decal layers lose the depth test against the face
- KNOWN:
  - P never handles POLY_OFFSET_FILL_ENABLE 0x0A68, SCALE 0x0A78 or BIAS 0x0A7C. A grep of rsx_commands.c and rsx_d3d12_backend.c in P and S finds nothing (R gcm_enums.h L642-649).
  - R applies them as depth bias (VK/VKDraw.cpp L215-236).
  - The legacy PSO sets no DepthBias.
- Why it fits (ASSUMED): coplanar decals drawn with LESS and no bias are rejected completely, so the face has no eyes. With LEQUAL they would z-fight and flicker.
- Test T3 needs a code change: add 0x0A68, 0x0A78 and 0x0A7C to S's existing SF_METHLOG list (S rsx_commands.c, the METHLOG block). It is logging only.
  - Confirmed if the game enables fill offset with a non-zero bias around the head draws.
  - A cheaper partial check: compare the face-range draws' `dt/df` in the FACES_CTL list. A LESS depth func on a decal-looking draw supports H3.
- Root fix: parse the three registers and add a D3D12 DepthBias/SlopeScaledDepthBias to the PSO key. Scale the bias for the depth format the same way R does.

### H4. A rigid face or eye sub-mesh feeds bone index or weight from a stride-0 array, and P reads the constant register instead of element 0
- KNOWN:
  - P rsx_vertex_fetch.c L42 returns the constant-register value for `stride == 0`.
  - R treats stride 0 as one element read from memory and repeated (Core/RSXDrawCommands.cpp L175-179).
- Why it fits (ASSUMED): rigid parts such as eyes, teeth and face plates bound to a single head bone are classic stride-0 users. With the wrong index or weight they move to the wrong bone or collapse, which is "the face texture sits outside the body mesh".
- Test T4: the FACES_CTL diag build, `deep a-b` on the head draws.
  - It prints each enabled attribute's stride and the first 4 fetched values.
  - Confirmed if an attribute has stride 0 and its fetched value differs from the bytes at its offset.
  - `SF_ATTRSIG=<seconds>` (S L7595) also prints stride per attribute layout with no extra code.
- Root fix: for stride 0, fetch element 0 from memory (keep the constant register only for disabled arrays).

### H5. Head or facial bone constants are wrong: range ≥468, a mid-draw constant update, or SPU-produced bones
- Covered in /workspace/sf-shared/skin-vs-viewport-test.md (T2-T7). In short:
  - P keeps writes to c468-c511 that R drops, and does no read-as-0 for those indices.
  - The per-sub-draw snapshot inside BEGIN/END is unverified.
- Why it fits (ASSUMED): facial bones often sit at the end of the palette, so they are the first to cross c467.
- Test: `TCONST_DBG=1 TCONST_MAX=4000` (S rsx_commands.c L392-394), plus the FACES_CTL `deep` constant files (faces_c_f*_d*.txt). Look for rows ≥468, or head-bone rows that are zero or equal to the previous draw's.

### H6. Missing texture sRGB, expand and shadow compare on the legacy path (tint and brightness, not missing eyes)
- KNOWN:
  - `rsx_fp_decompile` gets no gamma masks, no expand masks and no shadow descriptor.
  - The decompiler has them (P rsx_fp_decompiler.c L516, L583, L643, L1490), but the dump shows none in use.
  - R applies gamma and BX2 expand per texture (Program/GLSLSnippets/RSXProg/RSXFragmentTextureOps.glsl L28-40).
- Why it fits (ASSUMED): a better match for #9 and the white ground than for the missing eyes.
- Test: the TEXFMT_ALL line prints filter and address. Check the gamma bits (filter 28-31) and the expand/unsigned-remap bit (address bit 12) on the head draws' units.

### H7, low. NV40 half/full register aliasing is not modelled
- KNOWN: P declares separate r[48] and h[48] (P rsx_fp_decompiler.c L706). R models the aliasing with a dependency pass (Program/FragmentProgramDecompiler.cpp L1431-1439, Program/Assembler/Passes/FP/RegisterDependencyPass.cpp).
- I found no read-through-alias case in the 31 dumped programs. This is ASSUMED rare.
- Test only after H1-H5 are clean: `FP_PICK=<face fp>`, then compare against an R capture.

### Ruled down
- Viewport: the same for all draws (skin-vs-viewport §0).
- Sampler wrap and LOD: honoured (P L2131-2143).
- Mips: only level 0 is uploaded, so aliasing is possible but nothing goes missing.
- Fog cbuffer: affects the whole scene, not only faces.

## 2. Run plan for Salem
Salem's queue stays as it is: the loading-screen freeze first.
- Runs 1-2 use the existing build, with env vars only and no code change. Running them on Saud's PC still needs Saud's OK.
- Run them as 2 parallel instances at the village gatekeeper.
- Run 1, baseline plus logs: `TEXFMT_ALL=1 TEX_BINDDBG=300 REMAPDBG=1 SF_ATTRSIG=60 TCONST_DBG=1 TCONST_MAX=4000`.
- Run 2: the same logs plus `FP_CONSTBUF=0`. This is the only visual change.
- Capture in both:
  - a close-up screenshot of the gatekeeper face and Zhao Yun's face;
  - the stderr lines [TEXFMT_ALL], [TEXBIND], [REMAP], [SFSIG] and the TCONST lines;
  - the stdout [D3D12]/[FP] compile lines.
- Run 3 needs the FACES_CTL diag build (/workspace/faces/backend_diag.c, a code change, Saud approves first):
  1. `list` gives the [FCL] line per draw. Pick the head range by vertex count and fp.
  2. `skip` bisect, ceil(log2 N) runs, to find the face-detail draw. Diagnostic only.
  3. `deep` on that draw and its neighbours: attributes and strides, the 4 fetched vertices, the VP HLSL and the non-zero constants.
- Ask for one addition to the diag `list` line: per unit, how the backend resolved it (uploaded / stale / NULL / RT-alias / screen / subvp). The texture path takes those branches at P L4986-5082. This is a code change.
- Reference: an RPCS3 close-up of the same gatekeeper face (and Zhao Yun at the start). If possible, an RSX capture (Alt+C) of that frame for the face draw's textures (format, remap) and its FP constants.
- How to read the results:
  - Run 2 restores the faces → H1.
  - Run 1 shows a non-whitelisted format or a NULL SRV on head draws → H2.
  - Run 3 shows stride 0 on index/weight → H4, rows ≥468 → H5.
  - None of these, and the face-detail draw has a LESS depth func → do T3 (H3).
- One fix per build, then snapshot (playbook L12).

## 3. Shared-cause notes for the physics agent (cloth #3/#10)
- Possibly shared:
  - H4, stride 0: a cloth or scarf attach part with one bone has the same failure mode.
  - H5, constant range and timing: cloth bone matrices go through the same palette.
  - SPU output: if the face or eye bones come from an SPU animation job, check the same overlay clash (sec_cloth and sec_ponytail both at LS 0x3080, cloth image 375200614 on the interpreter as img=9000).
- Note on the ponytail: a wrong ponytail/hair output could pull hair cards down over the eyes. The dark band on Zhao Yun's eye line fits that (ASSUMED).
  - Test: `FP_KILL=<hair fp>` or a skip of the hair draw. If eyes appear under it, the cause is hair placement (physics), not the face shader.
- Not shared: H1 (FP constants), H2 (textures), H3 (depth bias) and H6 are pure RSX.
