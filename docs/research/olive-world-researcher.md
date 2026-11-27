# Olive world: why the ground, sky and village buildings are missing, and the lighting washed out

2026-11-26, ~13:10 UTC+3. Research only; nothing was run, and Saud's PC was not touched.

Pins:
- **P** = ps3recomp e85647a33ce5f9391788f0e3f52ab395a7fe6a89. `P:` means `https://github.com/sp00nznet/ps3recomp/blob/e85647a33ce5f9391788f0e3f52ab395a7fe6a89/`
- **R** = RPCS3 0ca5eb0efe50ec4e8aa07892ab86d57842246eb4. `R:` means `https://github.com/RPCS3/rpcs3/blob/0ca5eb0efe50ec4e8aa07892ab86d57842246eb4/rpcs3/`

**Correction first:** the subchannel-1 lead from 11:57 and 12:23 was wrong for this game (Salem, 12:32). The note is now at the top of colormask-researcher.md, github-tools-researcher.md and innovative-ideas-researcher.md.

## What the screenshots show (looked at this turn)

| Shot | Switches | Visible | Missing |
|---|---|---|---|
| p71_175 (62 FPS, 875 draws) | none | Zhao Yun and an NPC, the HUD, the tutorial box, grass tufts in the distance, the big light-shaft quad (opaque, grey, very bright) | the ground, the sky, the buildings, the trees; the screen is flat olive |
| p71_grid **t=150 s** | none | **distant green hills and the sky are visible** | the near ground (olive) and the buildings |
| p71_grid t=175 / 195 s | none | as p71_175 | the hills and sky are **gone** as well |
| p62_175 (104 FPS, 875 draws) | SF_COMPOSITE | the buildings, trees and well (dark), and the grass | the ground and sky (olive) |
| p61_180 (0.27 FPS) | CMASK_FORCE | the buildings, the ground (whitish), the trees and sky, translucent light shafts, all of it dark | nothing obviously |

KNOWN: these are visual observations only.

The facts that matter for the hypotheses:
1. The world exists as draws, because CMASK_FORCE and SF_COMPOSITE each make parts of it appear.
2. It *disappears over time*: hills visible at 150 s, gone at 175 s.
3. The characters and the HUD always draw.
4. Translucent things look opaque or too bright: the light shaft.

## Facts in the D3D12 backend that bear on this (all KNOWN at P)

- **Per-frame vertex budget.**
  - `MAX_VERTICES 393216` (P:libs/video/rsx_d3d12_backend.c#L63). Each VP vertex is 16 float4 = 256 bytes in a double-buffered upload buffer (#L1353-L1364).
  - A draw that doesn't fit is **truncated** to the room left (`count = maxv - (maxv % 3)`, #L6737-L6743). Every later draw in the frame then finds no room and is dropped as `upload_empty` (reasons table #L4550-L4558).
  - `VBFULL=1` logs `[VBFULL] fp=… wanted N verts, room for M` (#L6739, #L7008).
  - Salem has already seen `upload_empty` climbing (1768, then 32816).
- **Display passes don't use the guest's depth surface.**
  - A guest depth surface (OffDS) is created only for a draw with `rt_off || no_color` (#L4876-L4877).
  - A draw is bound to its OffDS only when `want >= 0 || no_color` (#L5338-L5339).
  - A draw into the display surface (`rt_off == 0`, which Salem measured in-stage) uses **one shared depth buffer**. That buffer is **cleared to 1.0 every time the pass switches targets** (#L5385-L5388; the comment at #L5440-L5442 says so).
  - So depth written by a display pass never reaches the guest zeta surface, and is lost at the next target switch.
  - By contrast, RPCS3 binds depth by address for every draw (R:Emu/RSX/Common/surface_store.h#L916, #L1081, #L1115).
- **Depth-clear decode.**
  - P always decodes the clear depth as Z24: `(zstencil_clear_value >> 8) / 0xFFFFFF` (P:libs/video/rsx_commands.c#L678).
  - RPCS3 uses the low 16 bits for Z16 surfaces (R:Emu/RSX/Core/RSXCoreRenderer.cpp#L215-L220, R:Emu/RSX/rsx_decode.h#L3403-L3419). It also handles the float depth formats (R:Emu/RSX/Common/TextureUtils.cpp#L1855-L1866).
  - Every guest PSO uses `DSVFormat = D24_UNORM_S8_UINT` (P:rsx_d3d12_backend.c#L2723).
- **Depth clip.**
  - The guest-FP PSO starts from `pd = {0}` (#L2670), so `DepthClipEnable` is FALSE: our build never clips on z.
  - RPCS3 enables clamping when `depth_clamp_enabled || !depth_clip_enabled` (R:Emu/RSX/VK/VKGSRender.cpp#L284, R:Emu/RSX/GL/GLDraw.cpp#L95).
  - So z-clip can only make **extra** geometry appear here, never make it vanish.
  - P has no `SET_ZMIN_MAX_CONTROL` (0x1D78) handling (git grep).
- **Reports and z-cull.**
  - `GET_REPORT` type 1 (ZPASS) writes 0xFFFF, which means visible, and every other type writes 0 (P:libs/video/cellGcmSys.c#L2376-L2400). Local-location reports (DMA 0xFEED0000, the default) go to a **host-side array only** (`s_report_data`, #L382-L392), readable only through `cellGcmGetReport*`.
  - **Strikeforce imports none of the report readers.** Its 23 cellGcmSys imports include `cellGcmGetLabelAddress` and `cellGcmSetZcull` (`EBOOT.imports.json`).
  - In RPCS3, local reports live in guest memory at `label_addr + 0x1400 + i*0x10`: `RsxReports{u32 semaphore[1024]; RsxNotify notify[64]; RsxReport report[2048]}` (R:Emu/Cell/lv2/sys_rsx.h#L112-L132, R:Emu/Cell/Modules/cellGcmSys.cpp#L204-L212).
  - RPCS3 returns −1 for ZCULL_STATS/1/2, and 0 or 0xFFFF for STATS3 (R:Emu/RSX/RSXZCULL.cpp#L445-L454). P returns 0 for all of them.
  - `SET_RENDER_ENABLE` (0x1E98, conditional rendering) is not implemented in P (git grep). That can only add draws, never remove them.

## Hypotheses, ranked by fit to the evidence

### H1. The per-frame vertex budget overflows now that a frame is the whole frame (best fit)

**Why it fits:**
- Before Salem's fix, the shadow-map clear split each real frame into several "frames", each with its own 393 216-vertex budget.
- Now one frame carries the shadow pass, the main pass and the effects, so the last draws in it are truncated or dropped.
- Large static world meshes are the biggest vertex consumers. Characters and the HUD survive if they come earlier, or (the HUD) through the non-VP `BasicVertex` path, which has its own buffer (#L6379-L6396).
- The "visible at 150 s, gone at 175 s" pattern fits a scene whose vertex count grows as more of the village streams in.
- `upload_empty` was already climbing.

ASSUMED, not measured. **VERIFY:** `D3D12_DROP_STATS_EVERY=60 VBFULL=1`. Expected if true: `upload_empty` > 0 every period in-stage, and `[VBFULL]` lines.

**Fix test:** raise `MAX_VERTICES` for one build, e.g. to 786432. KNOWN cost: the VP vertex buffer is 2 × N × 256 B, so 384 MiB of upload heap at 786 432. Check Salem's RAM and VRAM headroom before going further.

**Root fix (ASSUMED):**
- a smaller vertex record (16 float4 per vertex is the generic worst case);
- or flush or submit when the buffer fills, instead of dropping;
- or index instead of expanding.

### H2. Depth from display passes is lost: the prepass and EQUAL problem, or a later pass sees cleared depth (strong second)

**Why it fits:** CMASK_FORCE made the *whole* world appear, but **dark and unlit** (p61). That is what you see when a colour-masked depth pre-pass (cmask=0) gets its colour forced on: its fragment program isn't the lit one.

If the lit pass then draws with depth func EQUAL against the pre-pass depth, it fails wherever that depth was lost. And it is lost:
- display draws use the shared buffer;
- that buffer is cleared at every target switch (#L5385-L5388), e.g. pre-pass → shadow map → back to the display surface.

Characters (usually not pre-passed) and alpha-tested grass with LEQUAL still draw.

**VERIFY:**
1. `DEPTH_OFF=1` (#L2752). If the world appears, it is depth rejection.
2. `RSX_CAP=<frame>`: in manifest.txt, look for runs of `cmask=0` draws followed by the same `fp`/`n` with `cmask=F`.
3. Add `zs_key` to the manifest line (a 1-line local patch at #L1697-L1702) to see the depth func per draw. 0x202 or 0x203 = EQUAL/LEQUAL in the low bits (`rsx_zs_key`, #L2200-L2232).

**Root fix:** bind the guest's zeta surface for display draws too (`rt_off == 0 && zeta_off`), and stop the clear-on-switch for surfaces the guest owns. That is the RPCS3 model: surfaces keyed by address.

### H3. A full-screen pass reads the scene depth as a texture (fog or haze) and finds "far": olive = fog colour

**Why it fits:**
- In DW-style engines the clear colour usually *is* the fog colour (ASSUMED).
- If a fog or haze pass samples the guest zeta surface, it either finds no OffDS (display passes never create one, H2) or finds one that was only cleared to 1.0. Either way it reads "far" everywhere and paints full fog over whatever was drawn before it.
- Things drawn after it stay visible: characters, grass, the light shaft, the HUD.
- Fits "flat olive" exactly.

**VERIFY, cheapest discriminator first:**
1. `CLEAR_RGB=1,0,1` (#L6167). If the world area turns **magenta**, it is truly undrawn (H1/H2). If it stays **olive**, something *painted* olive over it (H3).
2. `RSX_CAP` manifest: a near-full-screen draw (`n=6` or `n=4`) whose `t0..t3` equals the frame's zeta offset (RTOFF log `zeta=0x…`, #L3718).
3. `DRAW_SKIP_TEX=<that zeta offset>` (#L4787). The world should reappear, unfogged.

### H4. Occlusion/visibility results are unreadable, so the world gets culled after a few frames

**Why it fits:**
- "Appears, then disappears" is the classic occlusion-query lag.
- The only things culled are what the engine tests: static world chunks, not characters or the HUD.
- If Strikeforce reads its ZPASS reports from report memory, computed from the label area it gets through `cellGcmGetLabelAddress` (it imports no report reader), it reads memory P never writes, i.e. 0, which means "occluded".

**Against it:** in p61/p62 the world was there with the same report code (ASSUMED that those runs had the same report path). So rank 4.

**VERIFY:**
- grep the log for `[GET_REPORT] type=` (printed by default, the first 6, #L2386).
- If type=1 with `dma=0xFEED0000` appears in-stage, H4 is live.
- **Test:** a local patch that also mirrors each local report into guest memory at `GCM_LABEL_GUEST_BASE + 0x1400 + idx*0x10` (the RsxReports layout from R:sys_rsx.h; facts only, no code).

### H5. Z16 clear decode / forced D24S8

**Why it could fit:** a Z16 surface cleared with `0x0000FFFF` (far, in Z16) decodes in P as `0xFF/0xFFFFFF`, which is about 0. Every LEQUAL draw on that surface then fails.

**Against it:** the characters would fail too if they share the surface. Weaker fit. ASSUMED.

**VERIFY:**
- log `SET_SURFACE_FORMAT` depth bits (`(fmt>>5)&7`: 1 = Z16, 2 = Z24S8; P uses the same field in `rec_zeta`, #L3679);
- log `ZSTENCIL_CLEAR_VALUE` in-stage (`[RSX] CLEAR_SURFACE` logs print the mask only, P:rsx_commands.c#L669-L676).

**Fix:** decode by format, as RPCS3 does.

### Rejected or low

- **Depth clip / ZMIN_MAX_CONTROL:** our PSO never clips on z (`pd={0}`, #L2670), so it can't be what makes geometry vanish. KNOWN.
- **Z-cull rejecting pixels:** neither P nor RPCS3 rejects pixels on z-cull (RPCS3's ZCULL code is reports only, R:Emu/RSX/RSXZCULL.cpp). KNOWN for RPCS3; for P, git grep shows no 0x1D84 handling.
- **Conditional rendering:** not implemented in P, so it can only *add* draws.

## The washed-out look (characters too bright, light shaft opaque)

Ranked; all ASSUMED:

1. **Missing post or tone-map composite.** The 6-vertex quad that samples 0x0B530000 (Salem, 11:57) is probably the tone-map or bloom composite. If the scene now goes straight to the display, or the quad samples a stale or empty slot, the result is an un-tone-mapped look.
   - P itself warns that slots share offsets at different sizes, so lookup by address alone is unsafe (#L5329-L5331).
   - **VERIFY:** `RTT_PASS=<n> RTT_VIEWRT=1` (#L4746-L4770) to view the scene RT just before the quad, and `RTT_DUMP=40` to list op order.
2. **Destination alpha on an X8 target.** RPCS3 treats X8 formats' alpha as 1 on read (colormask-researcher.md, R:Emu/RSX/color_utils.hpp#L300-L334). P maps the surface with no remap (`rsx_surface_dxgi`, P#L3748-L3756), so blending that uses DST_ALPHA or ONE_MINUS_DST_ALPHA sees whatever alpha was written.
   - That would make the light shaft (additive/alpha, normally translucent in p61) opaque.
   - **VERIFY:** `BLENDDBG=1` (#L2237, #L7361) on the light-shaft draw; check the `rt_fmt` of its target.
3. **sRGB or gamma.** RSX textures carry gamma bits (TEXTURE_ADDRESS bits 20-23). Ascension-R's `rsxcap_check.py srgb` reads exactly this from an `RSX_CAP` manifest (https://github.com/rigaz29/Ascension-R/blob/7c3201dd952adfc9ad2af6f8cb07ce52366d9810/scripts/rsxcap_check.py), but the `srgb=` field is in their fork only, so add it.

## Ordered checks for Salem (each one run, existing switches)

1. **`CLEAR_RGB=1,0,1`** → magenta = undrawn (H1/H2); olive = painted over (H3).
2. **`D3D12_DROP_STATS_EVERY=60 VBFULL=1`** → `upload_empty` > 0 or `[VBFULL]` lines confirm H1. Then do the MAX_VERTICES test build.
3. **`DEPTH_OFF=1`** → the world appears means depth rejection (H2/H5).
4. **`RSX_CAP=<in-stage frame>`**, read the manifest:
   - `cmask=0` draws followed by repeats (pre-pass, H2);
   - a full-screen draw sampling the zeta offset (H3);
   - the op order around the 6-vertex composite.
5. **Log check:** `[GET_REPORT] type=` and `[RTOFF] … zeta=` lines (H4, H5).
6. If H3: **`DRAW_SKIP_TEX=<zeta offset>`**. If washed out: **`RTT_PASS=<n> RTT_VIEWRT=1`** and **`BLENDDBG=1`**.
7. **Reference:** an RPCS3 Alt+C capture at the same spot, then `tools/parse_rrc.py`, to compare draw count and order against our manifest (github-tools-researcher.md #3).

Expected results above are ASSUMED until Salem runs them.
