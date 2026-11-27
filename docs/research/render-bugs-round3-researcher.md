# Strikeforce (BLUS30471) render bugs, round 3 (researcher)
Date: 2026-11-26, 14:45 (UTC+3). This is a research note. Nothing was run on Saud's PC.
Pins: ps3recomp master e85647a33ce5f9391788f0e3f52ab395a7fe6a89 (box clone), RPCS3 0ca5eb0efe50ec4e8aa07892ab86d57842246eb4.
Tags: KNOWN = read at the pinned SHA. ASSUMED = inference or an outside suggestion that is not yet checked. VERIFY = needs a run or log on Salem's build.
No GPL code is copied here. RPCS3 is only described.
Caveat on everything below (VERIFY): Salem's tree may carry local patches on top of master, so each "ps3recomp does X" applies to master e85647a.

## 0. Corrections to the brief
- KNOWN: vertex type 7 is UB256, not CMP. RPCS3 gcm_enums.h L1144-1150: S1=1, F=2, SF=3, UB=4, S32K=5, CMP=6, UB256=7. The parent cross-checked this against the SDK table on burnout.wiki and against RPCS3 d3d12 get_vertex_attribute_format, which maps UB256 to R8G8B8A8_UINT.
- KNOWN: 0x0A00-0x0A1C are not viewport scale/offset (RPCS3 gcm_enums.h L636-641). The registers there are:
  - 0x0A00 VIEWPORT_HORIZONTAL
  - 0x0A04 VIEWPORT_VERTICAL
  - 0x0A0C POINT_CENTER_MODE
  - 0x0A1C ZCULL_SYNC
  Viewport OFFSET is 0x0A20-0x0A2C and SCALE is 0x0A30-0x0A3C.
- KNOWN: 0x1D78 is SET_ZMIN_MAX_CONTROL. See section 4.

## 1. Vertex types (UB256 / CMP / SF / byte order)
RPCS3 behaviour (KNOWN):
- RSXVertexFetch.glsl L77-78: per-type element size and scale. UB256 has scale 1, so its values stay 0..255.
- L122: single-byte types ignore the byte swap.
- L127-133: CMP is X11 Y11 Z10, sign-extended and normalised, with W = 1.
- L115-120: SF goes through unpackHalf2x16.
- L138-141: a missing W becomes 1.
- rsx_utils.cpp L387-433: UB256 requires size 4.

ps3recomp legacy D3D12 path (KNOWN):
- read_vp_vertex (rsx_d3d12_backend.c L6519-6530) decodes every attribute on the CPU into float4 with rsx_fetch_attrib (rsx_vertex_fetch.c).
- UB256 (L116-118) becomes float(byte), unnormalised, which matches RPCS3.
- UB (L88-90) is /255.
- CMP (L100-114) matches RPCS3 apart from rounding (/1023 and /511 against RPCS3's shift then /32767).
- SF (L84-86) is a big-endian half. Denormals are flushed to 0, which is a tiny difference.
- F, S1, S32K and CMP all read big-endian.
- On this path the outside reviewer's points (b) BE byte swap and SF are already handled. A UINT DXGI format is never involved, because the shader receives floats.

UB256 decoded as UNORM (the parent's question):
- If some path divided UB256 by 255, a value meant as 0..255 (bone index, colour×255, or a count) would collapse into 0..1.
  - As a bone or palette index, every vertex would read matrix 0 or 1, giving collapsed or stretched geometry. ASSUMED.
  - As a colour that the shader later multiplies by 1/255, the result would be near black. ASSUMED.
- Where the risk lives (KNOWN): rsx_vertex_formats.h L121-125 maps UB256 to R8/R8G8/R8G8B8A8_UINT. That header is used by rsx_draw_engine.c, rsx_live_draw.c and rsx_vertex_compact.c, not by the legacy CPU fetch.
- On those paths, a UINT input-layout element feeding an HLSL float input is a component-type mismatch. ASSUMED that this reads as undefined or garbage; VERIFY with the D3D12 debug layer if those paths are ever enabled.
- Size 3 has no case in that switch (L121-125), and SF has no size-3 case (L106-110) (KNOWN). It does not matter on the legacy path.

New difference found (KNOWN):
- rsx_vertex_fetch.c L42 returns the constant register value (vertex_data4f) when an attribute has stride == 0.
- RPCS3 (RSXDrawCommands.cpp L175-179) treats an enabled array with stride 0 as single_vertex: it reads one element from memory and uses it for every vertex.
- RPCS3 decides "enabled" by size > 0 (L106-116). ps3recomp does the same (rsx_commands.c L344).
- So any per-draw constant attribute that the game supplies as a stride-0 array (colour, normal, tint) gets the wrong value in our port. ASSUMED that this can explain the white near ground and the dark buildings.
- Check: VP_ATTRS=1 (rsx_d3d12_backend.c L6590+) and look for any enabled attribute with stride=0 on the ground or building programs.

## 2. Alpha test (grass squares)
RPCS3 (KNOWN):
- 0x0304 ALPHA_TEST_ENABLE, 0x0308 ALPHA_FUNC, 0x030C ALPHA_REF (gcm_enums.h L583-585).
- The test is emitted as a discard in RSXROPEpilogue.glsl L34-47. It runs on the final col0.a, after the sRGB, rounding and fp16 export steps, and runs even when there is no colour output.
- Function index 0..7 is never/less/equal/lequal/greater/nequal/gequal/always (RSXFragmentPrologue.glsl L136-150). to_comparison_function ORs in 0x200, so both 0x4 and 0x204 mean GREATER (gcm_enums.h L1431-1437).
- The ref scale depends on the surface format (rsx_methods.h L744-756, rsx_decode.h L2565-2587):
  - RGBA8-class surfaces: (ref & 0xFF)/255.
  - W16Z16Y16X16: the low 16 bits as a half.
  - X32 or W32: float bits.
- The function always goes into rop_control (RSXDrawCommands.cpp L745-746). The ref goes into the fragment context (L779).

ps3recomp legacy D3D12 at e85647a (KNOWN):
- alpha_ctl is packed per draw (L7334-7338, L7467-7471, L7643-7647) and written to b1[16..18] (L3517-3530).
- No shader the legacy backend compiles reads it:
  - The string rsx_alphatest appears only in comments (L77, L3517) and docs/DIAGNOSTICS.md L488.
  - rsx_fp_decompile only declares a b1 cbuffer in the buffered mode (rsx_fp_decompiler.c L1394-1403).
  - rsx_d3d12_backend.c never calls rsx_fp_apply_alpha_test or rsx_fp_apply_alpha_test_buffered. The callers are rsx_draw_engine.c L2574, rsx_live_draw.c L5001/L5020 and rsx_vulkan_backend.c L1360.
- Result: on the legacy backend, alpha test is currently a no-op. The [ALPHATEST] log line prints, but nothing is discarded. This matches grass drawing square backgrounds with GREATER.
- The existing helpers are ready to use:
  - rsx_fp_alpha_ref(raw, surface_fmt) (L1538-1550) gives the same per-format ref scaling as RPCS3.
  - rsx_fp_apply_alpha_test(hlsl, size, func, ref) (L1573-1613) inserts `if (!(out.a OP ref)) discard;` before the return, using MRT target 0's alpha.
- Things to fix with it (KNOWN gaps):
  1. alpha_ctl keeps only ref & 0xFF, which is wrong for FP16 or FP32 targets. Keep the raw 32-bit ref plus the surface format.
  2. rsx_fp_apply_alpha_test only accepts func 0x200..0x207 (L1578). A raw 0..7 value is treated as ALWAYS. RPCS3 accepts both forms. Mask with `func | 0x200` first.
  3. The PSO cache key in vp_get_fp_pso (L2374-2386) has no alpha field. Once discard is baked in, enable, func and ref (or ref passed in a cbuffer) must be part of the key. Otherwise a cached variant without discard is reused, which is reviewer point (c) and is KNOWN to apply.
- Texture-side alpha (reviewer point (c)):
  - KNOWN: guest-memory textures get their remap through rsx_remap_to_d3d (rsx_d3d12_backend.c L5070-5074). B8 (0x81) is forced to mapping 0x1000.
  - ASSUMED: D3D12_ENCODE_SHADER_4_COMPONENT_MAPPING(0,0,0,0) = 0x1000, which means R in all four channels, so B8 alpha = R.
  - VERIFY: G8B8 and DXT1 1-bit alpha against RPCS3. If the grass texture is DXT1, transparent texels decode to alpha 0, which a GREATER test discards once the test is wired.

## 3. The 160x90 post target at 0x0B010000 (dark buildings)
RPCS3 (KNOWN):
- texture_cache.h fast_texture_search (L2512+) first checks whether the address is a bound ROP target (cyclic reference, with a texture barrier). It then looks up surfaces by memory-range overlap (get_merged_texture_memory_region), not by exact offset.
- texture_cache_helpers.h process_framebuffer_resource_fast (L655+):
  - Takes the texture's own width and height.
  - Applies resolution scaling.
  - Clips or copies when the texture size differs from the surface size.
  - Bitcasts (force_convert) when the texture format is incompatible with the surface format.
  - Resolves depth and colour conflicts.
  - Passes the texture remap through to the view.

ps3recomp legacy (KNOWN):
- off_rt_find (L3758-3764) matches the exact offset only. There is one slot per offset, whatever the size.
- off_rt_get (L3768-3828):
  - If the same offset arrives with a different w, h or format, it waits for the GPU, releases the resource and re-creates it, then fills the new resource from guest memory (L3830+).
  - w = 0 or h = 0 falls back to the display size (L3771-3772).
- The per-frame pre-pass (L4868-4876) calls off_rt_get for every draw's target in record order. If 0x0B010000 is a target at two sizes in one frame, the last size wins for the whole frame, and the slot is rebuilt from guest memory every frame. The source comment at L5329-5331 says the same: "slots share offsets at different sizes".
- An RT used as a texture (L5035-5040) binds an SRV of the whole RT resource with DEFAULT_SHADER_4_COMPONENT_MAPPING:
  - the texture's remap is ignored;
  - no sub-rectangle or scale is applied;
  - the format is the RT's DXGI format, not the texture's.

Ways this comes out dark (ASSUMED until logged):
1. The slot is re-created each frame because two sizes alias 0x0B010000, so the scene reads guest-memory content, likely zeros.
2. Read-before-write: if the scene reads last frame's 160x90 result (typical for exposure or luminance feedback), any recreate or clear loses it.
3. The producer writes somewhere else (a different offset or MRT slot, or a display-size fallback when rt_w = 0), so the 160x90 slot is never written.
4. Format mismatch: an FP16 surface read through an ARGB8 texture descriptor. RPCS3 bitcasts; we read raw floats.
5. Remap ignored: for example, the shader expects luminance in .a or .r after a remap.
6. Exposure clamp: a luminance of 0 drives exposure to its floor (reviewer point (e)).

Reviewer's barrier point: the RT-to-SRV transition goes through off_rt_transition (L3969). VERIFY that the transition happens before the sampling draw within the same command list.

## 4. 0x1D78 = SET_ZMIN_MAX_CONTROL (the big shape at the top)
- KNOWN: RPCS3 rsx_decode.h L624-654 decodes the bits as:
  - bits 0-3 depth_clip_enabled
  - bits 4-7 depth_clamp_enabled
  - bits 8-11 depth_clip_ignore_w
- KNOWN: RPCS3 clamps (no near/far clip) only when clamp is set or clip is off (RSXDrawCommands.cpp L763).
- KNOWN: the reset value is 1, which means clip on (ps3recomp rsx_dispatch.c L175-179, citing RPCS3). rsx_draw_engine.c L488-499 already handles this for the new engine.
- KNOWN: the legacy guest PSO is zero-initialised (rsx_d3d12_backend.c L2670, `pd = {0}`) and never sets DepthClipEnable. Every guest draw therefore runs with depth clip OFF, whatever 0x1D78 says. The legacy backend never reads 0x1D78.
- ASSUMED: geometry in front of the near plane or past the far plane, which RSX would cut, is drawn with clamped depth. A large near-camera or past-far mesh then covers part of the screen, which fits (b).
- Note: in the olive-world round, depth clip was ruled out as the cause of that bug only. It is still a candidate for (b).
- Fix shape: DepthClipEnable = ((z & 0xF) != 0) && ((z & 0xF0) == 0), with the value added to the PSO key.
- Depth range (reviewer point (d)): VERIFY that the VS epilogue maps RSX clip z to D3D's 0..w. A GL-style -1..1 z would make D3D clip or clamp half of the depth range.

## 5. Timeline arithmetic (Salem's numbers only)
- Boot to stage is 135 s, of which 75 s is idle on PRESS START, so about 60 s once the idle is cut. KNOWN arithmetic.
- Let T be the observation time per run (unknown) and N the number of parallel instances (2 work now).
- Throughput is N×3600/(60+T) runs per hour, against 3600/(135+T) runs per hour today.
  - T = 30 s: about 24/h today, against 80/h with N = 2.
  - T = 60 s: about 18/h today, against 60/h with N = 2.
- Build time is excluded and unknown.

## 6. Outside reviewer points (ASSUMED until checked)
- (a) Audit the 72 unhandled NIDs for output pointers that a fake CELL_OK leaves unwritten, sorted by call count. Log the pointer args and diff the memory before and after.
- (b) BE swap on 16/32-bit attributes: KNOWN handled on the legacy CPU fetch (section 1).
- (c) Alpha test on the final alpha, plus the cache key: KNOWN gap (section 2).
- (d) Winding vs the y-flip: VERIFY. Run once with culling off. If the white or missing ground changes, check FRONT_FACE inversion when the projection flips y. The legacy cull key is rsx_cull_key, packed into dr->cull.
- (e) Post target: section 3.
- (f) Crash dumps:
  - WER LocalDumps and gflags page heap change the registry or system on Saud's PC. They NEED SAUD'S APPROVAL and should not be enabled by default.
  - Prefer the in-process crash.inc handler. VERIFY that it exists in Salem's tree; not checked here.
