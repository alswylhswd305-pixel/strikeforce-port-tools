# Innovative ideas: faster, lower-risk PS3 → PC (Strikeforce now, any title later)

> **CORRECTION 2026-11-26 12:32 (UTC+3), from Salem's in-stage measurements:** the subchannel-1 / NV0039 lead was **wrong for Strikeforce**. There are no subchannel-1 methods in the 3D range and no SET_OBJECT in the stream, and the in-stage cmask is 0x01010101. The register collision described below is real as a *class* of bug (envytools, PSL1GHT and Demon's Souls fix 141 are still correct), but it is **not** this game's cause. The real cause was a shadow-map clear with no colour target being treated as a frame start. For the remaining olive world, see olive-world-researcher.md.


2026-11-26, ~12:45 UTC+3. Research only; nothing was run, and Saud's PC was not touched.

Pins:
- **P** = ps3recomp `e85647a33ce5f9391788f0e3f52ab395a7fe6a89`. `P/` = https://github.com/sp00nznet/ps3recomp/blob/e85647a33ce5f9391788f0e3f52ab395a7fe6a89/
- **R** = RPCS3 `0ca5eb0efe50ec4e8aa07892ab86d57842246eb4`. `R/` = https://github.com/RPCS3/rpcs3/blob/0ca5eb0efe50ec4e8aa07892ab86d57842246eb4/rpcs3/

Effort scale (ASSUMED, for one person who knows the codebase):
- **S** ≤ 1 day
- **M** 2-5 days
- **L** 1-3 weeks

The "payoff" rank is a judgement, not a measurement.

## Ranking (payoff ÷ effort)

| # | Idea | Payoff | Effort | Directly helps Strikeforce |
|---|---|---|---|---|
| 1 | Subchannel/register-collision tripwire | high | S | colour/blend bug class (today's lead) |
| 2 | Per-draw RSX register diff against an RPCS3 `.rrc` | high | S-M | visual fidelity |
| 3 | Replay an RPCS3 `.rrc` through ps3recomp's renderer, pixel-diff against RPCS3's own replay | very high | M | "match the original exactly", frame-exact |
| 4 | HLE struct-layout checker (RPCS3 header offsets vs ps3recomp offset macros) | medium-high | S-M | SPURS/sync structs |
| 5 | Load-bearing-NID bisection in the auto-loop | medium | S | remaining unresolved NIDs |
| 6 | HLE differential testing: record in RPCS3, replay against ps3recomp HLE | very high | L | event-flag-type semantic bugs |
| 7 | Cloth image: lift each Ovis overlay separately and dispatch by verified residency | medium | M | SPU cloth (now interpreted) |
| 8 | Symptom → switch → fix knowledge base, feeding upstream PRs | medium | S (ongoing) | every blocker so far |
| 9 | One-command pipeline per new title | high (next game) | M | future titles |
| 10 | Local LLM log triage (Ollama) | low-medium | S | triage only |
| 11 | Mid-run snapshots to skip boot | high | L | iteration speed |

---

### 1. Subchannel/register-collision tripwire (S)

**What:**
- **Step 1:** in the FIFO walker, track each subchannel's `SET_OBJECT` handle (method 0), as `GCM_OBJDBG` already prints.
- **Step 2:** log once per (subchannel, method) whenever a method arrives on a non-zero subchannel and all three hold:
  - it is routed to the 3D bank;
  - its offset is NV4097 *state* (e.g. 0x0300-0x03FC);
  - the subchannel is **not** bound to the same object as subchannel 0.
- **Step 3:** optional `GCM_SUBCH_STRICT=1` to route such methods by binding instead.

**Why:**
- Today's colour-mask lead is exactly this. P routes subchannel 1 to 3D by default (`P/libs/video/cellGcmSys.c#L2917-L2925`, `#L3087`), and NV0039's `FORMAT` (0x2324, `R/Emu/RSX/gcm_enums.h#L763`) would land on `COLOR_MASK` 0x0324.
- A tripwire turns a multi-hour visual hunt into one log line, for every future title.

**Builds on (KNOWN):**
- the `GCM_OBJDBG` handle log (`P/libs/video/cellGcmSys.c#L2972-L2985`);
- RPCS3's full-address register file (`R/Emu/RSX/RSXFIFO.cpp#L67`).

**Verify:** on Strikeforce the tripwire should name `subch=1 0x0324` in-stage. Then `GCM_SUBCH1_2D=1` should restore the ground, sky and character (colormask report, check 2). Unit test: feed the walker an NV0039 sequence on subchannel 1 and assert `COLOR_MASK` stays unchanged.

### 2. Per-draw RSX register diff against an RPCS3 capture (S-M)

**What:**
- **RPCS3 side:** extend `tools/parse_rrc.py` (it already keeps a register file while decoding, `P/tools/parse_rrc.py` `decode()` `regs[reg] = val`) to emit, for every draw, the full NV4097 state block as JSON: surface, colour mask, blend, depth/stencil, cull, viewport, scissor, FP/VP addresses, texture 0-15 control words.
- **Port side:** emit the same JSON from `rsx_state` at each draw. This is a local hook beside `RTT_DUMP` (`P/libs/video/rsx_d3d12_backend.c#L4731-L4742`).
- **Then:** align by (frame, fragment-program code hash, vertex count) and print only differing registers.

**Why:** an RPCS3 RSX capture is a byte-exact record of what the real game sent (`.rrc`: commands plus memory, `R/Emu/RSX/Capture/rsx_capture.cpp`). A register diff would have shown `COLOR_MASK 0x00000101 vs 0x01010101` directly, and will catch blend, depth or format mismatches the same way.

**Builds on (KNOWN):**
- `parse_rrc.py` (format notes in its header, `P/tools/parse_rrc.py#L1-L19`);
- RPCS3's capture hotkey Alt+C (`R/rpcs3qt/shortcut_settings.cpp#L87`). Saud approved RPCS3 captures at 11:46.

**Verify:** run it on the in-stage frame. The expected first hit is the mask/blend registers. A clean menu frame should diff empty, which is the control.

**Limit (ASSUMED):** draw alignment can drift if the port drops or merges draws. P merges batches (`P/libs/video/rsx_d3d12_backend.c#L7425-L7442`, the `merge_prev_draw` path), so align on draw groups.

### 3. Replay an RPCS3 capture through ps3recomp's renderer, then pixel-diff (M)

**What:** a host tool that:
- loads an `.rrc`;
- writes its memory blocks into a fake guest VM;
- replays its command list into `rsx_process_method` and the D3D12 backend;
- dumps the frame.

RPCS3 replays the same `.rrc` itself (`main_window::BootRsxCapture`, `R/rpcs3qt/main_window.cpp#L728`). Pixel-diff the two images.

**Why:** this removes everything that makes visual comparison unreliable (timing, PPU/SPU/HLE state, input, reaching the stage). It gives **the same frame, the same inputs, and two renderers**.
- Every visual bug becomes a deterministic, single-frame test case, without booting the game.
- A fixed frame becomes a regression test.

**Builds on (KNOWN):**
- `P/libs/video/tests/rsx_harness_main.c` already drives the RSX command processor and D3D12 backend over fake guest memory (header L1-L20);
- `parse_rrc.py` already reads the `.rrc` format;
- `regress.py --shots` handles frame dumps (`P/tools/regress.py#L187`, `#L318`).

**Effort:** M. The parser and harness exist. The new parts are the memory/tile setup from `.rrc` and a deterministic present. The RPCS3 `.rrc` format version is pinned in `parse_rrc.py` (`c_fc_version 6`). KNOWN: it matches R's `Emu/RSX/Capture/rsx_replay.h#L14` (`c_fc_version = 0x6`).

**Verify:** start with an RPCS3 capture of a menu frame Salem already renders correctly; it should come out near-identical. Then the stage frame.

**Licence (KNOWN rule):** the tool reads a data format and must not copy RPCS3 code (`P/CONTRIBUTING.md#L260`: "Don't port code from GPL projects").

### 4. HLE struct-layout checker (S-M)

**What:**
- **RPCS3 side:** run `clang -Xclang -fdump-record-layouts` over RPCS3's module headers (e.g. `R/Emu/Cell/Modules/cellSpurs.h`) to get exact field offsets as JSON. Those are facts, not code.
- **ps3recomp side:** compare them with ps3recomp's offset macros and structs. ps3recomp HLE mostly uses named offsets, e.g. `#define EF_ADDR 0x70` (`P/libs/spurs/cellSpurs.c#L253`). A small per-struct mapping file (`EF_ADDR ↔ CellSpursEventFlag.addr`) turns this into a build-time check.

**Why:**
- RPCS3 documents offsets and sizes: `CellSpursEventFlag` has `spuPort` at 0x0C, `isIwl` at 0x0D, `addr` at 0x70, and `CHECK_SIZE_ALIGN(..., 128, 128)` (`R/Emu/Cell/Modules/cellSpurs.h#L886-L918`). cellSpurs.h alone has 27 CHECK_SIZE/static_assert lines.
- P's `libs/` has only 11 `static_assert`s in total (git grep at P).
- Layout bugs (`CellFsStat`, `CellGcmContextData`) are a known class (`P/tools/dwarf_abi.py#L1-L16`).

**Builds on (KNOWN):**
- `tools/dwarf_abi.py --diff-headers` already diffs layouts, but needs a DEBUG build's DWARF, which retail Strikeforce doesn't have;
- `tools/hle_abi_audit.py` already reads RPCS3 **signatures only** as ground truth, under the same no-GPL-code rule (`P/tools/hle_abi_audit.py#L1-L20`).

**Honest limit (KNOWN from this project):** the event-flag bug was wrong *values* (`isIwl=0`, `addr=0`) at correct offsets, so a layout check would not have caught it. Idea 6 would.

**Verify:** the checker should report zero differences on structs known to be right. Then seed one deliberate wrong offset and confirm it is caught.

### 5. Load-bearing-NID bisection (S)

**What:**
- Add `PS3_HLE_UNRESOLVED_FAIL=<nid,nid,…>` (local, a few lines in `ps3_hle_unresolved`, `P/runtime/ppu/ppu_hle.cpp#L202-L240`) so that only the listed NIDs return an error.
- The auto-loop then bisects the unresolved set: does the run still reach the same milestone (`PS3_MILESTONE_OUT`) with half of them failing?
- Output: the NIDs that actually change behaviour, so they get real HLE first; the rest can stay faked.

**Why:**
- Today `PS3_HLE_UNRESOLVED=fail` is all-or-nothing (`#L218`), and the default fakes `CELL_OK` for every missing import.
- The milestone log already lists the called NIDs with bucketed counts (`P/runtime/milestone.c#L214-L252`).

**Verify:** a known load-bearing import, removed on purpose, must come out of the bisection on its own.

### 6. HLE differential testing against RPCS3 (L, highest ceiling)

**What:** for every HLE function Strikeforce calls (the import list in `EBOOT.imports.json`):
- **Record in RPCS3** at the import entry and at its return address: args r3-r10 and the bytes of every pointer argument (struct pre-state), then r3 and the struct post-state.
- **Replay each record** into ps3recomp's HLE function over a fake guest memory. The technique is `P/tools/test_lwcond_layout.py`, which builds real HLE functions into a small host program over stubbed memory (header L1-L13).
- **Diff** r3 and the post-state bytes. Mask kernel IDs and pointers that are allowed to differ; compare those relationally.

**Why:** this is the only idea here that finds **semantic** bugs automatically. Example: RPCS3's `_cellSpursEventFlagInitialize` writes `isIwl` and `addr` (`R/Emu/Cell/Modules/cellSpurs.cpp#L3267-L3269`). A post-state diff at +0x0D and +0x70 would have flagged our event-flag bug.

**Builds on (KNOWN):**
- **RPCS3 GDB stub driver:** `P/tools/rpcs3_probe/probe.py` (breakpoint plus memory-dump recipes, header L1-L19) and `rsp.py`.
- **Cheaper first pass:** RPCS3 already logs entry args of most HLE calls at warning level, e.g. `cellSpurs.warning("_cellSpursEventFlagInitialize(spurs=*0x%x, …)")` at `cellSpurs.cpp#L3269`. That gives args without a debugger.
- **Live memory reads:** RPCS3's PINE IPC (`R/Emu/IPC_socket.h#L6-L22`, pine_server plus read8/write8 and friends) can read guest memory while the game runs.

**Limits (KNOWN):**
- RPCS3 refuses PPU breakpoints with the LLVM decoder (`R/Emu/Cell/PPUThread.cpp#L1251-L1256`), so recording needs the slow interpreter.
- Whether RPCS3 runs libsre as HLE or LLE for this title decides which oracle you get. VERIFY in RPCS3's log.
- Functions whose effect is asynchronous (SPU side, event queues) need the post-state read later, not at return.

**Verify:** re-introduce the old `isIwl=0` behaviour in a branch; the diff must flag it.

### 7. Cloth SPU image: one lift per overlay, dispatched by verified residency (M)

**What:**
- `KSG2PS3SPUCloth.elf` uses overlapping overlays through cellOvis. Today it runs in the interpreter (`sf-shared/port-vs-rpcs3.md` L17-L18).
- Split it by the Ovis overlay table: lift each overlay segment separately, with its own symbol prefix and the same load LSA.
- Register each with `spu_overlay_register_verified_region` (`P/runtime/spu/spu_overlay_residency.h#L10-L31`). That API already marks an overlay resident when its DMA source EA lands, verifies the code bytes once, and dispatches by residency, so overlapping spans are handled.

**Why:** the cloth task moves from the interpreter to native code, with no new runtime mechanism.

**Builds on (KNOWN):**
- the residency API above;
- `lift_jobmods.py --engine-elf`, which registers modules as verified streamed regions keyed by source EA (`P/tools/lift_jobmods.py#L22-L28`);
- `SPU_INTERP_STATS` to see the interpreted hot spots before and after (`P/runtime/spu/spu_interp.c#L401`).

**Verify:**
- `SPU_INTERP_STATS` shows no cloth PCs.
- The cloth looks the same as the interpreter run: Zhao Yun's ponytail and banner, compared with idea 3.

**ASSUMED:** the Ovis table gives each overlay's source EA and LSA. VERIFY from `strikeforce_ovis.inc`.

### 8. Symptom → switch → fix knowledge base (S, ongoing)

**What:** one table per blocker: symptom, the env switch that showed it, root cause, fix, upstream status. For example:
- "nothing visible" → `D3D12_DROP_STATS` → `rt_off==0` gate;
- "colours wrong" → `GCM_OBJDBG` → subchannel-1 routing.

Generate the switch column from `P/tools/gen_diagnostics_index.py`, which already indexes every `getenv` with its comment.

Each fixed item becomes an upstream issue or PR draft. Posting needs Saud's or Salem's approval.

**Why:** most of today's blockers were already-known classes, e.g. the `rt_off` gate class that PR #747's drop counters exposed (git log at P: `205ccb7 Merge #747`), and Demon's Souls NOTES fixes 2, 5 and 6 (https://github.com/timboat/demons-souls-recomp/blob/9637b204f031c72839129d49e5b0586d4bcfdeed/docs/NOTES.md#L64-L90). The knowledge base makes "has someone hit this?" a lookup.

**Verify:** for the next new blocker, time how long until a matching entry or upstream issue is found.

### 9. One-command pipeline per new title (M)

**What:** `ps3port new <EBOOT> <USRDIR>` runs:
1. `pkg_extract`/`unfself`;
2. `spu_ident.py --db`, so known middleware (Edge zlib, Bink, Wwise) is identified and HLE'd instead of lifted (`P/tools/spu_ident.py#L1-L22`);
3. `extract_spu_images` + `build_spu_workloads`;
4. `find_functions` + `ppu_lifter --hle-stubs`;
5. `gen_hle_nids --all`;
6. the template project build;
7. `regress.py record`;
8. `auto_convert_loop.py`.

**Builds on (KNOWN):**
- `tools/harness/README.md` tiers: catalog, decrypt, profile, functions, lift, crosscheck;
- GoW Ascension's `prepare.ps1` bulk lift (https://github.com/bc160201983/GoW-Ascension-Recomp/blob/f4f19dc05840222668e4469241ac9ecd9178c56f/ascension/scripts/windows/prepare.ps1);
- Tornado `relift.sh` (https://github.com/sp00nznet/tornado/blob/2cc6c0fb660b62aab235e06ac8e0fa64106ec265/tools/relift.sh).

**Verify:** rebuild Strikeforce from scratch with it and diff the generated tree against the current one.

### 10. Local LLM log triage (S): useful, with hard limits

**What:**
- Ollama on Saud's PC, e.g. `qwen2.5-coder:7b` or `qwen3:14b` (https://ollama.com/library/qwen2.5-coder, https://ollama.com/library/qwen3; not pinned, library pages).
- Feed it the auto-loop's `report.json`, log tail and the knowledge-base table.
- Ask it to cluster errors, map them to knowledge-base entries, and draft a stub skeleton from a function's RPCS3 *signature* (the `hle_abi_audit` rule).

**Why:** a cheap first pass over long logs, offline, private.

**Limits (honest):**
- I have no source measuring these models on PS3 HLE semantics.
- ASSUMED: a 7B-14B model will invent struct offsets and return codes with confidence. Every claim it makes needs a source check (RPCS3 line or RE), exactly like ours.
- It must never write HLE bodies that get merged without that check.
- Needs VRAM on Saud's PC. VERIFY, by Saud.

**Verify:** give it three solved cases from today with the answer removed (`rt_off` gate, CMASK PSO cache, event flag) and see whether it ranks the real cause first.

### 11. Mid-run snapshots to skip boot (L)

**What:**
- Port-side save state: guest memory, PPU/SPU contexts, lv2 object tables, RSX state.
- inFamous 2's port has port-local `.p3ss` save states (earlier report, NOTES L155). P has none (git grep).
- RPCS3 has savestates (`R/Emu/savestate_utils.cpp`), but its format is RPCS3-internal.

**Why:** every iteration currently pays the boot-to-stage time.

**Cheaper stand-in (ASSUMED):** let the game save at the stage start, then `PAD_SCRIPT` straight into "Continue". Also, idea 3 removes the need to reach the stage for visual work.

**Risk:** host threads, D3D12 resources and HLE-side state that isn't in guest memory make a correct restore hard. Effort L.

## Suggested order for Strikeforce

1, then 2, then 5 (all S). Then 3 and 4 in parallel (M). Then 7. Idea 6 is the long-term guard against semantic bugs; start it with the warning-log variant (no debugger).
