# Strikeforce in-stage: colour mask, CMASK_FORCE at 0.27 FPS, upload_empty (2026-11-26, ~12:30 UTC+3)

> **CORRECTION 2026-11-26 12:32 (UTC+3), from Salem's in-stage measurements:** the subchannel-1 / NV0039 lead was **wrong for Strikeforce**. There are no subchannel-1 methods in the 3D range and no SET_OBJECT in the stream, and the in-stage cmask is 0x01010101. The register collision described below is real as a *class* of bug (envytools, PSL1GHT and Demon's Souls fix 141 are still correct), but it is **not** this game's cause. The real cause was a shadow-map clear with no colour target being treated as a frame start. For the remaining olive world, see olive-world-researcher.md.


Research only; nothing was run, and Saud's PC was not touched.

Pins:
- **R** = RPCS3 `0ca5eb0efe50ec4e8aa07892ab86d57842246eb4`. `R/` = https://github.com/RPCS3/rpcs3/blob/0ca5eb0efe50ec4e8aa07892ab86d57842246eb4/rpcs3/
- **P** = ps3recomp `e85647a33ce5f9391788f0e3f52ab395a7fe6a89`. `P/` = https://github.com/sp00nznet/ps3recomp/blob/e85647a33ce5f9391788f0e3f52ab395a7fe6a89/

## 0. Bottom line

1. **P decodes the 0x0324 mask the same way RPCS3 does for every legal value** (KNOWN, §1-§2). The byte order Salem guessed is right: B = bit 0, G = bit 8, R = bit 16, A = bit 24.
2. **The strongest lead is not the decode but *what gets written to 0x0324*.** P's FIFO walker treats **subchannel 1 as 3D by default** (KNOWN). libgcm's memory-to-memory engine NV0039 lives on subchannel 1, and **`NV0039_FORMAT` is method 0x2324 = subchannel 1 + 0x0324** (KNOWN, RPCS3 enum).
   - So every NV0039 transfer (`cellGcmSetTransferData`-style) would overwrite `COLOR_MASK`, along with `ALPHA_REF`, `BLEND_ENABLE`, blend factors, blend colour and equation, and `STENCIL_TEST_ENABLE`.
   - That it happens in Strikeforce is ASSUMED. VERIFY in one run (§4 check 1).
3. **0.27 FPS under `CMASK_FORCE=1` is a bug in the diagnostic itself** (KNOWN, §3). The forced mask is stored in the PSO cache entry, but the lookup uses the unforced mask. Every draw whose guest mask isn't 0xF therefore misses and runs a full decompile + `D3DCompile` + `CreateGraphicsPipelineState`.

## 1. RSX colour-mask encoding in RPCS3 (KNOWN, exact lines)

**`NV4097_SET_COLOR_MASK` = 0x0324, target 0.**
- Enum: `R/Emu/RSX/gcm_enums.h#L591`; `CELL_GCM_COLOR_MASK_B = 1<<0, G = 1<<8, R = 1<<16, A = 1<<24` (`#L293-L296`).
- Decoder (`R/Emu/RSX/rsx_decode.h#L3008-L3061`):
  - `color_b = bf_decoder<0,8,bool>`, `g = <8,8>`, `r = <16,8>`, `a = <24,8>`, so a channel is on if its **byte is non-zero**;
  - `color_write_enabled = value != 0`;
  - `is_invalid() = value & 0xFEFEFEFE`.
- **Invalid values are rejected.** `nv4097::set_color_mask` checks `is_invalid()` and **rolls the register back to the previous value** (`R/Emu/RSX/NV47/HW/nv4097.cpp#L340-L356`). So only bytes of 0x00 or 0x01 ever take effect.
- **Reset value is `0x01010101`** (`R/Emu/RSX/rsx_methods.cpp#L1021`). P resets it the same way (`P/libs/video/rsx_commands.c#L100`).
- A mask written with `cellGcmSetColorMask(R|G|B|A)` = 0x01010101, like Salem's menus, is the normal all-on value. Nothing special happens. Any other legal value (e.g. 0x00010101 = RGB with no alpha) just masks those channels.

**`NV4097_SET_COLOR_MASK_MRT` = 0x0370, targets 1-3.**
- Enum: `gcm_enums.h#L610`; bits `MRT1_A = 1<<4, R = 1<<5, G = 1<<6, B = 1<<7`, then MRT2 at bits 8-11 and MRT3 at bits 12-15 (`#L298-L309`).
- One nibble per target, `(value >> index*4)`, with bit 0 = A, 1 = R, 2 = G, 3 = B (`rsx_decode.h#L3063-L3095`). Target 0 never uses this register; it uses 0x0324 (`R/Emu/RSX/rsx_methods.h#L343-L401`).
- **Reset is 0** (`rsx_methods.cpp#L1175`). So in RPCS3, MRT targets 1-3 are **masked off until the game sets 0x0370**.

**Surface-format remap** (`R/Emu/RSX/Core/RSXCoreRenderer.cpp#L106-L137`, helpers in `R/Emu/RSX/Utils/color_utils.hpp`):
- **B8:** `get_b8_colormask` (`#L267-L273`): red = blue, then G, B and A are off. B8 is stored in the host R channel.
- **G8B8:** `get_g8b8_r8g8_colormask` (`#L196-L201`): red = blue, then B and A are off.
- **Then each channel is ANDed** with `get_write_output_mask(format)` (`#L300-L334`):
  - RGBA for A8R8G8B8, A8B8G8R8, the FP formats and **all X8/X1 formats**;
  - RGB for R5G6B5;
  - RG for G8B8;
  - R for B8 and X32.
- **X8 formats on read-back:** RPCS3 forces alpha to 0 or 1 when the target is later sampled. For example, `x8r8g8b8_o8r8g8b8` has swizzle {one, r, g, b} (`R/Emu/RSX/GL/GLRenderTargets.cpp#L21-L47`). This is a read-time remap, not a mask remap.

**Subchannel separation.** RPCS3's FIFO keeps the full method address including the subchannel bits: `m_command_reg = (m_cmd & 0xffff) + …` (`R/Emu/RSX/RSXFIFO.cpp#L67`). The 2D and transfer engines have their own register ranges:
- `NV0039_*` at 0x2000-0x2328, with **`NV0039_FORMAT = 0x2324`** (`gcm_enums.h#L753-L764`);
- `NV3062` at 0x6000, `NV309E` at 0x8000, `NV308A` at 0xA000, `NV3089` at 0xC000 (`#L767-L802`).

So in RPCS3 an NV0039 FORMAT write can never touch `COLOR_MASK`.

## 2. P's legacy D3D12 path vs RPCS3

**How P decodes it (KNOWN):**
- **0x0324:** stored raw (`P/libs/video/rsx_commands.c#L635-L640`). Converted at draw-record time with `R = bit 16, G = bit 8, B = bit 0, A = bit 24` into a D3D RGBA nibble (`P/libs/video/rsx_d3d12_backend.c#L7326-L7334`; same at `#L7459-L7466` and `#L7635-L7642`). That equals RPCS3 for every legal value.
- **Two differences**, neither of which can mask more than RPCS3 does:
  - P keeps illegal values instead of rolling them back, and tests only bit 0 of each byte.
  - P never decodes 0x0370. MRT 1-3 copy RT0's mask (`#L2704-L2722`). That writes *more* than RPCS3, not less.
- **No format remap:**
  - B8/G8B8/X8 surfaces all become `R8G8B8A8_UNORM` (`rsx_surface_dxgi`, `#L3748-L3756`), and the mask isn't remapped. A B8 target with mask = B would write host B, which RPCS3 puts in R. That only matters if Strikeforce renders B8/G8B8 targets (ASSUMED unlikely for the 1280x720 scene).
  - X8 targets keep whatever alpha was written instead of reading as 0/1. That can matter if the composite quad blends or alpha-tests with source alpha (ASSUMED; VERIFY the scene surface format, `rt_fmt` in `RTT_DUMP`).

**The likely bug: subchannel 1 goes into the 3D bank (KNOWN code, ASSUMED to be active in Strikeforce):**
- P's own comment says "libgcm binds: sub 1/6 = NV0039 (m2mf buffer copy)" (`P/libs/video/cellGcmSys.c#L1197-L1203`).
- Yet the walker sends subchannel 1 to `gcm_3d_method` unless `GCM_SUBCH1_2D=1`:
  - switch at `#L2917-L2918`;
  - fast path `#L2925-L2937`;
  - slow path `#L3087-L3088`;
  - the reason is in the comment at `#L2986-L3001` (Twisted Metal and Yakuza DS bind NV4097 there).
- `gcm_3d_method` strips to the NV4097 bank and calls `rsx_process_method` (`#L2356-L2370`).
- **Which NV4097 registers an NV0039 transfer on subchannel 1 would hit**, based on the NV0039 offsets at `R gcm_enums.h#L757-L764` with the subchannel stripped:

  | NV0039 method | lands on NV4097 |
  |---|---|
  | `OFFSET_IN` | 0x030C `ALPHA_REF` |
  | `OFFSET_OUT` | 0x0310 `BLEND_ENABLE` (non-zero, so blending turns on) |
  | `PITCH_IN` / `PITCH_OUT` | 0x0314/0x0318 blend factors |
  | `LINE_LENGTH_IN` | 0x031C `BLEND_COLOR` |
  | `LINE_COUNT` | 0x0320 `BLEND_EQUATION` |
  | **`FORMAT` (typically 0x00000101: in = 1, out = 1)** | **0x0324 `COLOR_MASK`**, decoded as B + G on, R and A off |
  | `BUFFER_NOTIFY` | 0x0328 `STENCIL_TEST_ENABLE` |

- **Effect:** every draw after a transfer, until the game's next explicit `SetColorMask` or blend setup, uses garbage mask and blend state.
- **Fits Salem's results** (ASSUMED): `CMASK_FORCE` "fixes" it, menus with fresh state look right, and in-stage draws (where data transfers happen between draws) lose colour.
- **Precedent:** PR #815 (open) describes the same class of bug for NV3062 on subchannels 2/3, which turned off alpha testing in Folklore. It fixes the draw engine only and keeps "1, otherwise → 3D" to match this walker (https://github.com/sp00nznet/ps3recomp/pull/815).

## 3. Why `CMASK_FORCE=1` runs at 0.27 FPS (KNOWN, code)

Everything happens in `vp_get_fp_pso` (`P/libs/video/rsx_d3d12_backend.c#L2322-L2788`):
- **Lookup** compares `vp_fp[i].cmask == cmask` using the **guest** mask passed in (`#L2373-L2386`).
- **Then** `CMASK_FORCE` sets `cmask = 0xF` (`#L2716-L2720`).
- **The new entry is stored with `cmask = 0xF`** (`#L2783`).

So for any draw whose guest mask isn't 0xF, the stored key never matches. Every such draw, every frame, does a full fragment-program decompile, `D3DCompile` and a new PSO (`s_perf_pso_miss++`, `#L2387`). The cache (`VP_FP_CACHE 2048`, `#L275`) also fills and evicts. That alone explains the speed drop, and it says nothing about the game.
- **Fix (local, one line):** apply the force *before* the lookup (top of `vp_get_fp_pso`, or at the call sites `#L5090`/`#L5475`), or store the unforced value.
- **Side note:** the forced mask also makes depth-only passes write colour (`#L2707-L2713` describes the shadow-map case). That costs bandwidth but isn't the 0.27 FPS.

## 4. Fast checks, in order

1. **Is subchannel 1 carrying NV0039 in the stage?**
   - Run with `GCM_OBJDBG=1` (SET_OBJECT handle per subchannel, `cellGcmSys.c#L2971-L2985`).
   - Also run `GCM_METHOD_HIST=5` (top (subchannel, method) pairs, `#L3030-L3045`) or `GCM_SUBCH_GATE=<file>`, touching the file in-stage (`[subch] 1 0x0324 = …`, `#L3018-L3021`).
   - Seeing `subch=1 … 0x030C..0x0328`, and/or a subchannel-1 handle different from subchannel 0's, confirms it.
2. **A/B: `GCM_SUBCH1_2D=1` without `CMASK_FORCE`.**
   - If ground, sky and Zhao Yun appear at normal FPS, the cause is confirmed.
   - Downside: if Strikeforce *also* puts NV4097 on subchannel 1, that state is dropped. Check 1 tells you which is the case.
   - **Proper fix (local):** route subchannel 1 by its `SET_OBJECT` handle, as PR #815 does for the draw engine. Or at minimum send methods 0x030C-0x0328 on subchannel 1 to the 2D path when subchannel 1 isn't bound to the same object as subchannel 0.
3. **See the real per-draw mask.**
   - `RTT_DUMP=4` prints every op with `rt=`, `cmask=`, `blend=` and `fp=` (`rsx_d3d12_backend.c#L4731-L4742`).
   - `BLENDDBG=1` prints the distinct blend keys (`#L7361-L7366`).
   - Expected if the lead is right: in-stage draws with `cmask=6` (G|B) and odd blend keys right after transfers; the 6-vertex composite quad among them.
4. **Fix `CMASK_FORCE`** (§3) before using it as a reference again. Then confirm with `PERF=1`, whose `[PERF] … pso … N MISS` line comes from `#L5683-L5695`; `PSOMISSDBG=1` (`#L2406`) names which key field differs.
5. **upload_empty** (counted at `#L4566-L4569` and `#L7383`). A VP upload returns 0 only when:
   - **position attribute 0 is disabled** (`upload_tris_vp` / `upload_tris_vp_indexed`, `#L6734-L6735`, `#L7003-L7004`); or
   - **the per-frame vertex buffer is full** (`MAX_VERTICES 393216`, `#L63`; the clamp at `#L6737-L6742`).

   Check with `VBFULL=1` (`[VBFULL] fp=… wanted … room for …`) and `FRAME_BUDGET=1` (`[BUDGET] requested … verts`, `#L5663-L5675`). If neither prints, it's attribute 0 being disabled; dump `vertex_attribs[0]` for those draws.
   - ASSUMED link: the same subchannel-1 clobber doesn't reach the vertex-array registers (0x1680+), so upload_empty is probably a separate issue. VERIFY.
6. **Surface format of 0x0B530000.** Read `rt_fmt` from `RTT_DUMP` or `RSX_CAP_DIR` (`manifest.txt`, `#L1671-L1690`).
   - If it is 4/5 (X8R8G8B8) and the composite samples alpha, add the RPCS3-style alpha-0/1 read remap.
   - If it is 9/10 (B8/G8B8), add the mask remap from §1.

## 5. What is still open

- Whether Strikeforce really issues NV0039 on subchannel 1 in the stage (check 1).
- Whether anything else on subchannel 1 is real 3D state (check 1). That decides between flipping the default and routing by handle.
- The upload_empty cause (check 5).
