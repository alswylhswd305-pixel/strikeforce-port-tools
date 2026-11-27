# VP branch bits (0x1FF8) on the legacy D3D12 path: root-fix proposal

Strikeforce BLUS30471, ps3recomp legacy path (`rsx_process_method` -> D3D12 backend, draw_engine_enabled=0).
This folder is a **proposal, as a diff**. Nothing here has been built for the PC or sent to anyone. Salem builds it only after Saud's OK.
Labels: **KNOWN** means read in source or measured, **ASSUMED** means reasoned, **VERIFY** means a test is still needed. There are no success percentages.

## Problem

- **0x1FF8 is stored but never used (KNOWN).**
  - `rsx_commands.c:879-880` stores `NV4097_SET_TRANSFORM_BRANCH_BITS` in `state->transform_branch_bits` (`rsx_commands.h:369`).
  - The legacy backend decompiles every VP with `rsx_vp_decompile` (`sh_work.c:1773` base VS, `:1955` per-draw VS, `:6339` FACES_CTL dump). It never calls `rsx_vp_set_branch_bits`.
  - The only callers are the disabled paths: `rsx_draw_engine.c:2549` and `rsx_live_draw.c:4984`.
- **The decompiler bakes the branch outcome (KNOWN).**
  - The decompiler (`rsx_vp_decompiler.c:142-143`) keeps `s_vp_branch_bits` at 0.
  - At L519-531 it emits each BRB/CLB as a fixed jump: taken (`_pc = target`) or not taken (`_pc = next`), chosen at decompile time.
  - Its own comment says "the caller keys the program on them". The legacy caller does neither: it doesn't set the bits and doesn't key on them.
- **What this means for the dumped programs (KNOWN, from the 1776 dumps in `/workspace/clothv2/r1776/cwd_1776/`):**
  - With bits = 0, every BRB in these programs is taken, because each has D3[28]=0.
  - In prop VP `0x6A46C9BA`, `BRB @14 -> 29` skips instructions 15-28: the light vector `vp_c[466]-pos`, normalize, n·l, exp2 specular, `× vp_c[257]`.
  - The program tests bit 0 only.
  - Shadow VP `0xD54F73A6` tests bits 1 and 2. Prop VP `0x3F083BFF` tests bits 0, 1 and 2. None of the three has a CLB.
- **Brightness link (ASSUMED).** The dim lit props are roof ×0.60, sign ×0.53 and noticeboard ×0.59 against RPCS3 (`findings.md:12`); 1785 measured roof ×0.68 (`sf-gfx-runs/bisect/report.md`). That they come from this skipped body is ASSUMED. It is also ASSUMED that the game writes a non-zero 0x1FF8 at that spot. The census will show this.
- **H1 ruled out on 1785 (KNOWN, `findings.md:49`).** `FP_CONSTBUF=0` did not restore the roofs on 1785.

## Polarity check

- **Our decompiler (KNOWN):**
  - The branch is taken when `((bits >> D3[23:27]) & 1) == D3[28]` (`rsx_vp_decompiler.c:524-525`).
  - The target is `D0[23]<<9 | D2[5:0]<<3 | D3[31:29]` (L165-169).
- **ISA meaning (KNOWN, public RSX docs as written in RPCS3; read for reference only, nothing copied):**
  - D3 bits 23-27 are the branch index and bit 28 is `brb_cond_true`. If the flag is set, the branch is taken when the bit is set; if it is clear, the branch is taken when the bit is clear. Source: `rpcs3/Emu/RSX/Program/RSXVertexProgram.h:166-167` (commit 0ca5eb0e, 2026-11-25).
  - Their decompiler emits "bit != 0" when the flag is set and "bit == 0" when it is clear (`VertexProgramDecompiler.cpp:301-306`, used for BRB at L740-747 and CLB at L764-767).
  - Their interpreter checks `cond == actual` (`Program/GLSLInterpreter/VertexInterpreter.glsl:336-343`).
- **Result: the polarity matches (KNOWN).** D3[28] does not invert the test. It is the value the bit must have for the branch to be taken. D3[28]=0 means "branch when the bit is clear", so at bits=0 every BRB here jumps over its body. That is what the 1776 HLSL shows.
- **Decode by hand of 0x6A46C9BA @14** (raw `... FC 3F 40 A0`): D3 = 0xA0403FFC, so the index is (D3>>23)&31 = 0, D3[28] = 0, and the target is 3<<3 | 5 = 29. This matches `FLOW BRB @14 -> 29`.
- **Harness T5/T6:** all 4 combinations of polarity and bit for both BRB and CLB come out as the ISA says.

## Design choice

**(a) Bake at decompile time and key the VS cache on the bits. This is RECOMMENDED and is what the diff does.**
- The tree already uses this pattern in both other paths (KNOWN):
  - `rsx_draw_engine.c:2431-2434, 2500, 2549` puts the bits in the pipeline key and sets them before decompiling.
  - `rsx_live_draw.c:4865-4869, 4984` does the same.
  - The legacy path is the only caller missing it.
- It changes no shader interface, no root signature, no cbuffer layout, and nothing the other two paths share.
- It is one function in the decompiler (a pure helper) plus about 20 lines in the backend.
- Only the bits a program actually tests go into the key, through `rsx_vp_branch_bits_mask`:
  - A program with no BRB/CLB keeps exactly its old key.
  - A program whose tested bits are 0 keeps its old key and output.
  - So the change does nothing until the game writes a tested bit.
- Cost: one VS per (microcode, tested-bit value). The masks here are 0x1, 0x6 and 0x7, so at most 2, 4 and 8 variants. `VP_VS_CACHE` is 512 (`sh_work.c:238`). Each new variant costs one `D3DCompile` on first use, as any new VP does today.

**(b) Branch at runtime on a per-draw cbuffer value.** This is how RPCS3 does it (KNOWN):
- The shader declares `transform_branch_bits` in its vertex context (`GL/GLVertexProgram.cpp:37`, `VK/VKVertexProgram.cpp:408`).
- It is filled from the 0x1FF8 register every draw (`Core/RSXDrawCommands.cpp:625`, read via `rsx_methods.h:1277-1280`).
- So there is one shader per microcode and no variants.
- For us it would mean:
  - a new cbuffer field emitted by the shared decompiler, which the draw engine and live draw use too;
  - a root signature or cbuffer layout change in the legacy backend;
  - a per-draw fill in `vp_record_cb`.
- That is more surface for the first fix. Keep it as a follow-up if the census shows many 0x1FF8 values per microcode (shader-compile hitches). VERIFY then.

**CLB** (call-if-bit) goes through the same bit test in the decompiler (L526-531) and uses the same key, so (a) covers it. Harness T6 checks it. None of the three dumped programs uses CLB.

## The fix (diff)

| file | base copy | md5 before | md5 after |
|---|---|---|---|
| `rsx_vp_decompiler.c` | `/workspace/faces/src` (Nov 25 00:54; same as `salem_lf` apart from line endings) | 95f82341 | 72c5d436 |
| `rsx_vp_decompiler.h` | `/workspace/faces/src` | 1de8076d | d5313184 |
| `rsx_d3d12_backend.c` | `/workspace/faces/sh_work.c` (Nov 26 20:38) | c66d52a1 | 8762e276 |
| `rsx_d3d12_backend.c` | 1786_movie_v5 copy, `/workspace/blackhang/video/rsx_d3d12_backend.c.orig` (from video_in.zip, file time Nov 27 17:56) | 2302fda0 | a88d41cb |

The v5 backend differs from `sh_work.c` by 136 lines elsewhere, but the 3 functions this diff touches are identical in both (KNOWN, diffed).

- `diffs/branch-bits.diff`: unified diff (LF-normalised) for the decompiler .c/.h and `sh_work.c`. `git apply --check` is clean on LF copies.
- `diffs/backend_1786v5.diff`: the same backend hunks against the v5 copy, which is the tree Run A was built from.
- `patched/`: the 4 patched files with their original line endings. `sh_work.c` has mixed CRLF/LF, and the patch keeps the CRLF in the patched region.

What changes:
1. **Decompiler:** adds `u32 rsx_vp_branch_bits_mask(ucode, bytes)`, which ORs `1<<D3[23:27]` over every BRB/CLB up to the end bit, and declares it in the header. It does not change existing behaviour.
2. **Backend:** adds `vp_branch_key_bits(st, vuc, vlen)`, which returns `st->transform_branch_bits & mask`.
   - Setting `VP_BRANCH_BITS_OFF=1` makes it return 0, i.e. the old behaviour in the same exe, for A/B.
3. **Backend `vp_get_vs`** (the per-draw VS, called at record time with the live state, so the bits match that draw):
   - When the key bits are non-zero, they are folded into the VS cache hash. That hash is also the `vs_hash` in the FP PSO key (`sh_work.c:2381`), so PSOs separate too.
   - The bits are set around `rsx_vp_decompile`, then reset to 0, so the base VS (`compile_vp`) and other callers are unchanged.
   - It logs `[VPBB] vp <ucode hash> branch bits <bits> -> key <key>`, first 16 only.
4. **Backend `faces_ctl_deep`** (FACES_CTL `deep` dump):
   - It dumps with the draw's own bits.
   - The file name becomes `faces_vp_<hash>_b<bits>.hlsl` when the bits are non-zero.
   - The header gains `branch bits 0x.. (0x1FF8 = 0x..)`.

Not in this diff (one change per build):
- The legacy path also never calls `rsx_vp_set_branch_base`, so a program with `transform_program_start != 0` would get absolute branch targets. All 14 programs dumped on the box start at 0, so they are not affected (KNOWN). Other programs: VERIFY.
- The base VS from `compile_vp` stays at bits 0. It is used only when a per-draw VS fails to compile (`sh_work.c:2340`).

## Apply / revert (test copy only, after Saud's OK)

```
python apply_branch_bits.py --video C:\<test-copy>\ps3recomp\libs\video             (dry run, prints the diff)
python apply_branch_bits.py --video C:\<test-copy>\ps3recomp\libs\video --write     (keeps *.bb.bak)
python apply_branch_bits.py --video C:\<test-copy>\ps3recomp\libs\video --revert
```

- Every anchor has to match exactly once, or nothing is written. Running it twice does nothing.
- If the backend file has another name, add `--backend <file>`.
- Tested on the box: the patch applies to `sh_work.c` and to the v5 copy. The second run reports "already patched". The revert is byte-identical to the original.
- The census hook from `tools/rsx_census` can sit in the same test build: it only logs, and its anchors don't overlap.

## Harness on the box (`harness/`)

`harness/run.sh` builds the **patched** decompiler with gcc and clang. It also extracts `vp_hash_ucode`, `vp_branch_key_bits` and the key fold verbatim from the patched backend (`harness/key_logic.inc`). It then runs these checks against the 1776 dumps:

| test | result |
|---|---|
| T1 tested-bit mask: 3F083BFF 0x7, 6A46C9BA 0x1, D54F73A6 0x6 | pass |
| T2 bits=0 output of 6A46C9BA is byte-identical to the 1776 dump's HLSL (46 instrs) | pass |
| T3 bits=0: `BRB @14` emits `_pc = 29;` (block 15-28 unreachable); bits=1: emits `_pc = 15;`, and block 15 reads `vp_c[466]`, `vp_c[257]` | pass |
| T4 key: bits 0 or untested bit 0x100 give the old hash 0x6A46C9BA; bit 0 gives a new key 0x967C6A6B; 0x101 gives the same key as 0x1 | pass |
| T5/T6 synthetic BRB and CLB, both polarities × bit clear/set | pass |

- **Result:** `BRANCH-BITS HARNESS PASS (0 failures)` with gcc and with clang. Clang gave 0 warnings.
- The one gcc warning (`-Wformat-truncation` in the LIT case) is already in the unpatched file. The patch adds none.
- The only difference between `harness/out_6A46C9BA_bits0.hlsl` and `harness/out_6A46C9BA_bits1.hlsl` is line 96: `_pc = 29;` vs `_pc = 15;`.
- **Limits:**
  - The backend can't be compiled on Linux (D3D12). Its new lines are checked only through the verbatim extraction above, and `faces_ctl_deep` was not compiled. VERIFY on the PC build.
  - The lit HLSL has not gone through `D3DCompile` on the box. The same block is already in the bits=0 shader as dead code, so it is ASSUMED to compile.

## Risks

- **Shader cache growth:** up to 2, 4 and 8 variants for the three known programs. Each costs one compile hitch on first use. VP_VS_CACHE is 512.
  - If the cache ever fills, eviction shifts the slots. That code is unchanged, and the PSO key keeps `vs_hash`.
- **Shadow VP `0xD54F73A6`** (the depth-only pass, draws #0-#311 at the blacksmith) tests bits 1 and 2. With real bits it runs bodies it has never run before; they look like matrix/`a0` work on `vp_c[260..262]`.
  - This can move or change the shadow map. Shadow acne is currently ×1.12, close to the reference. Watch it.
  - `VP_BRANCH_BITS_OFF=1` gives the before picture in the same exe.
- **Never-executed HLSL now runs:** lighting math (specular exp2, LIT) that has never run on our side. Faults could be over-bright, NaN or black props. Compare against RPCS3, not against our old picture.
- **Correct but no visible change:** if the census shows 0x1FF8 = 0 (or no tested bit set) at the spot, the patch changes nothing and the dim props have another cause. That outcome is also an answer.

## Test plan for Salem (after Saud's OK)

1. Apply to a test copy of the 1786_movie_v5 tree, with the census hook too if it isn't already in, and build it as a new exe, for example `1788_bbits`. Change nothing else.
2. **Census first (decides the rest):** same blacksmith tour stop as Run A, `RSX_CENSUS=<sec>,2` and `DRAW_LIST=<sec>`.
   - In `rsx_census.txt`, read the `M,0x1FF8,...` line: writes, distinct values, last, and draws_nondef.
   - If the tested bits (0x1 for the prop VP) are never set, stop and report. The fix is inert at this spot.
3. **Same spot, two runs from the same exe, same camera:**
   - A: `VP_BRANCH_BITS_OFF=1`
   - B: unset
   - Expect `[VPBB] vp 0x6A46C9BA branch bits 0x00000001 -> key 0x967C6A6B` (or similar) in B's stderr, and none in A.
4. **Shots:** the blacksmith prompt view in both runs, plus the RPCS3 ref `village_blacksmith.png`.
   - Measure with `python gfx_bisect.py diagnose ours.png ref.png --out diag_A` (and `diag_B`). On the box this is `tools/gfx_bisect`.
   - Read dark roofs, sign and noticeboard (where the old values were ×0.53-0.68), shadow acne and MAE.
   - Also compare A against B directly.
5. **Optional confirmation of the shader:** `FACES_CTL` `deep` on one prop draw in run B should write `faces_vp_6A46C9BA_b1.hlsl` with `_pc = 15;` after BRB @14.
6. **Face close-up spot:** repeat steps 3-4 at that spot, to check for regressions.
7. **Send back:** the census txt, the `[VPBB]`, `[VP]` and `[CENSUS]` lines, the 2+2 shots, the diagnose `report.md` files, the exe name and the bat env lines.
8. Revert with `--revert`. Keep the build as a test build until Saud decides.

The claim "this fixes the dim props" stays ASSUMED until step 4 shows roof/sign/board moving toward the reference **with** the census showing the tested bit set.
