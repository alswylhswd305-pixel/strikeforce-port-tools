# Existing tools for the Strikeforce stage we're at (colour-mask/blend corruption, then frame-exact matching, then the auto-loop)

> **CORRECTION 2026-11-26 12:32 (UTC+3), from Salem's in-stage measurements:** the subchannel-1 / NV0039 lead was **wrong for Strikeforce**. There are no subchannel-1 methods in the 3D range and no SET_OBJECT in the stream, and the in-stage cmask is 0x01010101. The register collision described below is real as a *class* of bug (envytools, PSL1GHT and Demon's Souls fix 141 are still correct), but it is **not** this game's cause. The real cause was a shadow-map clear with no colour target being treated as a frame start. For the remaining olive world, see olive-world-researcher.md.


2026-11-26, ~13:15 UTC+3. Research only; nothing was installed or run on Saud's PC.

Every repo below was opened (GitHub API plus a shallow clone) this turn. Licences come from each repo's LICENSE file. "Last activity" is the last push or commit date (UTC+3). Pins:
- **P** = ps3recomp e85647a33ce5f9391788f0e3f52ab395a7fe6a89
- **R** = RPCS3 0ca5eb0efe50ec4e8aa07892ab86d57842246eb4

## Big finding first

Three independent, non-GPL sources confirm the colour-mask hypothesis.

**1. KNOWN — envytools rnndb (MIT).** NV0039 (M2MF) registers sit at the same offsets as these NV4097 3D registers:

| Offset | M2MF (`nv_m2mf.xml` L38-56) | NV4097 3D (`nv30-40_3d.xml` L204-231) |
|---|---|---|
| 0x30C | OFFSET_IN | ALPHA_FUNC_REF |
| 0x310 | OFFSET_OUT | BLEND_FUNC_ENABLE |
| 0x314 | PITCH_IN | BLEND_FUNC_SRC |
| 0x318 | PITCH_OUT | BLEND_FUNC_DST |
| 0x31C | LINE_LENGTH_IN | BLEND_COLOR |
| 0x320 | LINE_COUNT | BLEND_EQUATION |
| **0x324** | **FORMAT** | **COLOR_MASK** |
| 0x328 | BUF_NOTIFY | STENCIL[0].ENABLE |

Links:
- https://github.com/envytools/envytools/blob/f102b82381f3f11cee113d16374c87091db039d9/rnndb/graph/nv_m2mf.xml#L38-L56
- https://github.com/envytools/envytools/blob/f102b82381f3f11cee113d16374c87091db039d9/rnndb/graph/nv30-40_3d.xml#L204-L231

**2. KNOWN — PSL1GHT (MIT).** Its librsx copies memory with `RSX_SUBCHANNEL_METHOD(1, NV_MEMORY_TO_MEMORY_FORMAT_OFFSET_IN, 8)`, so M2MF runs on **subchannel 1**. The seventh word, at 0x324, is `(1<<8)|1` = 0x101.
- Link: https://github.com/ps3dev/PSL1GHT/blob/dd4e8c9be744e3273d665c393fa6d97a87402e2e/ppu/librsx/commands_impl.h#L1846-L1856
- If that word lands in 3D state, COLOR_MASK becomes 0x00000101: B and G on, R and A off, by the RPCS3 decode in colormask-researcher.md.
- At the same time BLEND_FUNC_ENABLE gets the destination offset, which is non-zero, so blending turns on.
- ASSUMED: Sony's libgcm, which Strikeforce links, emits the same 8-word M2MF block. PSL1GHT is homebrew, not libgcm.
- VERIFY: compare against the in-stage `cm=` value Salem logs.

**3. KNOWN — Demon's Souls port (MIT) hit the same bug** (NOTES fix 141, "2D transfer words landed in the 3D registers"): DeS binds NV0039 at 0x2000 (subchannel 1), and the transfers overwrote 0x300-0x328, "for NV0039, the blend enable, factors, equation and colour mask".
- Its fix is for the Metal draw-engine path.
- P master still strips the subchannel there: `u32 m = (method >= 0xE000u) ? (method & 0xFFFCu) : (method & 0x1FFCu);` at https://github.com/sp00nznet/ps3recomp/blob/e85647a33ce5f9391788f0e3f52ab395a7fe6a89/libs/video/rsx_draw_engine.c#L4185
- Our D3D12 legacy path's routing is the separate cellGcmSys.c L2917-2925 issue from colormask-researcher.md.
- Link: https://github.com/timboat/demons-souls-recomp/blob/9637b204f031c72839129d49e5b0586d4bcfdeed/docs/NOTES.md#L3263-L3282

## Ranked by usefulness now

| # | Tool | Licence | Last activity | Windows (Salem) |
|---|---|---|---|---|
| 1 | DeS `test_subchannels.c` + `GCM_SUBCH_LOG` patch | MIT | 2026-11-24 | yes (C test; the patch is plain C) |
| 2 | envytools rnndb (nv_m2mf, nv30-40_3d, nv_object) | MIT | 2023-10-26 | yes (XML, read in a browser) |
| 3 | P's own `RSX_CAP` + `tools/parse_rrc.py` + RPCS3 `--headless --rsx-capture` | MIT / GPL tool use | P 2026-11-22 | yes |
| 4 | NVIDIA FLIP (`pip install flip-evaluator`) | BSD-3-Clause | 2026-10-13 | yes (pip) |
| 5 | odiff | MIT | 2026-10-13 (v4.5.0 released 2026-07-23) | yes (`odiff-windows-x64.exe`) |
| 6 | RenderDoc (P already has a hook) | MIT | 2026-11-25 (v1.47 2026-10-31) | yes |
| 7 | Ascension-R `scripts/rsxcap_check.py` | MIT | 2026-11-26 | yes (pure Python) |
| 8 | MotorStorm `lift_ms_plugins.py` + GT5 `lift_spu_jobs.py` (+ P `SPU_DUMP_OVL`) | MIT | 2026-11-26 / 2026-11-25 | yes |
| 9 | PSL1GHT headers (non-GPL HLE reference) | MIT | 2026-11-04 | yes (read only) |
| 10 | ps3kit (independent non-GPL PS3 runtime) | MIT | 2026-10-23 | partial |
| 11 | pixelmatch / pixelmatch-py, scikit-image SSIM | ISC / ISC / BSD-3 (VERIFY: GitHub reports NOASSERTION) | 2026-11-24 / 2026-11-23 / 2026-11-24 | yes |
| 12 | PIX `pixtool.exe` | Microsoft, closed, free | page dated 2017; tool updated with PIX (VERIFY) | Windows only |
| 13 | GhidraSPU | Apache-2.0 | 2023-07-07 | yes (Ghidra) |

---

### 1. Demon's Souls: `test_subchannels.c` and `GCM_SUBCH_LOG` (MIT)

**Links:**
- https://github.com/timboat/demons-souls-recomp/blob/9637b204f031c72839129d49e5b0586d4bcfdeed/mac/tests/test_subchannels.c
- `GCM_SUBCH_LOG` in https://github.com/timboat/demons-souls-recomp/blob/9637b204f031c72839129d49e5b0586d4bcfdeed/patches/ps3recomp-local.patch (hunk at L11325-L11337)

**Does:**
- The test sets 3D alpha and blend state, draws, then writes the same low offsets on subchannels 0x2000, 0x6000, 0x8000, 0xA000 and 0xC000. It checks that the bound pipeline and the pipeline-create count don't change.
- That is exactly the regression test we need. Port it to our D3D12 path; P's `libs/video/tests/rsx_harness_main.c` is the harness.
- `GCM_SUBCH_LOG=<n>` prints the first n method headers on any non-zero subchannel (offset, header, subch, method, count, first word). It is about 6 lines in `gcm_rsx_process_fifo_unlocked` and is **not in P master** (git grep).

**Can't:**
- The test targets the Metal draw engine (`rsx_draw_engine_method`), not `rsx_d3d12_backend.c`, so it needs adapting.
- It doesn't fix cellGcmSys's subchannel-1 routing by itself.

### 2. envytools rnndb (MIT)

**Link:** https://github.com/envytools/envytools/tree/f102b82381f3f11cee113d16374c87091db039d9/rnndb

**Does:**
- The machine-readable register database for NV4097 (`nv30-40_3d.xml`, NV40 variants), M2MF (`nv_m2mf.xml`) and the object classes (`nv_object.xml` L167: `0x0039 NV3_M2MF`).
- It includes `MRT_COLOR_MASK` 0x370 for NV40, bits 4-15 = buffers 1-3 (`nv30-40_3d.xml` L249-L262), which matches the RPCS3 decode.
- It is a non-GPL source for the methods, so the collision tripwire (ideas doc #1) can be generated from it.

**Can't:**
- It is desktop NV40, not RSX. RSX-only methods (e.g. Sony's 0xE9xx driver methods) are absent.
- The `demmt` decoder needs Linux mmiotrace and doesn't apply to PS3 FIFOs.
- Last push was 2023, but the data is stable.

### 3. Tools we already have, joined into a frame-exact diff

KNOWN, all verified at the pins:
- **P `RSX_CAP=start[:count[:stride]]`** dumps the backbuffer, every offscreen RT as BMP, and a `manifest.txt` with one line per op: `rt mrt vp fp vs n cmask blend bk t0-t3`, plus texture formats. The directory is set by `RSX_CAP_DIR`. https://github.com/sp00nznet/ps3recomp/blob/e85647a33ce5f9391788f0e3f52ab395a7fe6a89/libs/video/rsx_d3d12_backend.c#L1671-L1710 and `#L5996-L6020`
- **P `tools/parse_rrc.py`** turns an RPCS3 `.rrc.gz` into a draw-list manifest with blend and texture state. The format version is 6, which matches R `Emu/RSX/Capture/rsx_replay.h#L14`.
- **RPCS3 writes captures** to `<config>/captures/<TITLEID>_<time>_capture.rrc.gz` (R `Emu/RSX/RSXThread.cpp#L2207`). The hotkey is Alt+C.
- **RPCS3 replays a capture headless:** `rpcs3.exe --headless --rsx-capture <file>` (R `rpcs3/rpcs3.cpp#L414`, `#L843`, `#L1228`; added in https://github.com/RPCS3/rpcs3/pull/13330). That gives an automated reference frame.
- **RPCS3's built-in RSX debugger** (`rpcs3qt/rsx_debugger.cpp`) shows live register state. The old standalone https://github.com/RPCS3/rsx-debugger (no licence, last push 2017-12-06) reads an obsolete capture.txt and is not useful.

**Does:** about 100 lines of Python can align the two manifests and print the cmask/blend differences per draw.

**Can't:** no standalone `.rrc` viewer exists on GitHub. A GitHub search for "rrc rpcs3" or "rsx replay" returns 0 repos, and a web search found only RPCS3 itself.

### 4. NVIDIA FLIP (BSD-3-Clause)

**Link:** https://github.com/NVlabs/flip/tree/d3ab02a (README L32/L52: `pip install flip-evaluator`)

**Does:** a perceptual error map and a mean error between a reference and a test image. It is better than mean absolute difference for "does it look the same", e.g. checking the olive tint is gone.

**Can't:**
- It tells you that images differ, not why.
- It needs pixel-aligned frames of the same size. RPCS3's resolution scale must equal the port's.
- No numeric threshold is published for "the same" (VERIFY by calibrating on a menu frame that is already correct).

### 5. odiff (MIT)

**Link:** https://github.com/dmtrKovalenko/odiff (releases v4.5.0 include `odiff-windows-x64.exe`)

**Does:**
- Fast pixel diff with `threshold`, `antialiasing`, ignore regions (to mask the HUD or the clock) and a diff PNG.
- It can run in server mode over JSON stdio, a good fit for the auto-loop's `frame_check`.

**Can't:** it isn't perceptual. Timing-dependent frames (particles, animation) will always differ; use capture replays (#3) to freeze them.

### 6. RenderDoc (MIT)

**Links:**
- https://github.com/baldurk/renderdoc
- Python API: https://renderdoc.org/docs/python_api/examples/renderdoc_intro.html (live). `renderdoc.dll` plus the Python module; `rd.InitialiseReplay`, `OpenCaptureFile`.

**Does:**
- P already loads it: `RENDERDOC_DLL=<renderdoc.dll>`, captures to `RENDERDOC_DIR/gcm_*.rdc` (`rsx_d3d12_backend.c#L573-L586`).
- A Python script can replay the `.rdc` with no UI and dump each draw's D3D12 `RenderTargetWriteMask` and blend.
- That separates whether the guest register is wrong (#3) from whether our PSO translation is wrong.

**Can't:**
- It sees only D3D12, not RSX registers.
- Replay needs a D3D12 GPU, which Salem's Windows machine has. It doesn't run on our Linux box.

### 7. Ascension-R `scripts/rsxcap_check.py` (MIT)

**Link:** https://github.com/rigaz29/Ascension-R/blob/7c3201dd952adfc9ad2af6f8cb07ce52366d9810/scripts/rsxcap_check.py

**Does:** reads the same `RSX_CAP` output layout and offers four modes:
- `png`: BMP→PNG;
- `flicker`: per-frame luma and lag changes;
- `srgb`: pairs sRGB encode and decode per target;
- `textures`: formats and remaps.

It is pure Python with no dependencies.

**Can't:** the `srgb=` manifest field comes from their fork ("fork" in their `docs/notes/2026-11-01-rendering-accuracy.md` L10-L13). P's manifest lacks it, so that mode only half-works on ours (ASSUMED; VERIFY). It has no colour-mask check.

Related: MotorStorm's `scripts/bmpdiff.py` (MIT) is a grid-cell mean-absolute diff of two RSX_CAP BMPs that shows *where* frames differ: https://github.com/nynjardin/motorstorm-apocalypse-recomp/blob/2c453c88c7dbc12e653471ac293926196ccbccef/scripts/bmpdiff.py

### 8. SPU overlay lifting: MotorStorm and GT5 (MIT), on top of P's `SPU_DUMP_OVL`

**Links:**
- https://github.com/nynjardin/motorstorm-apocalypse-recomp/blob/2c453c88c7dbc12e653471ac293926196ccbccef/scripts/lift_ms_plugins.py
- https://github.com/MormonFTP-hub/gt5-recomp/blob/d1c160fd619106d338faf0c8b0f148466b5ae32d/GT5/scripts/lift_spu_jobs.py (L16, L42, L232-L244)

**Does:**
- MotorStorm dumps runtime-streamed SPU code banks with `SPU_DUMP_OVL=<dir>,<lsa>`. P master has this: `runtime/spu/spu_channels.c#L2164-L2172`, writing one `ovl_<ea>.bin` per source EA.
- It lifts each bank at its LS address and registers it with `spu_overlay_register_verified_region`, keyed by EA and byte-checked at first dispatch. "~40x too slow" interpreted is the author's own figure.
- GT5 does the same for Wws jobs streamed into 0x4000, with a 64-byte verified sample.
- This is the template for the cloth image's cellOvis overlays: dump at the Ovis LSA, lift per overlay, register.

**Can't:**
- Neither handles cellOvis's table directly. Our overlay LSAs and EAs have to come from `strikeforce_ovis.inc` (VERIFY).
- Position-dependent overlays sharing one LSA need one registration per content, and the verify step handles that.

Also relevant: Killzone 2's `tools/spu/lift_spu.py` wraps raw job modules as one-segment ELFs before lifting: https://github.com/undecuple/project-pyrrhus/blob/bc3301d2032da208ee0213289f305f5418fd327b/tools/spu/lift_spu.py

### 9. PSL1GHT (MIT): non-GPL PS3 reference

**Link:** https://github.com/ps3dev/PSL1GHT/tree/dd4e8c9be744e3273d665c393fa6d97a87402e2e

**Does:**
- Real librsx command emission, including subchannel use: M2MF on 1, NV3062 on 3, NV308A on 5 (`commands_impl.h` L1651-L1666, L1847).
- NV30/40 method defines (`tools/cgcomp/include/nv30-40_3d.xml.h` L344-L348, L418).
- `ppu/include/spurs/*.h` struct declarations.
- Code can be read and reused under MIT, unlike RPCS3.

**Can't:**
- It is homebrew, not Sony's libgcm or libsre, so command sequences and SPURS layouts may differ from what Strikeforce does (ASSUMED; VERIFY against RPCS3 offsets before relying on them).
- It has no HLE semantics.

### 10. ps3kit (MIT): an independent PS3 runtime (not ps3recomp)

**Link:** https://github.com/vs-sr-dev/ps3kit/tree/38b0a12010b32fdd1e1bd4087d9be8579f39af01

**Does:**
- A second, non-GPL implementation of gcm, rsx, spurs, sync and lv2 to cross-check our HLE against (`runtime/*.cpp`).
- `runtime/rsxcap.cpp` keeps a full 0x4000-entry method register file per draw.
- `gdb_trace.py` traces recompiled functions' r3-r6, LR and return under gdb.

**Can't:**
- Different ABI and context layout from ps3recomp, so its scripts don't drop in.
- Its SPURS is "a kernel of the runtime's own that does not schedule" (README L367-L373), so it's not an oracle for SPURS semantics.
- gdb tracing on Windows needs a gdb-debuggable build. VERIFY whether Salem's MSVC build qualifies.

### 11. pixelmatch / pixelmatch-py / scikit-image SSIM

**Links:**
- https://github.com/mapbox/pixelmatch (ISC; CLI `pixelmatch a.png b.png diff.png threshold includeAA`)
- https://github.com/whtsky/pixelmatch-py (ISC)
- https://scikit-image.org/docs/stable/api/skimage.metrics.html (`structural_similarity`)

**Does:** simple Python-native options for the loop when Node or an exe isn't wanted.

**Can't:** same limits as #5. SSIM works on luminance structure and can miss pure tint shifts like olive vs green (ASSUMED). Use FLIP for colour.

### 12. PIX `pixtool.exe` (Microsoft)

**Link:** https://devblogs.microsoft.com/pix/pixtool/ (live)

**Does:** from the command line: take a GPU capture, open a capture, `save-event-list` to CSV, and `save-resource out.png` after playback.

**Can't:**
- Windows only and closed source.
- It doesn't see RSX state. RenderDoc (#6) is already hooked into P, so PIX is optional.

### 13. GhidraSPU (Apache-2.0)

**Link:** https://github.com/aerosoul94/GhidraSPU

**Does:** disassembles and decompiles SPU code in Ghidra, for reading the cloth job by hand while we work out its overlay table.

**Can't:** it doesn't lift and was last pushed in 2023.

## Checked and rejected

- **eth-man/ps3-cell-re-tools:** GPL-2.0, so no code can be copied (P CONTRIBUTING L260).
- **AlexAltea/nucleus:** GPL-2.0 and archived.
- **kornelski/dssim:** AGPL-3.0. Usable as an external exe only; FLIP covers the need.
- **Goatman13/spu2c:** an IDA SPU-to-C plugin with no licence file, so all rights reserved. Read only.
- **project-vekta's F12 pass capture:** Vulkan-only (`rsx_vulkan_backend.c`).

## Suggested use today (Salem, Windows)

1. Apply the `GCM_SUBCH_LOG` hunk from DeS (#1) and run in-stage. Expected (ASSUMED): `subch=1 method=0x030C count=8`, with the 7th word 0x101.
2. Take `GCM_SUBCH1_2D=1` A/B runs with `RSX_CAP=<frame>` on each. Compare the `cmask=` and `blend=` columns.
3. Make an RPCS3 Alt+C capture of the same spot. Run `parse_rrc.py` on it and diff against the RSX_CAP manifest.
4. Replay with `rpcs3 --headless --rsx-capture` for the reference image, then run FLIP or odiff against our backbuffer.
5. Once fixed, port `test_subchannels.c` to the D3D12 path as a regression test.
