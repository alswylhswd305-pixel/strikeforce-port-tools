# Community fixes survey: ps3recomp render layer vs. Strikeforce bugs
Date: 2026-11-26, about 20:45 (Kuwait time, UTC+3). Read-only research. No code changed.

## Scope and method
- Cloned upstream `sp00nznet/ps3recomp`, 2867 commits, HEAD `e85647a` (2026-11-22). Saud's test copy is at exactly this commit (`git log -1` in `ps3recomp-v020-test\ps3recomp`), so every upstream fix listed here is **already in our tree**. The question for each one is whether it reaches the **D3D12 vtable path** (`rsx_commands.c` + `rsx_d3d12_backend.c`), which is the path we use.
- Shallow-cloned 17 downstream ports and grepped their docs and code: inFamous 2, Kamen Rider Battride War, GoW Ascension (Ascension-R), Demon's Souls, Killzone 2/3/HD, Drakengard 3, Bleach SR, GT5, Haze, Ratchet ToD, flOw, Twisted Metal, Saints Row 2, DBZ Budokai HD, PlayStation All-Stars.
- Every URL below returned HTTP 200 on 2026-11-26. GitHub `blob` pages sometimes return 503 at first and load on retry. The winehq page blocks curl but loads through a fetch.
- Licences: upstream ps3recomp is MIT, and its README says "No RPCS3 (GPL) code belongs in this tree". Every port cited here is MIT, except DBZ and Bleach, which have no LICENSE file (treat as all-rights-reserved: idea only). Several of these docs **cite RPCS3 files as a behaviour reference**. Those are flagged [RPCS3-ref]. We use only the idea, with the reference.
- Excluded as GPL: `Michele-M-Media/PS3-TO-PS5-LLVM-RPCS3-RECOMPILER` (GPL-2.0, RPCS3 runtime), `GaSeCaDi/Halo-PS3-Recomp` (GPL-3.0), `SEALCOOL13/broken-2008-incredible-hulk-ps3-recomp` (GPL-2.0). None of them were read for code.

Correction to the brief: **0xA5 is not a depth format.** It is A8R8G8B8 (0x85) with the LN flag (0x20). **0xB0** is DEPTH24_D8 (0x90) with LN. The faces executor's 20:50 inbox note already says the 0xA5 units are colour RTs.

---
## A. Dark faces and buildings: shadow compare (our bug (a), CONFIRMED by our own logs)

### A1. Upstream: the shadow compare exists, but only on the shared draw engine. KNOWN
- ps3recomp PR #302 (Will Tekulve), commit `4033da8d` "Implement referenced 2D depth texture comparisons", and `docs/SHADOW_COMPARISON.md`.
  - https://github.com/sp00nznet/ps3recomp/pull/302
  - https://github.com/sp00nznet/ps3recomp/commit/4033da8d
  - https://raw.githubusercontent.com/sp00nznet/ps3recomp/master/docs/SHADOW_COMPARISON.md
- What it does (paraphrase):
  - A unit with a native depth format (0x90-0x93), alpha-kill off, and TEXTURE_ADDRESS zfunc (bits 28-31) between 1 and 6 becomes a compare unit.
  - TEX/TXP compares the stored red depth against the projected reference (z, or z/w for TXP), clamped to [0,1]. The result is replicated into all 4 lanes.
  - For linear filtering it compares the 4 texel centres and then interpolates (PCF). It does not compare a filtered depth.
  - The doc states plainly: **"Other standalone legacy backend paths still need to adopt the metadata API."**
- Our tree: `rsx_fp_decompile` in the D3D12 backend passes no shadow descriptor. Only `rsx_draw_engine.c` calls `rsx_fp_decompile_buffered_shadow_color_expand_vol_ex`. This matches our log diagnosis exactly.
- Licence: MIT [RPCS3-ref: the doc cites RSXTexture.cpp, RSXThread.cpp, FragmentProgramDecompiler.cpp and VKDraw.cpp as the behaviour contract].
- Maps to: dark faces, dark buildings, probably the dark band over Zhao Yun's eyes. **KNOWN** (the gap is confirmed in our tree and logs).

### A2. Upstream: compare direction fix, "depth FUNC reference". KNOWN
- PR #424 (n0madic), commit `2768e87f`, fixes issue #403.
  - https://github.com/sp00nznet/ps3recomp/commit/2768e87f
  - https://github.com/sp00nznet/ps3recomp/pull/424
  - https://github.com/sp00nznet/ps3recomp/issues/403
- What it changed: the first helper compared in ARB_shadow order (reference FUNC depth), which inverted every shadow. The RSX compares the stored depth against the reference.
- Titles that settled the direction: Soulcalibur II HD (GREATER) and **Killzone 3 on D3D12** (GEQUAL).
- Already in our tree: `rsx_fp_decompiler.h` line 137 says "depth FUNC reference".
- Licence: MIT [RPCS3-ref].
- Maps to: (a). This matters when we wire A1 in: use the helper as it is. Do **not** add another flip on top (see B1).

### A3. inFamous 2 (bhuiyah, D3D12, Windows): the same bug, documented and fixed in their fork. KNOWN that it happened to them; LIKELY the same for us
- Links:
  - https://github.com/bhuiyah/infamous2-recomp/blob/main/docs/GROUND_TRUTH.md (section 4.2: "TEXTURE_ADDRESS bits 28-31 zfunc ... Ours: Ignored; ComparisonFunc is NEVER")
  - https://github.com/bhuiyah/infamous2-recomp/blob/main/docs/NOTES.md, entries "2026-10-15 (morning) - the white-out and the blue faces were dropped texture binds" and "2026-10-20 - shadows (D3): exact depth-compare PCF"
- Symptoms they had:
  - The D3D12 bind recorded only a whitelist of formats. DEPTH24_D8, X16 and Y16_X16 binds were dropped, and the unit kept its previous texture. Result: white-out and **cyan/blue faces**.
- What they changed:
  1. Every libgcm format is bound and decoded.
  2. Depth units do the zfunc compare with 2x2 PCF. Their helper is `rsx_ztex` in the decompiler, and the depth is read through an R24_UNORM_X8 SRV.
  3. PCF exactness: Gather is taken at the footprint centre, with weights from the same coordinate.
  4. TEXTURE_BORDER_COLOR is honoured. Their 1024^2 depth units use border 0x00FFFFFF, which means depth 1.0 = lit outside the map.
  5. SET_SHADER_PACKER (0x1FEC) sRGB output encode is decoded: "without it the correctly lit floor is near-black".
- Their code lives in `patches/ps3recomp/0001-entry-envp-and-lwcond-layout.patch` (MIT repo). They cite envytools, PSL1GHT and Mesa nouveau (MIT) for the compare. Their remap tables cite RPCS3 [RPCS3-ref].
- Maps to: dark faces (KNOWN class), blue tint (UNCONFIRMED: their blue faces came from a dropped bind; see C2), dark buildings (LIKELY).

### A4. Kamen Rider: Battride War (robertoqimin, Vulkan engine): a musou-style brawler, nearly our case. KNOWN for them, LIKELY for us
- Links:
  - https://github.com/robertoqimin/battride-war-recomp/blob/main/docs/ISSUES.md, item 17 "Wrong shadows"
  - https://github.com/robertoqimin/battride-war-recomp/blob/main/port/graphics/rsx_engine_bridge.c (`eng_shadow_reverse`, and the per-unit `rsx_fp_shadow_desc_from_texture` loop)
- Symptom: characters cast no shadow, and the floor inside the shadow map's reach was all darkened. The setup is a 1024x1024 Z24S8 map on unit t3, DEPTH24_D8, zfunc LESS, linear filter. That is the same shape as ours: t1/t2/t3 = 0xB0, 1024x1024, linear.
- Cause 1: the compare direction. They swap LESS<->GREATER and LEQUAL<->GEQUAL, with `PORT_SHADOW_REVERSE=0` to undo it. Their port predates #424, or works around it. Our tree already has #424, so treat the direction as an A/B diagnostic env, not a second flip.
- Cause 2: the border. The shadow map uses BORDER wrap with border 0xFFFFFFFF (depth 1.0). Their backend used black, so everything outside the map read as "in shadow", with a straight-edged dark rectangle.
- How they wired it: for each sampled unit, call `rsx_fp_shadow_desc_from_texture(format, dimension, cubemap, mipmaps, filter, wrap, control0)`, collect a shadow mask, and pass it into the shadow decompile entry point. This is exactly the wiring our D3D12 path lacks.
- Licence: MIT.
- Maps to: dark faces and dark buildings, plus any straight-edged dark region. **LIKELY.**

### A5. Upstream: depth surfaces readable as textures on D3D12 (God of War HD). KNOWN; already in our tree
- PR #559 (Ryan Bagas), commit `fb891549`: https://github.com/sp00nznet/ps3recomp/commit/fb891549
- What it does:
  - Each zeta offset gets its own R24G8_TYPELESS surface.
  - A draw that samples it reads a colour copy whose bytes match what a guest sees for D24S8 read as A8R8G8B8.
- Before it, God of War HD's "distant cliffs came out black and the whole scene too dark".
- This is the "colour copy" our shadow units are bound to today. It is right for 0x85/0xA5 bit-cast reads and wrong for 0x90/0xB0 compare reads.
- Related commits (all MIT):
  - Live-draw: `40789072` (depth read as texture returns real depth).
  - Engine: `948d73f5` and `38b5c377` (D24S8 to ARGB and Z16 to DEPTH16 on the GPU).
  - `aae64e0c`: depth formats present one channel on every crossbar source. Without it, a DEPTH16 map read through crossbar 0xA900 "compared depth 1.0 everywhere". [RPCS3-ref]
- Maps to: (a), the binding half of the fix. **KNOWN.**

### A6. Upstream: guest samplers in D3D12 guest-FP pipelines (GoW HD). KNOWN; in our tree
- PR #558, commit `21c14a65`: https://github.com/sp00nznet/ps3recomp/commit/21c14a65
- Four static samplers were replaced by descriptors built from TEXTURE_ADDRESS/FILTER/CONTROL0/BORDER. Its compare func is still NEVER (our `rsx_d3d12_backend.c` ~L2137).
- Licence: MIT.
- Relevant because a SampleCmp route would need a comparison sampler here. inFamous 2 chose an explicit HLSL compare instead (no root-signature change), and so did upstream's helper.

---
## B. White ground: the terrain is never drawn (our new finding)

### B1. Our D3D12 path ignores VERTEX_DATA_BASE_OFFSET / BASE_INDEX (0x1738 / 0x173C). UNCONFIRMED, cheap to test
- Not a community fix. It is a gap found while comparing paths.
  - Upstream `rsx_dispatch.c` (shared engine) decodes 0x1738 and 0x173C, and the engine applies base_index per draw.
  - `rsx_commands.c` (the vtable path we use) has no handler. Our own `SF_METHLOG` comment says "registers the legacy path ignores today".
- If Strikeforce draws terrain chunks from one shared VB with a base offset or base index, our path fetches the wrong vertices. The tiles then land off-screen or degenerate, which would explain "draws present, nothing visible".
- Test: `SF_METHLOG=1` (log-only, already built in). I found no METHLOG output under `sfauto`, so it has probably never been run.
- Maps to: white ground. **UNCONFIRMED.**

### B2. GoW Ascension (Ascension-R, rigaz29, **same D3D12 vtable backend as ours**): state written by the title and dropped by the backend. KNOWN for them
- Link: https://github.com/rigaz29/Ascension-R/blob/main/docs/notes/2026-10-28-rendering-accuracy-plan.md
- Measured on their path:
  - Draw records past `MAX_DRAWS` = 2048 were dropped. 18% of level frames hit it; they raised it to 8192.
  - Draws were skipped while their pipeline compiled.
  - Never decoded: polygon offset (0x0A68/0x0A78/0x0A7C), blend colour 0x031C, MRT blend enables and masks (0x036C/0x0370), depth bounds (0x0380-0x0388), depth range (0x0394/0x0398), ZMIN_MAX_CONTROL 0x1D78.
- Fixes in their fork (commits `8dad92bf`, `ee59fa6e`, `61ccc5fe`, `8c2916e2`, `428d3289`, `b0122755`; fork not checked for availability):
  - FP precision.
  - MAX_DRAWS 8192.
  - Depth bias.
  - Mip chains.
  - Blend colour via OMSetBlendFactor.
  - Depth bounds via OMSetDepthBounds.
  - Depth clip following ZMIN_MAX_CONTROL.
- Our tree: MAX_DRAWS is 2048, but our listed frame 7091 has 610 draws, so **truncation is ruled out for that frame**. We also have no OMSetDepthBounds, no OMSetBlendFactor, `DepthClipEnable = TRUE` always, and no decode for 0x0380/0x0394.
- Licence: MIT.
- Maps to:
  - white ground: ZMIN_MAX / depth clip, UNCONFIRMED.
  - **opaque light shaft**: depth bounds, LIKELY; see C1.

### B3. Upstream: SET_ZMIN_MAX_CONTROL depth clamp (inFamous 2). KNOWN; engine only
- Commit `53650c7d` (erikomis): https://github.com/sp00nznet/ps3recomp/commit/53650c7d
- What it does: when clipping is off or the clamp is on, geometry in front of the near plane or past the far plane is clamped, not cut. In inFamous 2, shadow casters were cut without it.
- Licence: MIT [RPCS3-ref: "as RPCS3's Vulkan renderer does"].
- Our D3D12 path always clips (`DepthClipEnable = TRUE`, ~L4264). Large terrain or sky geometry crossing the far plane would be cut.
- Test: `SF_METHLOG=1` already logs 0x1D78.
- Maps to: white ground, and shadow casters missing from the shadow map. **UNCONFIRMED.**

### B4. Upstream: user clip planes (inFamous 2 reflections). KNOWN; engine only
- Commit `b19ac284`: https://github.com/sp00nznet/ps3recomp/commit/b19ac284
- What it does: honours SET_USER_CLIP_PLANE_CONTROL (0x1478) with SV_ClipDistance.
- Without it, things are drawn rather than lost, so this is unlikely to be our missing terrain. Low relevance.
- Licence: MIT [RPCS3-ref].

### B5. Upstream: an empty scissor means draw nothing (Folklore, Guitar Hero 3). KNOWN
- Commits `45ef6fcd` (engine) and `5c3e0ca0` (live draw):
  - https://github.com/sp00nznet/ps3recomp/commit/45ef6fcd
  - https://github.com/sp00nznet/ps3recomp/commit/5c3e0ca0
- The commit says the D3D12 path already treats a written zero scissor as empty.
- Worth one log line: if a terrain pass has a written zero-size or off-target scissor, it draws nothing. Low relevance.

### B6. Upstream: offscreen-only batches were dropped (Rubber Ducky). KNOWN; fixed
- Commit `0a776dd3`: https://github.com/sp00nznet/ps3recomp/commit/0a776dd3
- Render-to-texture passes never executed. Already fixed in our tree. Only relevant if terrain goes to an offscreen RT and is composited.

### B7. "Never submitted" branch: terrain built by SPU jobs. UNCONFIRMED lead
- Ascension-R (same note as B2): the FIFO hole "EDGE reserves for an SPU job to fill: the job did not run or did not finish".
- inFamous 2 NOTES "EG1": Edge geometry culling and skinning on SPU.
- Upstream `c26aa59a` "find the RSX pushbuffer an SPU built".
- If Strikeforce's terrain is emitted by an SPU job, a lost-wake there would leave no terrain draw at all. That links to our mixer and SPURS lost-wake class. **UNCONFIRMED.**

### B8. Vertex attribute fixes. KNOWN in our tree; stride-0 is RULED OUT for us
- Commits `bbc14484` (disabled attribute reads the VERTEX_DATA4F constant, not 0) and `b3150f3c` (missing components expand to w = 1):
  - https://github.com/sp00nznet/ps3recomp/commit/bbc14484
  - https://github.com/sp00nznet/ps3recomp/commit/b3150f3c
- Demon's Souls NOTES fix 25 ("invisible shield"): https://github.com/timboat/demons-souls-recomp/blob/main/docs/NOTES.md
  - S1 attributes must convert the NV/GL way, (2c+1)/65535, not c/32767.
  - Not upstream: upstream `rsx_vertex_fetch.c` still divides by 32767.
  - Matters only if terrain weights or positions are S1 with exact zeros. Low relevance.
- Licence: MIT.

---
## C. Other remaining bugs

### C1. Opaque light shaft: depth bounds and blend colour
- **Depth bounds (Ascension-R step 2.3, KNOWN for them).** "The red panels were the depth bounds test". A light curtain drawn with bounds of about 0.97-1.0 covered the whole scene without the test. **LIKELY** for our opaque shaft.
- **Blend colour (Ascension-R step 2.1, KNOWN for them).** CONSTANT_COLOR/ALPHA was mapped but OMSetBlendFactor was never called, so the D3D12 default factor (1,1,1,1) was used and translucent passes came out opaque. **LIKELY** too; we have no OMSetBlendFactor.
- Link: same Ascension-R note as B2. MIT.
- Upstream engine equivalents: `b8839229` and `59d1533b` (depth bounds).

### C2. Blue tint / overall colour
- Upstream `adedc943`, docs/rsx-framebuffer-srgb.md: SHADER_PACKER 0x1FEC sRGB output. Engine only. Our D3D12 backend has no 0x1FEC.
  - inFamous 2 had the same gap on D3D12 ("lit floor near-black").
  - Maps to: dark scene / tint. UNCONFIRMED.
- Upstream `04d2eb17`: per-channel texture gamma. Engine only.
  - https://github.com/sp00nznet/ps3recomp/commit/04d2eb17
  - A gamma applied to some channels and not others would give a colour cast. UNCONFIRMED.
- Upstream `122690f2`: biased unsigned remap and _bx2 fetches (inFamous 2: "normals leaned to (1,1,1)... occlusion volumes drew as dark boxes"). It is wired through the engine's expand masks, so check whether our path passes them.
  - https://github.com/sp00nznet/ps3recomp/commit/122690f2
  - [RPCS3-ref]. Maps to: dark buildings or blue cast from unexpanded normals. UNCONFIRMED.
- inFamous 2 "blue/cyan faces = dropped texture binds" (A3). Our TEX_BINDDBG showed 0 null-SRV units, so a fully dropped bind is **unlikely**.
  - Our D3D12 bind whitelist still drops 0x82/0x83/0x84/0x8F/0x9E/0x9B and DEPTH16 that is not an RT.
  - Check TEXFMT_ALL for any of those.

### C3. Fog (FOGC) and precision
- Demon's Souls NOTES fix 23: a red/dark face came from the FP source precision modifier being ignored. The fog factor near the camera went negative and pushed the colour away from white.
  - Upstream has this since `7e975c9e` (2026-11-02, so it is in our tree, and the decompiler is shared): https://github.com/sp00nznet/ps3recomp/commit/7e975c9e
  - [RPCS3-ref: "RPCS3 ClampValue"]. Nothing new to apply.
- Demon's Souls fix 22: depth read as ARGB fixed missing fog volumes. Live-draw only; the equivalent is already in our D3D12 path via A5.
- No community fix found for FOGC itself. Our 20:50 note says FOGC is not logged yet.

### C4. Audio and SPURS lost-wake, and the ring-index runaway (for the mixer track)
- **Demon's Souls NOTES fixes 26a, 29 and 30 (KNOWN for them), libmixer (cellSurMixer).**
  - `_cellsurMixerMain` waits on the cellAudio notify queue (capacity 2), reads the port's read index, and writes its block **at that index**. So each block must be mixed within one 5.33 ms period.
  - Their WASAPI-paced mix thread produced events in bursts.
  - Fix: mix on an even QPC clock.
  - Also: the notify-queue key race needs `PS3_PRIO_START=1`. That exists upstream, commit `fa360daa`.
- **Battride War, docs/WINDOWS.md (KNOWN for them).** `cellSurMixerStart` read the notify queue key before `_cellsurMixerMain` stored it, and registered key 0. Fix: patch 0002, where the creator waits until the mixer thread first blocks.
  - https://github.com/robertoqimin/battride-war-recomp/blob/main/docs/WINDOWS.md
- **GT5 (MIT)** CHANGELOG 3 Nov: "lost wake-ups" among three freeze causes. No detail read.
- **Upstream cellAudio:** read index as BE u64 (`5bffb52a`), clearing each consumed block (`74c6f961`), POSIX mixer pacing (`64f22fe5`).
- Maps to: the mixer halt / ring runaway, **LIKELY the same class**. A block index taken at the wrong moment, or a key-0 queue, are both candidates. Forward this to the mixer researchers.

### C5. The named projects checked
- flOw (https://github.com/sp00nznet/flow), Twisted Metal, Saints Row 2, DBZ Budokai HD and PlayStation All-Stars (samuelMadureira23/allstars-port; ColinGamez/allstars-ps3 also exists): their docs have **nothing relevant** to shadow, depth, attribute, fog or terrain bugs. They are early-stage or menus-only.
- Twisted Metal's render work went upstream (README: "Most of v0.14.0's draw-engine and Vulkan work came out of this port").
- Killzone 2/3 (undecuple) and Killzone HD (gustavomorinaga): their docs list deferred lighting, shadows and light shafts as "partial", and point to the upstream PRs above. No separate D3D12 shadow fix was found in their docs.

---
## What to try first (max 3)
1. **Wire the existing shadow compare into the D3D12 path.** Same wiring as Battride's `rsx_engine_bridge.c` (A4) and upstream's engine (A1).
   - Per sampled unit, call `rsx_fp_shadow_desc_from_texture` and decompile with the shadow entry point. Add the shadow mask to the FP PSO key.
   - Bind the real depth SRV (R24_UNORM_X8) for compare units.
   - Honour the depth border colour as 1.0 (A3/A4).
   - Keep #424's direction, with a diagnostic A/B env for the flip.
   - It changes behaviour, so it needs Saud's OK.
2. **Missing terrain: one log-only run with `SF_METHLOG=1`** (covered by the standing approval). It shows whether 0x1738/0x173C (vertex base offset/index, which our path ignores: B1) and 0x1D78 (ZMIN_MAX, which we always clip: B3) are written around draws 288-348.
   - If base offset or base index is non-zero there, that is the prime suspect.
   - Also grep that run for `[FP] decompile fail` and `[VP] decompile failed`, since those draws are silently dropped.
3. **Opaque light shaft: log 0x0380-0x0388 (depth bounds) and 0x031C (blend colour) on the shaft draw** (log-only).
   - Our path decodes neither; Ascension-R found exactly this (C1).
   - The fix would be OMSetDepthBounds plus OMSetBlendFactor, after Saud's OK.

---
## Automation tools (added 2026-11-26, about 21:05 Kuwait time, UTC+3)
Honest answer: **no end-to-end tool exists, for ps3recomp or any sibling recomp, that automatically finds and fixes shadow or lighting bugs, or automatically diffs a port against RPCS3 draw by draw.** What exists is a set of building blocks: capture hooks, capture parsers, RenderDoc scripts, frame-diff gates and shader test suites. Wiring them into a per-draw "first divergent draw" pipeline would be new work.

Every URL below returned HTTP 200 on 2026-11-26. Stars and last-push dates come from the GitHub API today. "In our tree" means present in `ps3recomp-v020-test\ps3recomp` (upstream `e85647a`).

### 1. ps3recomp itself (MIT): all in our tree unless noted
- **RenderDoc capture on demand for the D3D12 backend** (PR #561): https://github.com/sp00nznet/ps3recomp/pull/561
  - `RENDERDOC_DLL=<renderdoc.dll>` loads RenderDoc in-process. It captures a frame with at least N draws, up to `RENDERDOC_MAX` frames, into `RENDERDOC_DIR`, and names resources in guest terms.
  - In our `rsx_d3d12_backend.c`: **yes**.
  - Works with our port: **yes, directly**. RenderDoc is already approved by Saud. A capture run needs no code change.
- **`tools/parse_rrc.py`**: https://github.com/sp00nznet/ps3recomp/blob/master/tools/parse_rrc.py
  - Parses an RPCS3 `.rrc.gz` RSX capture into a draw-list manifest (draws, textures, shaders, blend state). The docstring calls it a "ground-truth oracle".
  - Last changed 2026-07-23. Their own code; it reads RPCS3's data format and copies no RPCS3 code.
  - In our tree: yes. Works for us: yes, as the RPCS3 side of a per-draw diff. **An `.rrc` capture needs Saud's OK.**
- **`tools/regress.py` + `regress_ports.toml`**: https://github.com/sp00nznet/ps3recomp/blob/master/tools/regress.py
  - Port regression gate: diffs a milestone log against a checked-in golden. With `--shots`, it compares the port's frames against a gold screenshot and writes a side-by-side image.
  - Five ports are registered (Twisted Metal, VF5, Simpsons, YDKJ, Tokyo Jungle); active through Oct 2026.
  - Works for us: adaptable. It would need a Strikeforce entry. The gold screenshot comparison is a whole-frame check, not per draw.
- **`libs/video/tests/validate_fp_shaders.c`**: https://github.com/sp00nznet/ps3recomp/blob/master/libs/video/tests/validate_fp_shaders.c
  - Runs our FP decompiler over a directory of raw fragment programs (for example RPCS3's shader cache `raw/*.fp`). It reports unhandled opcodes and, on Windows, D3DCompile failures.
  - Works for us: **yes**, against Strikeforce's RPCS3 shader cache. It is read-only on those files.
  - It can show which FPs fail to translate, and those draws get dropped silently.
- **Shader and shadow unit tests**: https://github.com/sp00nznet/ps3recomp/tree/master/libs/video/tests
  - 84 tests, for example `test_shadow_metadata.c`, `test_shadow_engine.c` and `test_fp_decompiler.c`.
  - They are synthetic tests of the shared engine's shadow detection (`rsx_fp_shadow_desc_from_texture` is the "auto-detect shadow texture" logic).
  - Works for us: as a template for a D3D12-path test, not directly.
- **Engine pass dump** `RSX_ENGINE_PASS_DUMP` / `RSX_ENGINE_SHADER_DUMP` (docs/BUILDING.md): each pass's colour targets and zeta, plus a per-draw list. **Engine only**, so not on our vtable path today.
- **PR #748, "opt-in D3D12 backend for the register-file draw engine"** (tekulvw, **open, not merged**, merge-conflicted, about 2,100 lines in 1 commit): https://github.com/sp00nznet/ps3recomp/pull/748
  - With `PS3RECOMP_D3D12_DRAW_ENGINE=1`, Windows renders through the shared engine. That brings shadow compare, depth bounds, depth clamp, vertex base index and the pass dump with it.
  - Not in our tree (`rsx_d3d12_engine.inc` is missing).
  - Works for us: **potentially the biggest single lever**, but it is an unmerged and unreviewed renderer swap, so it is risky. Testing it needs Saud's OK, on the test copy only.
  - A related proposal and fork from an ICO port: issue #457 https://github.com/sp00nznet/ps3recomp/issues/457, and https://github.com/feanor-noldorin/ico-recomp (MIT, 5 stars, last push 2026-10-27).
- **`tools/compare/`**: https://github.com/sp00nznet/ps3recomp/tree/master/tools/compare
  - Function-level comparison of Xbox 360 vs PS3 builds of the same game. CPU-side only, **not render**. Not useful here.

### 2. Downstream ports' tooling
- **Ascension-R `tools/rdoc/`** (MIT, 201 stars, last push 2026-11-26, very active): https://github.com/rigaz29/Ascension-R/tree/main/tools/rdoc
  - `port_run.ps1` captures the D3D12 port through `RENDERDOC_DLL`.
  - `rpcs3_run.ps1` loads RenderDoc's Vulkan layer into one RPCS3 run and posts key presses to RPCS3.
  - `inspect.py` runs headless in qrenderdoc and dumps per-draw lists, textures, pixel history, per-event shader and pipeline state, post-VS vertices, and RPCS3 fragment constants and texture params.
  - It is the **closest thing to a port-vs-RPCS3 per-draw comparator**. It still has no automatic "first different draw" step: they compare by hand.
  - Works for us: **yes**, it targets the same D3D12 vtable backend.
  - Caveats for Saud's rules: their RPCS3 script presses keys (no pad presses during cutscenes) and injects a layer into RPCS3. Both need his OK. Capturing our own port is covered by the RenderDoc approval.
- **Drakengard 3 `rsx_replay` + `tools/replay_regress.sh` + `tools/compare_frames.py`** (MIT, 369 stars, last push 2026-11-24):
  - https://github.com/soyjxck/dod3-recomp/blob/main/tools/replay_regress.sh
  - https://github.com/soyjxck/dod3-recomp/blob/main/tools/compare_frames.py
  - https://github.com/soyjxck/dod3-recomp/blob/main/docs/DEBUGGING.md
  - `RSX_CAPTURE` records the game's RSX stream. `rsx_replay` replays it headless. `compare_frames.py` diffs replayed frames against a reference with a cross-GPU tolerance (99% of pixels within N levels).
  - This is a real **golden-image render regression gate**. But `rsx_replay` lives in their own ps3recomp fork (the submodule is not in the repo snapshot) and drives the shared engine.
  - Works for us: `compare_frames.py` yes. The capture/replay half would need porting to our path.
- **inFamous 2 `tools/ground_truth/`** (MIT, 97 stars, last push 2026-11-19): https://github.com/bhuiyah/infamous2-recomp/tree/main/tools/ground_truth
  - `pngstat.py` and `targets.json` hold region-based colour and luma targets measured from real-PS3 footage. They also have a [ZTEXID] log that auto-lists every depth-compare unit per FP, and `test_ztex_pcf` (exact PCF compared against a double-precision reference on WARP and a GPU).
  - Works for us: `pngstat.py` yes (stdlib-only). It gives a numeric "is the ground still white, are the faces still dark" check on our screenshots. The PCF test would need porting.
- **Killzone 3 `tools/smoke/`** (MIT, 181 stars, last push 2026-11-25): https://github.com/undecuple/project-helghast/tree/main/tools/smoke
  - Many small host tests for single RSX features (blend colour, colour mask, conditional render...), run against real D3D12 under Proton.
  - Works for us: as templates only.
- **Battride War `rsx_engine_bridge.c`** (MIT): https://github.com/robertoqimin/battride-war-recomp/blob/main/port/graphics/rsx_engine_bridge.c
  - Not a tool, but its per-unit shadow detection loop (with an env A/B switch) is the pattern to copy for a "detect every shadow unit and log it" diagnostic.

### 3. General building blocks (not PS3-specific)
- **RenderDoc** (MIT, 11.4k stars, active today): https://github.com/baldurk/renderdoc
  - Python API (https://renderdoc.org/docs/python_api/index.html) for scripted capture inspection and replay.
  - Works for us: yes; already approved. No built-in capture-vs-capture diff exists, so we would script it.
- **NVIDIA FLIP** (BSD-3-Clause, 670 stars, last push 2026-10-13): https://github.com/NVlabs/flip
  - Perceptual image-difference metric and tool. It is a better "how different does this look" score than a raw pixel diff for port-vs-RPCS3 screenshots.
  - Works for us: yes, offline on screenshots. Installing it needs Saud's OK.
- **XenosRecomp** (MIT, 517 stars, last push 2026-11-14): https://github.com/hedge-dev/XenosRecomp
  - Offline Xbox 360 shader to HLSL translator used by the XenonRecomp ports. An analogue of our FP decompiler.
  - It has no shadow or lighting fix automation; its value is as a design reference for offline, testable shader translation. Not usable on RSX code.
- **RT64** (MIT, 1.6k stars, last push 2026-11-05) and **N64Recomp** (MIT, 8.5k stars):
  - https://github.com/rt64/rt64
  - https://github.com/N64Recomp/N64Recomp
  - N64 renderer and recompiler. Nothing that automates render-fix finding, and nothing transferable to RSX.
- **Xenia GPU trace dump** (BSD-3, 9.9k stars, last push 2026-02-18): https://github.com/xenia-project/xenia/blob/master/src/xenia/gpu/trace_dump.cc
  - Replays a recorded GPU command trace and dumps the frame for regression checks. A design analogue of dod3's `rsx_replay`; Xbox 360 only.
- **RPCS3 game patches (`patch.yml`)**: the engine is https://github.com/RPCS3/rpcs3/blob/master/Utilities/bin_patch.cpp (**GPL-2.0**).
  - Patches are per-game memory patches applied at load. **Not usable as code.** As an idea, it is a per-game fix config.
  - It conflicts with our "root fixes only" rule, so we should not use it.
  - The RPCS3 wiki page on patches blocks fetches (403), so it is not cited.

### What this means for us
- **Usable today, read-only or log-only:**
  - our own `RENDERDOC_DLL` capture;
  - Ascension-R's `inspect.py` on that capture;
  - `pngstat.py` or FLIP numbers on our screenshots;
  - `validate_fp_shaders.c` over the RPCS3 shader cache.
- **The automatic per-draw diff that was proposed (Saud's point 3) does not exist anywhere yet.** The parts to build it from are: RENDERDOC_DLL (port side), parse_rrc.py or RenderDoc on RPCS3 (reference side), inspect.py (per-draw state), and compare_frames.py or FLIP (scoring).

---
## New ports (Nov 22-26)

Date: 2026-11-26, about 22:05 (Kuwait time, UTC+3). Revised in the same hour to add GT6 0068, the live-draw path caveat, Cubic's shadow-clear idea, and Vekta's no-shadow-map frame map. Read-only web/GitHub research. Nothing was changed on Saud's PC, and no code in our tree was changed.

This section is an add-on to the survey above. It does not repeat the earlier findings (upstream #302/#424, inFamous 2, Battride War, the D3D12 vtable gaps for 0x1738/0x173C, 0x1D78, 0x0380-0x0388, 0x031C, and the earlier notes on Killzone HD and All-Stars). Those still stand.

### ملخص عربي

- راجعت ستة بورتات طلعت هذا الأسبوع بأداة ps3recomp. الأفيد لنا هو **Gran Turismo 6** (Project Grand Tourer Advanced) لأنه يرسم بـ Direct3D 12 مثل بورتنا.
- **ولا تصليح من هالبورتات انرفع للأصل بعد commit حقنا `e85647a` (22 نوفمبر 2026، 21:22 بتوقيت الكويت).** أصل ps3recomp باقي واقف عند نفس النقطة؛ ما فيه pull request من أصحاب هالبورتات.
- أهم شيء لمشكلة **الأرض البيضاء**: في GT6 لون المزج (`NV4097_SET_BLEND_COLOR`، الأمر 0x031C) ما كان يتطبّق، والجهاز كان يستخدم أبيض (1, 1, 1, 1). هم صلّحوه وصرنا نقدر ننقل الفكرة لمسارنا (رخصة MIT، مع ذكر المصدر). هذا نفس الفراغ المسجّل عندنا في القسم B. **غير مؤكد** إنه هو سبب أرضنا، لكنه أرخص وأقرب تصليح جديد للأرض.
- لمشكلة **الظلال والوجوه الداكنة**: ما لقيت تصليح جديد من نوع الحل المعروف عندنا (قراءة العمق بـ R24_UNORM_X8 + comparison sampler). في GT6 فيه تصليحان مجاوران: (أ) باتش 0068: ممر خريطة الظل بدون هدف لوني كان يوسّم سطح خاطئ عند العنوان صفر، فيُقرأ نسيج فاضي (هذا صلّح وميض المرآة، issue #10). (ب) قراءة العمق كنسيج لوني ARGB (نسخ، مو مقارنة) في باتش 0032/0024، يفيد فقط إذا الظل أو الأرض تُقرأ كلون. **غير مؤكد** أيّ منها ينطبق علينا.
- تصليحات GT6 الرسومية على مسار `rsx_live_draw.c`. هذا الملف موجود في شجرتنا عند `e85647a` (مسار Track B، والهيدر يقول `RSX_DRAW` افتراضياً ON). المسح السابق وصف مسارنا بأنه الـ vtable (`rsx_commands.c` + `rsx_d3d12_backend.c`). **أي المسارين تشتغل عليه سترايك فورس غير مؤكد** من غير سجل من البناء. ننقل الفكرة؛ ما نلصق الباتش كما هو إلا إذا تأكدنا إننا على live-draw.
- MotorStorm وYakuza: لا رخصة واضحة على جذر المستودع (نأخذ الفكرة فقط، ما ننسخ كود). Cubic.Heroes رخصته GPL-3.0: وصف فقط — عندهم خريطة الظل ما كانت تنمسح في بداية الممر. Killzone HD في المستويات اللي صوروها ما فيه خرائط ظل؛ All-Stars ما فيه تصليح رسم جديد هذا الأسبوع.

### Upstream after e85647a

- `sp00nznet/ps3recomp` HEAD is still `e85647a` (merged 2026-11-22, 21:22 Kuwait time, UTC+3). A `since=2026-11-22` listing returned only that merge and its parent. No later commits.
- No pull requests from PrimeTimerer, papand7, gustavomorinaga, IvanBarbosaFilho, irnutsmurt or samuelMadureira23 were found on that repo. A search for "blend constant" / "zstencil" / "GT6" PRs created on or after 2026-11-22 returned none.
- Therefore **none of the fixes below are upstreamed after e85647a**. They are not in our tree unless we port them ourselves.

### 1. Gran Turismo 6 — Project Grand Tourer Advanced (most relevant)

- Repo: https://github.com/PrimeTimerer/Project-Grand-Tourer-Advanced (main). MIT. 70 stars. Created 2026-11-23 07:35 Kuwait time; last push 2026-11-26 19:55 Kuwait time.
- Title: GT6 EU BCES01893 update 1.22. Renderer: **Direct3D 12**. Windows only.
- ps3recomp pin: submodule at `4e8f3ca` (upstream "unify the open PRs for v0.18.0", 2026-10-26). **Older than e85647a.**
- How they patch: apply `patches/*.patch` (79 files, 0001-0080, no 0020) onto that submodule, in number order. See https://github.com/PrimeTimerer/Project-Grand-Tourer-Advanced/tree/main/patches and BUILD.md.
- Almost all of the graphics patches below edit `libs/video/rsx_live_draw.c` (the live-draw D3D12 path). That file is already in our tree at e85647a ("Track B live NV4097 draw path", gated by `RSX_DRAW`; the upstream file header says the default is ON). The earlier survey described our path as the vtable backend (`rsx_commands.c` + `rsx_d3d12_backend.c`). **Which path Strikeforce actually runs is غير مؤكد** without a log from our build. If we are already on live-draw, these patches apply more directly; if we are still on the vtable path, port the idea, do not paste the patch as-is. MIT: reusable with credit to PrimeTimerer / Project Grand Tourer Advanced. [RPCS3-ref: the README says RPCS3 was a behaviour reference and is not shipped.]
- Relevant patches:

  1. **`0078-gt6-blend-constant-colour-light-cubes.patch`** (labelled [GT6 0149] in the patch).
     - https://github.com/PrimeTimerer/Project-Grand-Tourer-Advanced/blob/main/patches/0078-gt6-blend-constant-colour-light-cubes.patch
     - What it fixes: blend factors 0x8001-0x8004 (constant colour / constant alpha and their inverses) were translated to D3D12 `BLEND_FACTOR`, but nothing ever called `OMSetBlendFactor`, so the factor stayed at D3D12's default (1, 1, 1, 1). A "constant colour" was therefore white, and its inverse was nothing. GT6 uses this for glare (CONSTANT_COLOR, ONE — every pass was added in full), a running mean (CONSTANT_ALPHA), and some materials.
     - The colour is `NV4097_SET_BLEND_COLOR` (**0x031C**): A8R8G8B8 for an 8-bit target. For a 16-bit float target the title writes four half-floats: red/green in 0x031C, blue/alpha in **0x037C**. If the RGB factors ask for constant *alpha*, alpha is replicated into all four channels (D3D12 has one factor).
     - Off switch: `LD_BLEND_CONSTANT=0`. Maps to our white-ground suspect 0x031C (survey B2). **LIKELY useful; whether it is the cause of our white ground is غير مؤكد** until the log-only run sees 0x031C around the missing terrain draws.
     - The same patch also builds host cube textures from six render-target faces (GT6 car lamp cubes that were never copied back to guest memory, so the road stayed unlit at night). That part is GT6-specific. **غير مؤكد** for Strikeforce.

  2. **`0068-gt6-surface-without-colour.patch`** (fixes their issue #10).
     - https://github.com/PrimeTimerer/Project-Grand-Tourer-Advanced/blob/main/patches/0068-gt6-surface-without-colour.patch
     - Commit `7c1c9e88` (2026-11-24 19:17 Kuwait time, UTC+3): https://github.com/PrimeTimerer/Project-Grand-Tourer-Advanced/commit/7c1c9e8875aa6032b4d5653629c933d3dee2222c
     - What it fixes: a draw that cannot write its colour target (no colour target selected, or every channel masked) must not mark that address's colour surface as drawn. GT6's shadow-map pass is depth-only; the unused colour-offset register holds 0, the address of display buffer 0. Live-draw used to mark the 1024² surface made for that pass as drawn, so a later 1×1 texture at offset 0 (used where a material has no shadow map of its own) and draws into display buffer 0 read an empty surface. Symptom: the rear-view mirror lost its sunlight on one frame in three (issue #10).
     - Maps to our 0xB0 1024² shadow-map passes if they are also depth-only and share an address with a colour buffer. This can steal or blank a texture. It does **not** replace the R24 comparison-sampler fix (A1/A4). **غير مؤكد** for Strikeforce until a log shows the colour target and colour offset of our shadow pass.

  3. **`0032-gt6-zeta-read-as-argb-texture-stencil-text.patch`** (2026-11-15 in the patch comment).
     - https://github.com/PrimeTimerer/Project-Grand-Tourer-Advanced/blob/main/patches/0032-gt6-zeta-read-as-argb-texture-stencil-text.patch
     - What it fixes: GT6 menu text had no glyphs. The game draws strings into the stencil plane, then binds the **same zeta as an A8R8G8B8 texture** (linear, remap 0xAAFF, every channel from B). D24S8 read that way is A=depth 23-16, R=15-8, G=7-0, B=stencil. Guest memory there is empty because the stencil lives only in the host depth resource, so every string was fully transparent.
     - The fix is a compute pass that packs both planes into an R8G8B8A8 view with the bind's remap, refreshed when the zeta is drawn or cleared. `LD_STENCIL_VIEW=0` turns it off.
     - This is **not** the known shadow-compare fix (R24_UNORM_X8 SRV + comparison sampler, border depth 1.0). It is the other way of binding a depth buffer: as a **colour copy**. That matches the wording of our 0xB0 maps at 0x3A0000 ("bound as RGBA colour copy with ComparisonFunc NEVER"). If the terrain shader samples t1 as a colour texture (alpha test) rather than a shadow compare, this packing may be what is missing. If it is a compare, fix 1780 remains the right one. **غير مؤكد** which of those Strikeforce actually does on the terrain draws.

  4. **`0024-depth-resolve-gpu.patch`** (2026-11-13 in the patch comment).
     - https://github.com/PrimeTimerer/Project-Grand-Tourer-Advanced/blob/main/patches/0024-depth-resolve-gpu.patch
     - NV3089 scaled blit out of a depth buffer that the renderer keeps only on the GPU, into a colour buffer (used in GT6 for depth of field). Guest memory was empty, so the composite treated every pixel as out of focus. The blit is drawn on the GPU from the zeta's R32F snapshot, packing D24 as RGB with A=0, then the live colour surface serves later texture lookups. `LD_DEPTH_RESOLVE=0` turns it off.
     - Same "GPU-only depth, colour read sees nothing" class as 0032. Useful if we later see NV3089 copies of the shadow map or the scene depth. **غير مؤكد** for the current village/snow frames.

  5. **`0080-gt6-polygon-offset-rounded-without-dynamic-bias.patch`** (closes their issue #23, 2026-11-26 19:55 Kuwait time).
     - https://github.com/PrimeTimerer/Project-Grand-Tourer-Advanced/blob/main/patches/0080-gt6-polygon-offset-rounded-without-dynamic-bias.patch
     - https://github.com/PrimeTimerer/Project-Grand-Tourer-Advanced/issues/23
     - On devices that do not offer `ID3D12GraphicsCommandList9` dynamic depth bias (RTX 3080, GTX 1650 SUPER in their reports), every distinct polygon-offset value became a new pipeline state. After three championship races the PSO cache hit `MAX_PSOS` (32768) and further draws were dropped: the **track disappeared first**. The patch rounds factor/units away from zero to 5 mantissa bits (3 bits after 3/4 of the cache is full), and keeps exact values only with `LD_BIAS_EXACT=1`. Dynamic bias stays the first choice when the device offers it.
     - Maps to survey B2 (our vtable path never decodes polygon offset 0x0A68/0x0A78/0x0A7C). Not a white-ground cause by itself, but if we add polygon offset we must not put the raw floats in the PSO key. Also a reminder that a full PSO cache can make terrain vanish.

  6. **`0079-gt6-light-cube-test-switches.patch`**: A/B diagnostics only (`LD_CUBE_FACES_BLINK`, richer light-diag lines). Not a fix.

  7. Nearby, lower priority: **`0026-hair-coverage-cubemap.patch`** first wires polygon offset 0x0A68/0x0A78/0x0A7C into the D3D12 rasterizer (0080 then stops the PSO table filling up) and emulates alpha-to-coverage in the fragment shader when 0x1D7C bit 0x10 is set on a single-sample target (https://github.com/PrimeTimerer/Project-Grand-Tourer-Advanced/blob/main/patches/0026-hair-coverage-cubemap.patch). **`0077-gt6-end-without-begin-draws-nothing.patch`** (same commit as 0078): an END with no BEGIN draws nothing, as on the hardware; without it the previous immediate group was redrawn with the wrong vertex layout (https://github.com/PrimeTimerer/Project-Grand-Tourer-Advanced/blob/main/patches/0077-gt6-end-without-begin-draws-nothing.patch). No patch in the set that was searched decoded 0x1738 / 0x173C (vertex base) or 0x0380-0x0388 (depth bounds).

- Other open GT6 issues worth knowing, not already fixed above: #18 "weird lighting / strange shadows in the car's lighting" (open, 2026-11-25). Issue #10 (rear-view mirror flicker) was fixed by patch 0068 in commit `7c1c9e88`.
- **Not upstreamed** after e85647a.

### 2. MotorStorm: Pacific Rift (papand7)

- Repo: https://github.com/papand7/Motorstorm-PacificRift-Recompilation (main). GitHub licence field is "Other" / NOASSERTION. There is **no project LICENSE file** at the root, only `THIRD_PARTY_LICENSES.md`. The README credits ps3recomp (MIT) and third-party tools, and does not grant a licence for the port's own files. **Treat as all-rights-reserved: idea only, do not copy code.**
- Public repo (the description still says "Private"). 28 stars. Created 2026-11-03; last push 2026-11-26 21:39 Kuwait time (start-up timeout merge). Player-facing README published 2026-11-23.
- Renderer of the public build: **Vulkan** (Enhanced lighting, optional FSR, "Shadows" row). A D3D12 investigation tree also exists in their docs from October.
- ps3recomp pin cited in THIRD_PARTY_LICENSES.md: `0fe7dbf` (v0.15.0, 2026-10-16), much older than e85647a. An integration doc walks a merge to v0.17.0 (`a6d76c8`, 2026-10-22), still before our HEAD.
- Relevant docs (ideas only):
  - https://github.com/papand7/Motorstorm-PacificRift-Recompilation/blob/main/docs/RSX_BLEND_STATE_INVESTIGATION.md (2026-10-23): independently records that **0x031C `SET_BLEND_COLOR` is not decoded and the D3D12 backend never calls `OMSetBlendFactor`**. Same gap GT6 0078 later implemented on live-draw, and the same gap our survey already listed for our path. Their garage-loading blend state did not use the constant, so they left it as a documented gap.
  - https://github.com/papand7/Motorstorm-PacificRift-Recompilation/blob/main/docs/WHITE_TO_BLACK_INVESTIGATION.md (2026-10-23): a **menu emblem** ramps to white then goes fully black. Leading hypothesis is auto-exposure / a luminance pass whose result never reaches guest memory (D3D12 targets have no readback). **Not the same as our missing terrain**, and not a shadow-map bug (they eliminated depth/stencil as the cause of the ramp).
  - README known issues: "the game's own shadows are used" in Original fidelity; "the new world shadows are not finished and are off"; some shadows can follow the camera in Enhanced; 60 FPS can show camera and shadow glitches. GRAPHICS_PLAN.md / Enhanced work is new lighting, not a repair of the RSX compare path. A 2026-11-23 commit turns Enhanced "tile shadows" off unless `RSX_SHADOW_TILES_FORCE=1`.
- Nov 22-26 commits are launcher, settings, start-up, handheld, LAN, and Enhanced options. **No D3D12 shadow-compare or vertex-base (0x1738/0x173C) fix was documented.**
- **Not upstreamed** after e85647a.

### 3. Killzone HD — Project Vekta (Gustavo Morinaga)

- Repo: https://github.com/gustavomorinaga/project-vekta (main). MIT. 76 stars. Vulkan, Linux and Windows. Pinned in the README at ps3recomp v0.19.0 plus `port/patches/`. Created 2026-10-30; last push 2026-11-26 20:48 Kuwait time. Release v0.7.0 on 2026-11-24.
- Already covered in the survey above: docs pointed at upstream shadow PRs, with no separate D3D12 shadow fix (this port is Vulkan). Rechecked for this add-on.
- New frame-map of Levels 1, 4, 7, 8 and 11 (commit `c5a44d96`, 2026-11-14 01:46 Kuwait time, UTC+3: https://github.com/gustavomorinaga/project-vekta/commit/c5a44d96bdf406264e570e47694add3f9450f632) states **there are no shadow maps in those five levels**. Docs: https://github.com/gustavomorinaga/project-vekta/blob/main/docs/dev/frame-map.md — so this title, in the captured levels, does not exercise shadow-map sampling.
- Patch 2076 (commit `b57b005d`: https://github.com/gustavomorinaga/project-vekta/commit/b57b005dd7f570f8fb9f5cfcddfa20e302a6ec32): a depth target read as A8R8G8B8 now carries the stencil byte (Vulkan depth-pack compute). Same bit-cast idea as GT6 0032 / our A5, for glow, not shadow compare.
- https://github.com/gustavomorinaga/project-vekta/blob/main/docs/KNOWN_ISSUES.md (last checked 2026-11-11) has no open "wrong shadows / white ground" item. Closest new note: **white and black blotches on some foliage** in Level 6 at 3440x1440 and FOV 120, seen once, "as if their alpha test or blending went wrong", not yet investigated. **غير مؤكد** whether that is the same class as our missing alpha-tested terrain.
- features.tsv (checked 2026-10-30, still current in the tree) lists campaign graphics as working (MLAA, glow, motion blur) and does not list a remaining shadow-compare defect.
- **No new fix to port. Not upstreamed after e85647a.**

### 4. Yakuza Kenzan (IvanBarbosaFilho)

- Repo: https://github.com/IvanBarbosaFilho/Yakuza-Kenzan-Recomp (main). Created 2026-11-24 19:24 Kuwait time; last push 2026-11-26 17:28 Kuwait time. 51 stars. **Vulkan.** Beta: the game boots and plays.
- Licence: GitHub licence field is empty and there is **no root LICENSE**. `engine/LICENSE` is MIT (copyright 2026 Ned Heller / sp00nznet). The README says the engine comes from ps3recomp through the inFAMOUS 2 port's fork (https://github.com/SamiEnazi/infamous2-port), with Kenzan's changes, and is MIT. The launcher and packaging have no stated licence. **Reuse only `engine/` MIT code with credit; treat the rest as all-rights-reserved. Prefer the inFamous 2 findings already in section A3 over copying this fork.**
- Issues search for shadow/ground/depth/white/dark returned only #5 (black screen and loud audio on boot, closed 2026-11-26). No documented shadow-compare or white-terrain fix.
- **Not upstreamed** after e85647a.

### 5. 3D Dot Game Heroes — Cubic.Heroes (irnutsmurt)

- Repo: https://github.com/irnutsmurt/Cubic.Heroes (main). **GPL-3.0** (LICENSE and README). 86 stars. Vulkan. US disc BLUS-30490. Created 2026-10-30; last push 2026-11-26 20:55 Kuwait time. Beta 0.2.0-beta.5.
- **Describe only. Do not copy project code.** The README still lists `patches/ps3recomp/` as MIT (the upstream recompiler). That label is **غير مؤكد** as a reuse grant once the files live in a GPL-3.0 repository; we do not copy them.
- Known issues (README): on AMD graphics "a few shadows and floor reflections differ slightly from the reference captures (faint; nothing missing or misplaced); being investigated."
- Earlier commit `8d93b9de` (2026-11-06 03:37 Kuwait time, UTC+3): https://github.com/irnutsmurt/Cubic.Heroes/commit/8d93b9deacbeedbba1de19f89594374e8ea0b398 — **idea only, no code quoted.** A draw-by-draw compare showed the native shadow map was never cleared: the shadow pass clears depth and stencil inline at its start, and those clears were not applied with the next draw. After carrying the clears, the scene-target difference in the River scene fell from 89.8% to 6.9% of pixels. A possible extra cause if our 1024² 0xB0 map is also left uncleared; it does not replace the R24 comparison-sampler wiring. **غير مؤكد** for Strikeforce.
- **Not upstreamed** after e85647a.

### 6. PlayStation All-Stars (samuelMadureira23)

- Repo: https://github.com/samuelMadureira23/allstars-port (master). MIT. D3D12. 29 stars. Last push 2026-11-26 14:21 Kuwait time.
- Already covered in the survey above: docs had nothing relevant to shadow, depth, attribute, fog or terrain bugs. Rechecked: the only commit since 2026-11-22 is `0cf997a` (2026-11-26), a README update to v0.6 (mouse and keyboard, Xbox icons, setup wizard, intro movie, fast loading). **No new graphics fix.**
- **Not upstreamed** after e85647a.

### Top 3 applicable fixes (ranked)

All three are from GT6, MIT, with credit to PrimeTimerer / Project Grand Tourer Advanced. None is in upstream after e85647a. Port the idea onto whichever D3D12 path Strikeforce actually runs (live-draw vs vtable: غير مؤكد); do not paste a live-draw patch onto the vtable backend as-is.

1. **Blend constant colour (0x031C, and 0x037C for FP16 targets) + `OMSetBlendFactor`.** Direct match for the white-ground suspect already listed in B2, independently confirmed as unimplemented in MotorStorm's D3D12 notes (idea only). GT6 shows the default (1, 1, 1, 1) turns constant-colour blends into a full-white add. Link: https://github.com/PrimeTimerer/Project-Grand-Tourer-Advanced/blob/main/patches/0078-gt6-blend-constant-colour-light-cubes.patch — commit: https://github.com/PrimeTimerer/Project-Grand-Tourer-Advanced/commit/42dbef1981fe2ef6ea839ee9d3e94081d1574835 — **LIKELY for lighting/blend; غير مؤكد as the cause of the missing terrain.**

2. **A depth-only shadow pass must not mark a colour surface as drawn (GT6 0068).** Directly about a 1024² shadow-map pass with no colour target, on the same D3D12 live-draw files. Complements, and does not replace, the R24 comparison-sampler fix from the earlier survey (A1/A4). Link: https://github.com/PrimeTimerer/Project-Grand-Tourer-Advanced/blob/main/patches/0068-gt6-surface-without-colour.patch — commit: https://github.com/PrimeTimerer/Project-Grand-Tourer-Advanced/commit/7c1c9e8875aa6032b4d5653629c933d3dee2222c — **غير مؤكد for Strikeforce until the shadow pass's colour target and colour offset are logged.** Runner-up on the same theme: 0032/0024 (depth bound as an A8R8G8B8 colour texture, plus the NV3089 GPU depth-resolve blit) — use only if t1 is a colour fetch, not a zfunc compare: https://github.com/PrimeTimerer/Project-Grand-Tourer-Advanced/blob/main/patches/0032-gt6-zeta-read-as-argb-texture-stencil-text.patch and https://github.com/PrimeTimerer/Project-Grand-Tourer-Advanced/blob/main/patches/0024-depth-resolve-gpu.patch

3. **Polygon-offset handling that does not explode the D3D12 PSO cache.** If we decode 0x0A68/0x0A78/0x0A7C (also listed in B2; first wired in 0026), copy the idea of dynamic depth bias when the device offers it, otherwise quantise the offset so draws are not dropped (GT6's track vanished after the cache filled). Link: https://github.com/PrimeTimerer/Project-Grand-Tourer-Advanced/blob/main/patches/0080-gt6-polygon-offset-rounded-without-dynamic-bias.patch — commit: https://github.com/PrimeTimerer/Project-Grand-Tourer-Advanced/commit/18c899cc50444e69d0664299ec15a2d82d19a5a5 — issue: https://github.com/PrimeTimerer/Project-Grand-Tourer-Advanced/issues/23 — useful when we implement polygon offset; not a stand-alone white-ground fix.

What this does **not** change: the first job for the dark faces remains wiring the already-known compare path (survey A1/A3, fix 1780). None of these new ports published a better D3D12 version of that R24_UNORM_X8 + comparison-sampler recipe.
