# rsx_census: unhandled RSX method census (legacy D3D12 path)

Strikeforce (BLUS30471) port, ps3recomp legacy D3D12 backend, draw_engine_enabled=0.
Built on the box on 2026-11-27. It is a logging-only tool: it changes no rendering and contains no GPL or RPCS3 code.
Labels: **KNOWN** means read in source or measured, **ASSUMED** means reasoned, **VERIFY** means a test is still needed.

The goal is one log run that lists every NV4097 method the game writes that our legacy path ignores, ranked by how many draws are issued while that method holds a non-default value.

## Files

| file | what |
|---|---|
| `gen_coverage.py` | Static scan of Salem's tree. Writes `coverage.json` and `coverage.md` (handled / stored-but-unused / unhandled for every method 0x0000-0x1FFC). |
| `nv4097_names.py` | Public NV40/RSX method names and offsets (facts only). Names from `rsx_commands.h` take precedence. |
| `coverage.json`, `coverage.md` | Output of the scan of `/workspace/faces/src` plus `/workspace/faces/sh_work.c`. |
| `census_hook.c` | Part A of the hook: self-contained, fixed arrays, gated by `RSX_CENSUS`. |
| `apply_census.py` | Inserts the 4 hook lines into a **test copy** of the tree. It does a dry run (diff) by default and has `--write` and `--revert`. |
| `harness/` | Box harness (gcc/clang) that compiles the hook with stub types and checks the counts on a synthetic method stream. |
| `census_report.py` | Analyzer: reads `rsx_census.txt` plus `coverage.json` and writes `report.md` and `report.html`. |
| `test_synthetic/` | Report built from the harness output (a test of the analyzer). |
| `partial_methlog/` | PARTIAL report from the only real method log on the box (`/workspace/faces/s2/ml_all.txt`, `[METHLOG]`). |

## Static coverage (gen_coverage.py)

Sources scanned (newest copies on the box):
- `rsx_commands.c` / `.h`, `cellGcmSys.c`, `rsx_vertex_fetch.c`, `rsx_texture_layout.c`, `rsx_draw_engine.c` and `rsx_dispatch.c` from `/workspace/faces/src`. These are `rsx_commands.c` md5 3720caf7 (Nov 26 15:29) and `.h` a201ae5f.
- Backend: `/workspace/faces/sh_work.c` (md5 c66d52a1, Nov 26 20:38). It is newer than `src/rsx_d3d12_backend.c` (15:29). The later `diag3/rsx_d3d12_backend.c` (22:20) gives an identical classification.

Rules:
- **handled** means `rsx_process_method` stores the state and the D3D12 path, `rsx_vertex_fetch.c` or `rsx_texture_layout.c` reads it outside printf. It also covers methods that act directly: a backend call, a guest write, a label or semaphore, or the FIFO walker.
- **stored-but-unused** means the state is stored but only logs read it, or nothing reads it.
- **unhandled** means there is no branch, so the method falls through to `return -1`. A method that only `rsx_draw_engine.c` handles still counts as unhandled, because that engine is off.

The classes are mechanical (ASSUMED). The overrides carry file:line evidence and are KNOWN.

Top gaps (named render-state methods):

| method | name | class | label |
|---|---|---|---|
| 0x0A60/0x0A64/0x0A68 | POLY_OFFSET_POINT/LINE/FILL_ENABLE | unhandled (draw engine has it) | ASSUMED |
| 0x0A78 / 0x0A7C | POLYGON_OFFSET_SCALE_FACTOR / BIAS | unhandled (draw engine has it) | ASSUMED |
| 0x08CC / 0x08D0 / 0x08D4 | FOG_MODE / FOG_PARAMS[0..1] | unhandled (no engine has it) | ASSUMED |
| 0x1D78 | ZMIN_MAX_CONTROL | unhandled (draw engine has it) | ASSUMED |
| 0x1738 / 0x173C | VERTEX_DATA_BASE_OFFSET / BASE_INDEX | unhandled (dispatch has it) | ASSUMED |
| 0x0394 / 0x0398 | CLIP_MIN / CLIP_MAX | unhandled: no branch, `clip_min/max` fixed at 0/1 in `rsx_state_init` and only printed | ASSUMED |
| 0x0A20/24/2C, 0x0A30/34/3C | VIEWPORT_OFFSET / SCALE x,y,w | stored-but-unused: the epilogue forces x/y/w to identity, z only (sh_work.c:3693-3699) | KNOWN |
| 0x0A28 / 0x0A38 | VIEWPORT_OFFSET.z / SCALE.z | handled (depth remap) | KNOWN |
| 0x08C0 / 0x08C4 | SCISSOR_HORIZONTAL / VERTICAL | stored-but-unused: the backend always sets a full-window scissor (sh_work.c:5273) | KNOWN |
| 0x1FF8 | TRANSFORM_BRANCH_BITS | stored-but-unused: the legacy path never calls `rsx_vp_set_branch_bits`, so BRB/CLB always see 0 | KNOWN |
| 0x0900-0x097C | VERTEX_TEXTURE_* (4 units) | stored-but-unused: the backend never reads `vertex_textures` | ASSUMED |
| 0x034C / 0x0354 / 0x0358 | BACK_STENCIL_MASK / FUNC_REF / FUNC_MASK | stored-but-unused: the zs key uses only back func/ops | ASSUMED |
| 0x031C / 0x037C / 0x036C | BLEND_COLOR / BLEND_COLOR2 / BLEND_ENABLE_MRT | unhandled | ASSUMED |
| 0x0380-0x0388 | DEPTH_BOUNDS enable/min/max | unhandled | ASSUMED |
| 0x1828 / 0x182C, 0x0368, 0x0374/0x0378 | polygon mode, shade mode, logic op | unhandled | ASSUMED |
| 0x0B00-0x0B3C, 0x0B40-0x0B64 | TEXTURE_CONTROL2, TEX_COORD_CONTROL | unhandled | ASSUMED |
| 0x1500.., 0x1880.., 0x1900.., 0x1940.., 0x1980.., 0x1E40.., 0x0A80.. | VERTEX_DATA 3F/2F/2S/4UB/4S/1F/SCALED4S | unhandled (only 4F at 0x1C00 is handled) | ASSUMED |
| 0x1FF0 / 0x1FF4 | VERTEX_ATTRIB_INPUT/OUTPUT_MASK | stored-but-unused | ASSUMED |

`d3d12_set_viewport` is a TODO no-op at sh_work.c:6661 (KNOWN).

Static scans can't tell which of these the game actually writes, or on which draws. The census run answers that.

## Hook design (census_hook.c)

- **Gate:** env `RSX_CENSUS=<start_sec>[,<frames>]`, with frames defaulting to 2. Set `RSX_CENSUS_OUT=<file>` to change the output (default `rsx_census.txt` in the working folder). With no env set, the cost is one `if (s_rsxc_mode)` per method.
- **Window:** values are tracked from boot, so a value set once at load is seen. The window opens at the first frame end after `<start_sec>`, measured with the same `clock()` process-age clock as `DRAW_LIST`. With the same integer seconds in `DRAW_LIST` and `RSX_CENSUS`, both cover the same frames, and draw `#N` in the census is draw `#N` in `[DRAWLIST]`.
- **Per method, 0x0000-0x1FFC:**
  - writes in the window and since boot
  - first value ever, first value in the window, and the last value
  - up to 8 distinct values in the window, including the value held at window start
  - **draws affected**: window draws issued while the value differs from the reference. The reference is the reset default from a small table (4 entries copied from `rsx_dispatch_init`, which are KNOWN; the rest are ASSUMED) or, failing that, the first value ever written.
  - draws after first write
- **Per draw:** frame, draw index, and a 64-bit mask over 55 watched gap methods (up to 16384 draw records).
- **Storage:** about 200 KB of static arrays, no heap. It writes one file at the end of the window, then goes idle.
- **Rendering:** unchanged. The hook only reads `(method, data)` and writes its own statics.

## Exact paste points

Paste into a **test copy** only. Saud approves before anything is built (team rule).

Use `apply_census.py` or paste by hand. The anchors are text, so line numbers may shift in your tree.

1. **Copy** `census_hook.c` to `ps3recomp\libs\video\rsx_census_hook.inc`.
2. **`rsx_commands.c`: include.** Put this directly ABOVE `int rsx_process_method(rsx_state* state, u32 method, u32 data)` (box copy `faces/src/rsx_commands.c` L455, just below `volatile unsigned g_sf_rsx_ring_pos = 0;`):
   ```c
   #include "rsx_census_hook.inc"   /* RSX_CENSUS (log-only) */
   ```
3. **`rsx_commands.c`: call.** Inside `rsx_process_method`, put this on the line right AFTER the ring breadcrumb `{ unsigned _p = g_sf_rsx_ring_pos++ & 511u; ... }` (L457 before the include; it sits next to the SF_METHLOG block):
   ```c
       if (s_rsxc_mode) rsx_census_method(method, data);   /* RSX_CENSUS (log-only) */
   ```
4. **`rsx_d3d12_backend.c`: draw call.** In `sf_draw_gate`, put this right AFTER `u32 idx = s_sf_fdraw++;`. That is L6258 in `faces/src/rsx_d3d12_backend.c`, L6405 in `faces/sh_work.c` and L6573 in `faces/diag3`.
   ```c
       { extern void rsx_census_draw(unsigned); rsx_census_draw(idx); }   /* RSX_CENSUS (log-only) */
   ```
5. **`rsx_d3d12_backend.c`: frame-end call.** In the body of `static void sf_draw_gate_frame(void)` (the definition, not the forward declaration), put this as the first line after `{`. The definition is at L6280 in `faces/src` (insert at L6282), L6428 in `sh_work.c` (insert at L6430) and L6596 in `diag3`.
   ```c
       { extern void rsx_census_frame(void); rsx_census_frame(); }   /* RSX_CENSUS (log-only) */
   ```
   This is the place `DRAW_LIST` already uses for its frame boundary, triggered by a `cellGcm_flip_request_count` change. Step 4 counts every backend draw before `DRAW_RANGE` or FACES_CTL can skip it.

`apply_census.py` does steps 1-5. It matches each anchor exactly once, keeps `.census.bak` backups and handles CRLF files:

```
python apply_census.py --video C:\<test-copy>\ps3recomp\libs\video            (shows the diff only)
python apply_census.py --video C:\<test-copy>\ps3recomp\libs\video --write    (applies it)
python apply_census.py --video C:\<test-copy>\ps3recomp\libs\video --revert   (undo)
```

Checked on the box: a patched copy of `rsx_commands.c` passes `gcc -fsyntax-only -Wall` with stub ps3emu headers and gives 0 warnings. The backend lines were inserted and diffed, but the backend can't be compiled on Linux (D3D12).

## Windows run (Salem)

The spot is the same as Run A: build 1786_movie_v5 at the blacksmith tour stop, then the frontal face close-up (gatekeeper/noticeboard soldier, #4).

1. Get Saud's OK for this code change (logging only).
2. Make a test copy of the 1786_movie_v5 tree, apply steps 1-5 above, and build it the usual way under a new name, for example `1787_census`.
3. Copy the Run A launcher `.bat` and change only these lines. Use integer seconds, picked so the camera is already idle at the spot (the same timing you used for the Run A shots):
   ```
   set RSX_CENSUS=<sec>,2
   set RSX_CENSUS_OUT=play_logs\rsx_census_blacksmith.txt
   set DRAW_LIST=<sec>
   ```
   Keep every other env var exactly as in Run A, including the DRAW_LIST frames. Don't set `DRAW_RANGE` or a skip.
4. Run it. Expect these lines in stderr: `[CENSUS] armed ...`, `[CENSUS] window open at X s`, `[CENSUS] wrote play_logs\rsx_census_blacksmith.txt: 2 frames, N draws`.
5. For the second run, at the face close-up, use the same exe with `RSX_CENSUS_OUT=play_logs\rsx_census_face.txt` and that spot's seconds.
6. Send back:
   - the two `rsx_census_*.txt` files (small, plain text)
   - the `[CENSUS]` and `[DRAWLIST]` lines from each stderr (`findstr /C:"[CENSUS]" /C:"[DRAWLIST]" ...`)
   - one screenshot of each spot from that run
   - the exe name and the exact env lines of the bat

   Nothing else is needed, and no game files.
7. Keep the census build as a test build only. Undo the edits with `--revert`.

## Analyzer

```
python3 gen_coverage.py                         # refresh coverage.json if the tree changed (--src, --backend)
python3 census_report.py rsx_census_blacksmith.txt --out reports/blacksmith --title "1787 blacksmith"
python3 census_report.py --methlog stderr.txt --out reports/partial        # PARTIAL, [METHLOG] lines only
```

`report.md` and `report.html` contain:
- **Ranked gap table** with method, name, class, writes, distinct values, **draws affected**, draws after first write, reference, decoded samples (floats for offset, fog, viewport and clip registers), the register meaning (KNOWN) and a separate open-bug link column (ASSUMED).
- **Per-draw view** listing the draw ranges (DRAW_LIST numbering) on which each watched method was non-default.
- **Context table** of handled methods.

The section headers are in Arabic with short English.

## Results on the box

- **Harness** (`harness/harness_result.txt`): HARNESS PASS with gcc `-std=c99 -Wall -Wextra -Wpedantic -Wshadow` and with clang 19, 0 warnings. It checked 11 methods plus the total draw count: draws affected, the distinct-value cap and overflow, a value set at boot, a first write inside the window, the default compare versus the first-value compare, and a value held from before the window. The off test (no env) passed: nothing recorded, no file written.
- **Synthetic report:** `test_synthetic/report.md`.
- **Partial census:** `partial_methlog/report.md`. The only real method trace on the box is `/workspace/faces/s2/ml_all.txt`, and its `[METHLOG]` build watched only 0x0310 (BLEND_ENABLE, handled) and 0x1FEC (NO_PARANOID_TEXTURE_FETCHES, unhandled, values 0/1). It is too narrow to rank anything; it is labelled PARTIAL. No `[rsxm]` traces exist on the box.

## Limits

- Classification is a regex and condition-evaluation scan (ASSUMED). A field read inside a non-printf debug branch counts as "read". Evidence lines in `coverage.json` let each claim be VERIFIED by eye.
- Vertex-program microcode and constant runs that take the `rsx_process_vp_run` fast path bypass `rsx_process_method`, so 0x0B80.. and 0x1F00.. counts are low. Those are handled methods, so the gap ranking is unaffected.
- Methods consumed upstream in `cellGcmSys.c` (2D subchannels, NV406E semaphores) never reach the hook.
- "Draws affected" depends on the reference value. For a method with no reset default in the table, a value set once at boot counts 0. Read "draws after first write" and the reference column for those (fog is the main case).
- Per-draw masks cover 55 watched methods only. All other methods get totals, not per-draw bits.
- Reset defaults: the 4 values copied from `rsx_dispatch_init` (COLOR_MASK, FRONT_FACE, ZSTENCIL_CLEAR, ZMIN_MAX_CONTROL) are KNOWN. The rest are ASSUMED and need checking against the GCM docs.
- Method names marked "(name VERIFY)" in `coverage.md` are from memory and lower confidence.
- The hook assumes the FIFO thread does both the methods and the draws (single thread, as the `s_backend` calls in `rsx_process_method` show). ASSUMED.
