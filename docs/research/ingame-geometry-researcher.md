# Strikeforce in-stage: draws issued, nothing on screen (2026-11-26, ~11:30 UTC+3)

Research only; nothing was run, and Saud's PC was not touched.

Pins:
- **P** = ps3recomp `e85647a33ce5f9391788f0e3f52ab395a7fe6a89` (https://github.com/sp00nznet/ps3recomp/blob/e85647a33ce5f9391788f0e3f52ab395a7fe6a89/)
- **R** = RPCS3 `0ca5eb0efe50ec4e8aa07892ab86d57842246eb4` (https://github.com/RPCS3/rpcs3/blob/0ca5eb0efe50ec4e8aa07892ab86d57842246eb4/)

## 0. Which renderer Salem is on (KNOWN)

- On Windows, P's project template always uses the legacy D3D12 "vtable" backend, `libs/video/rsx_d3d12_backend.c` (P `templates/project/main.cpp#L127-L134`). `FP_IDCOLOR` lives in that file (`#L2575-L2600`), which confirms it.
- The shared register-file **draw engine** that Vulkan/Metal use (`rsx_draw_engine.c`) has **no D3D12 backend at P**:
  - PR #748 "opt-in D3D12 backend for the register-file draw engine" is still open (https://github.com/sp00nznet/ps3recomp/pull/748).
  - Issue #457 says the legacy D3D12 paths left ICO black where the engine path rendered (https://github.com/sp00nznet/ps3recomp/issues/457).
- `RSX_LIVE_DRAW=1` is a third, opt-in path (P `libs/video/rsx_live_draw.c#L1259-L1271`).

## 1. The strongest lead: the legacy D3D12 path never presents frames whose draws all go to offscreen surfaces (KNOWN)

**How the present gate works:**
- `d3d12_present` (P `rsx_d3d12_backend.c#L6102-L6140`) and the ticker present `rsx_d3d12_backend_present` (`#L8068-L8172`) set `has_display` **only if some draw has `rt_off == 0`**, i.e. targets surface offset 0.
- The ticker path still *executes* offscreen draws (`render_frame`, `#L8160-L8171`). But it only **Presents** when `has_display` is true: `s_present_this_frame = has_display`.
- Strikeforce's colour target is 0x0B530000 and its display buffers are 0x0D750000/0x0D3B0000, all non-zero offsets. So no draw ever counts as "onscreen", and the window keeps showing the backbuffer clear (Salem's magenta).
  - ASSUMED that his offsets are surface offsets as `rt_off` sees them. VERIFY with step 1 in §4.
- PR #747 (merged 2026-11-21) describes exactly this: "a flip renders only when some draw targets surface offset 0, otherwise draws keep accumulating … All of this can end as a black frame with nothing in the log" (https://github.com/sp00nznet/ps3recomp/pull/747).

**Where the scene actually lives:**
- In this backend, rendered surfaces live **only on the GPU** (`off_rt[]` textures).
- P `#L4297-L4312`: "That surface lives in guest RAM, which the D3D12 path never writes -- the scene is on the GPU -- so the CPU copy in nv3089_blit faithfully moves zeros."
- So **reading 0x0B530000 from guest memory will show whatever the CPU/clear left there (olive), even if the draws worked.** VERIFY how Salem "showed" 0x0B530000:
  - If it was through guest RAM, e.g. `GCM_GUEST_FB=…` (`#L4384`), that test can't tell us anything.
  - Look at the GPU copy instead (§4 step 2).
- The GPU-side composite that exists for this case, `rsx_d3d12_composite_from_offscreen()` (`#L4313-L4330`, triggered "under GCM_COMPOSITE_RT"), **has no caller at P** (`git grep` finds only the definition and its use in `composite_present`). The comment refers to an env var that no longer exists.

**Conclusion:** "draws produce no pixels" is **not yet shown**. What is shown is that nothing from an offscreen target reaches the screen in this backend. Separate the two before chasing vertex data.

## 2. Q1: how the KOEI engine presents

- **KNOWN: nothing published** that I could find on the Dynasty Warriors / Omega Force PS3 present path.
- **Indirect hint** (RPCS3 forum, BLUS30471 thread, https://forums.rpcs3.net/thread-199283.html, posts #3/#5, 2022):
  - one tester reports the game is "Playable needs write color buffers", with graphics broken in the main story mission without it;
  - another reports no difference.
- RPCS3's "Write Color Buffers" copies rendered targets back to guest memory. A game that needs it reads its render output **through memory**: a CPU/SPU pass, or a copy the emulator only sees in memory.
- ASSUMED: the final image may reach the display buffer through a 2D-engine/transfer copy or memory, not a fullscreen-quad draw. That fits Salem's "no draw targets the display buffer and nothing samples 0x0B530000".
- **What P does with each candidate** (KNOWN):
  - **NV3089 scaled-image blit / `cellGcmSetTransferImage`-style copies:** `nv3089_blit` is a **CPU copy in guest RAM** (P `libs/video/cellGcmSys.c#L1358-L1440`). On the D3D12 legacy backend its source surface was never written back, so it copies the clear or zeros.
    - `NV3089_GATE=<file>` logs each blit's geometry while `<file>` exists (`#L1365-L1380`).
    - RPCS3 implements NV3089 in R `rpcs3/Emu/RSX/NV47/HW/nv3089.cpp`, with surface-cache awareness.
  - **`cellGcmSetFlip` on another offset:** P tracks the current scanout (`cellGcm_current_scanout`, used at `rsx_d3d12_backend.c#L4469-L4471`). But it only presents guest bytes automatically when the frame had **zero** RSX draws (`SCANOUT_FB`, `#L4447-L4465`).
  - **SPU job writing the display buffer:** possible (ASSUMED). It would also need the colour buffer in guest RAM, which this backend never writes.
- **VERIFY in RPCS3:** take an RSX capture (Alt+C, R `rpcs3/rpcs3qt/shortcut_settings.cpp#L87`; `Emu/RSX/Capture/rsx_capture.cpp`) during a stage frame. Note the last commands before the flip: NV3089/NV3062 methods, a fullscreen draw, or a flip to 0x0B530000.

## 3. Q2: RSX state P's D3D12 path handles differently from RPCS3 (KNOWN, with impact ASSUMED)

| State | P legacy D3D12 | RPCS3 | Could it cull everything? |
|---|---|---|---|
| Viewport x/y scale/offset (0x0A20/0x0A30) | Decoded (P `libs/video/rsx_commands.c#L611-L630`). The shader epilogue uses **identity x/y** and keeps only z scale/offset (`rsx_d3d12_backend.c#L3606-L3615`). `d3d12_set_viewport` is a **TODO no-op** (`#L6297-L6302`). The D3D viewport and scissor are the **full RT size** (`#L5346-L5368`). | Builds a scale-offset matrix from viewport scale/offset **relative to the surface clip size** (R `rpcs3/Emu/RSX/Core/RSXDrawCommands.cpp#L594-L616`). | Only if the game's viewport isn't "full surface" with the usual scale = w/2, offset = w/2. A negative-y scale (flip) would invert, not cull. ASSUMED low. |
| Depth | DSV fixed at D24S8 (`#L2723`). Depth func/write/stencil come from the guest (`#L2724-L2746`). Depth clip is off (zero-init). | Full surface cache incl. depth formats. | **Yes**: if the bound DSV wasn't cleared to the guest's clear value, or a shared or window-sized DSV is used with a GREATER-style test, every fragment fails. Test with `DEPTH_OFF=1` (`#L2747-L2753`). |
| Colour mask | Guest mask honoured. A mis-decode writes nothing (`#L2709-L2722`). | — | **Yes**. Test with `CMASK_FORCE=1`. |
| Culling / winding | Guest cull face and front face (`#L2678-L2690`). | — | Yes, if winding is inverted. Test with `CULL_OFF=1` / `CULL_FLIP=1`. |
| Transform constants (0x1EFC/0x1F00), VP load/start (0x1E9C/0x1EA0) | Decoded (P `rsx_commands.c#L384-L500`, `#L810`). | — | Wrong or zero constants put everything outside clip. `VTX_DUMP=1` writes the first few draws' positions plus viewport scale/offset to `vtx_dump.txt` (`rsx_d3d12_backend.c#L6716`, `#L6891-L6908`; note `#L6777` only fires for surface 0xCC0000). `RSX_DBG_CB=<tex>` prints the constant buffer the shader actually sees (`#L3593-L3605`). `VP_FIXPROJ=1` forces a fallback projection (`#L3639-L3660`). **Note:** that fallback also turns on *silently* when c0-c15 are all zero (`garbage`), which can mask missing SPU-written matrices. Use `VP_NOFIXPROJ=1` while diagnosing. |
| Vertex formats | `rsx_vertex_fetch.c`; missing components are expanded (PR #597, merged). | — | Half-float/CMP/stride-0 bugs give garbage, not usually zero pixels. ASSUMED. |
| Draw drops | `D3D12_DROP_STATS_EVERY=<n>` counts `not_ready`, `bad_count`, `no_vp_resources`, `prim_unwired`, `upload_empty`, `records_full`, deferred flips and `vp_fallback_ps` (`#L4552-L4590`, PR #747). `[FP] PSO FAIL` drops a pipeline (`#L2757-L2760`). | — | Yes, if records fill or PSOs fail. |

**2D methods clobbering 3D state:** issue/PR #815 (open) fixes the *shared engine* routing NV3062 methods on subchannels 2-6 into 3D alpha-test registers. The FIFO walker in `cellGcmSys.c` already splits them, per that PR. Not the D3D12 legacy path's problem as far as I can tell (ASSUMED).

## 4. Fastest ordered checks (each uses an existing knob unless marked "local")

1. **`D3D12_DROP_STATS_EVERY=60 VP_SUBMIT=3`.** VP_SUBMIT prints `[PRESENTGATE] targets: 0x… xN`, is_vp vs not_vp, and `render_frame=YES/SKIPPED` (`#L8121-L8158`). Read:
   - deferred flips;
   - `records_full` (more than 2048 records/frame drops the rest, `MAX_DRAWS` `#L66`);
   - `vp_fallback_ps`;
   - `not_vp` draws (never executed).
   This confirms or refutes §1 in one run.
2. **Look at the GPU copy of 0x0B530000, not guest RAM.**
   - `RENDERDOC_DLL=<renderdoc.dll> CELLMARK_DUMP=…` captures a frame. Resources are named in guest terms (PR #561; `rsx_d3d12_backend.c#L586`, `CELLMARK_DUMP` `#L7960`).
   - In RenderDoc: open the 1280x720 off_rt, use the pixel history on one pixel, and the mesh viewer for VS output of one draw.
   - Alternative (local, one line): call `rsx_d3d12_composite_from_offscreen(2)` before present each flip. `2` means "whatever this frame's draws targeted" (`#L4325-L4330`).
   - **Decision:** RT has the scene, so the problem is only the present/copy path (go to 3). RT is empty, so it's geometry or state (go to 4).
3. **Find the final copy.** Set `NV3089_GATE=<file>` and create the file during a stage frame. Also log the flip offset (`cellGcm_current_scanout`).
   - If an NV3089 blit goes 0x0B530000 to 0x0D750000, the **fix** is a GPU-side blit from the off_rt in the D3D12 backend: wire `rsx_d3d12_composite_from_offscreen` from `nv3089_blit` when its source matches an off_rt.
   - Better long-term: move Windows to the shared draw engine (PR #748 or the ICO fork) so surfaces and transfers are handled in one place.
   - Also treat a draw to the **current display buffer offset** as onscreen, not only `rt_off == 0`. The stats already compute `deferred_with_display_draw`.
4. **Only if the RT really is empty:**
   - `VTX_DUMP=1`: all-zero positions or c[] point to missing SPU output (ASSUMED source: the same MOC jobs). Plausible positions point to state.
   - Then single-knob A/B: `DEPTH_OFF=1`, then `CMASK_FORCE=1`, then `CULL_OFF=1`, then `VP_FIXPROJ=1`. Whichever one makes pixels appear names the state.
   - Fullscreen test triangle (local): one draw with a passthrough VS into 0x0B530000 proves the RT binding and the present/copy chain.
5. **RPCS3 side by side:** an RSX capture of the same stage frame (Alt+C). Compare:
   - the draw count and target list (same 0x0B530000?);
   - one draw's vertex buffer and constants;
   - the method sequence at frame end (NV3089 vs fullscreen draw vs flip offset).
   Optional: test RPCS3 with Write Color Buffers on and off to see whether the image depends on memory write-back.

## 5. Open

- How Salem displayed 0x0B530000 (guest RAM vs GPU).
- Whether `rt_off` values equal the offsets he quotes.
- The actual final-copy mechanism: no public source. Needs NV3089_GATE or an RPCS3 capture.
