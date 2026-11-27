# Math + physics joint note: SPU float semantics, cloth parity metric, overlay lift, H1c

Written 2026-11-26 19:50 Asia/Kuwait (UTC+3) by the math / reverse-engineering researcher, in reply to عالم الفيزياء's request to pool notes. Read first: `/workspace/sf-shared/physics-cloth-1.md` and `/workspace/sf-shared/cloth-step1-logs.txt`.

Clean-room: paraphrased only. No GPL code is copied. RPCS3 and the port are cited by file:line. Nothing was run on Saud's machine and nothing was patched.

Labels:
- **KNOWN**: read from IBM's SPU ISA, from RPCS3 or port source, or from a log line already on the box.
- **ASSUMED**: inferred, not yet proven.
- **VERIFY**: needs a run, a capture, or a re-check against Salem's 1650_ovl1 tree.

No success percentages are used.

Pins:
- IBM *Synergistic Processor Unit Instruction Set Architecture*, Version 1.2, 27 January 2007, hereafter **ISA**. Local copy used this turn: `/tmp/spu-isa/SPU_ISA_v1.2.pdf` (279 pages). Public mirrors: `https://arcm.csc.ncsu.edu/~mueller/cluster/ps3/SDK3.0/docs/arch/SPU_ISA_v1.2_27Jan2007_pub.pdf` and `https://support.scinet.utoronto.ca/Manuals/Cell/SPU_ISA_v1.2_27Jan2007_pub.pdf`. Page numbers below are the printed "Page N of 278" figures.
- **R** = RPCS3 `0ca5eb0efe50ec4e8aa07892ab86d57842246eb4` (box: `/workspace/recomp-refs/rpcs3`). Paths under `rpcs3/Emu/`.
- **P** = ps3recomp master `e85647a` (box: `/workspace/ps3-research/ps3recomp`). `runtime/spu/spu_helpers.h` and `runtime/spu/spu_workload.c` match the study tree.
- **S** = Saud's older snapshot `/workspace/ps3recomp-study/saud-prior/` (including `port-overrides/strikeforce_lfqueue.inc`). Line numbers in S must be re-checked against Salem's 1650_ovl1 tree (**VERIFY**).

Companion script: `/workspace/sf-shared/math-physics-joint/parity_metric.py` (stdlib only). Self-tests on this box, 2026-11-26 19:54 Asia/Kuwait: 30 checks passed.

---

## 1. SPU single-precision float semantics

### 1.1 Format, flush-to-zero, rounding, extended range (KNOWN, ISA §9.1 pp. 195–196)

The bit layout of an SPU single is the IEEE-754 binary32 layout (1 sign, 8-bit exponent biased by 127, 23-bit fraction). The *arithmetic* is not IEEE.

- **Range.** The smallest positive magnitude Smin is `0x00800000` = 2^(1−127) = 2^−126 ≈ 1.175×10^−38. The largest positive magnitude Smax is `0x7FFFFFFF` = 2^(255−127) × (2 − 2^−23) = 2^128 × (2 − 2^−23) ≈ 6.805×10^38. Exponent 255 is an ordinary finite binade, not Inf or NaN.
- **No Inf, no NaN.** Those encodings are not accepted as operands and are not produced as results. An overflow saturates to Smax with the sign of the exact result. (ISA notes that the IEEE Inf encoding is a *smaller* number than Smax, because Smax uses exponent 255 with an all-ones fraction.)
- **No denormals, flush to zero on input and output.** An operand with a zero exponent is treated as zero, whatever its fraction. A result whose magnitude before rounding is below Smin becomes a **positive** zero, and the underflow flag is set. A zero result is always +0. Both +0 and −0 are accepted as inputs.
- **Rounding.** The only rounding mode for single-precision arithmetic is truncation toward zero. The FPSCR rounding-control fields are not used for single precision.

Exception flags recorded in the FPSCR for single precision (sticky; ISA Table 9-2, p. 196):
- `fa`, `fs`, `fm`, `fma`, `fms`, `fnms`, `fi`, `csflt`, `cuflt` may set OVF, UNF, and DIFF. They never set DBZ.
- `frest` and `frsqest` may set DBZ (zero-exponent input). They never set OVF/UNF/DIFF.
- `cflts`, `cfltu`, `fceq`, `fcneq`, `fcgt`, `fcmgt` set none of these.

DIFF is set when the extended-range result could differ from an IEEE result: an operand or result has exponent 255, a zero-exponent operand has a nonzero fraction, or an underflow flushed a nonzero exact result to zero.

### 1.2 `fa` / `fs` / `fm` / `fma` / `fms` / `fnms` (KNOWN, ISA pp. 206–212)

All six produce a four-wide single-precision result, flush underflows to +0, and saturate overflows to ±Smax.

For `fma` (rt = ra×rb + rc), `fms` (rt = ra×rb − rc) and `fnms` (rt = rc − ra×rb) the **product is exact and is not itself limited in range**. Only the result of the following add or subtract is flushed or saturated. That is a single truncation of a fused product-plus-addend, not two IEEE roundings.

`fa`, `fs` and `fm` are the unfused add, subtract and multiply, each truncated once.

### 1.3 `frest`, `frsqest` and `fi` (KNOWN, ISA pp. 215–219)

`frest rt, ra` does not return a finished reciprocal. It returns a packed **base and step** in the same 32-bit word: sign, 8-bit biased exponent, a 13-bit base fraction, and a 10-bit step fraction. Interpreted as an ordinary float, that word is already a rough estimate of 1/x. The intended use is as the `rb` operand of `fi`. A zero-exponent input raises DBZ.

`frsqest` is the same idea for 1/√|x|. The sign bit of the estimate is forced to 0.

`fi rt, ra, rb` unpacks the base and step from `rb` and interpolates with Y = 0.ra[13:31] (the low 19 bits of `ra`, binary point to the left of bit 13):

    rt = (−1)^S × (1.BaseFraction − 0.000StepFraction × Y) × 2^(E−127)

If `rb` came from `frest`/`frsqest` of the value in `ra`, the ISA says `fi` produces a more accurate estimate.

Quality after the recommended sequences (ISA, not a measured figure of this port):

- Reciprocal: `frest` → `fi` → `fnms` (t = 1 − x·y) → `fma` (y + t·y). For normal inputs, the final y2 is within **1 ULP** of the IEEE-single reciprocal (either exact or one ULP smaller in magnitude). Special cases: 1/0 is defined to be Smax (`0x7FFFFFFF`); if |x| ≥ 2^126, 1/x underflows to 0 (one input where IEEE would still return a tiny normal).
- Reciprocal square root: `frsqest` → `and` to take |x| → `fi` → two `fm`s and an `fnms`/`fma` Newton step. For normal inputs, |Y − y2| ≤ 1 ULP. Zero-ish inputs go to Smax, with a documented corner for tiny fractions above `0x000ff53c`.

The ISA does **not** quote a "12-bit estimate" figure. The base itself has a 13-bit fraction; the accuracy that the ISA guarantees is the 1-ULP bound **after interpolation and one Newton step**.

Cloth overlay opcode counts from physics-cloth-1.md §1.3 (KNOWN): sec_cloth has `frest` 28, `frsqest` 27, `fi` 55 (exactly 28+27). sec_ponytail has `frest` 60, `frsqest` 44, `fi` 104. Every estimate is paired with exactly one `fi`. Any Newton step uses `fnms`/`fma`/`fm` (of which there are many) and does not need a second `fi`. **ASSUMED**: the cloth solver follows the ISA-recommended estimate → interpolate → one Newton pattern, or estimate → interpolate only.

### 1.4 `fcgt` / `fcmgt` (KNOWN, ISA pp. 233–234)

Both always run in extended-range mode (the ISA "mode bit" is ignored).

- `fcgt`: each word of `rt` is all-ones if `ra > rb`, else all-zeros. Two zeros never compare greater, regardless of sign and fraction.
- `fcmgt`: the same test on absolute values. Two zeros never compare greater, regardless of sign and fraction.

Because exponent 255 is a finite value, an "Inf-looking" encoding is simply a large finite and compares as one. There are no NaN-unordered cases in this format.

### 1.5 Conversions `csflt` / `cuflt` / `cflts` / `cfltu` (KNOWN, ISA pp. 220–223)

The immediate is an 8-bit field I8. The scale used by the operation is an 8-bit integer that must be in 0..127; otherwise the result is **undefined**.

| inst | meaning | scale |
|---|---|---|
| `csflt rt, ra, scale` | signed i32 in `ra`, to extended single, then ÷ 2^scale | scale = 155 − I8 |
| `cuflt rt, ra, scale` | unsigned u32 in `ra`, to extended single, then ÷ 2^scale | scale = 155 − I8 |
| `cflts rt, ra, scale` | extended single in `ra`, × 2^scale, truncate toward zero to signed i32 | scale = 173 − I8 |
| `cfltu rt, ra, scale` | same, to unsigned u32 | scale = 173 − I8 |

Saturation (KNOWN):
- `cflts` saturates to 2^31−1 above, and to −2^31 below.
- `cfltu` saturates to 2^32−1 above, and to 0 if the product is negative.

The scale is the position of the binary point from the right of the integer register: scale 0 means an unscaled integer. These four instructions do not set the single-precision exception flags (`cflts`/`cfltu` never; `csflt`/`cuflt` may set OVF/UNF/DIFF).

A port comment at P `spu_helpers.h:1306-1320` notes an implementation subtlety that should be **VERIFY**ed against the ISA and against hardware if a conversion-heavy path is ever blamed: `cflts`/`cfltu` of a zero-exponent input are described there as *not* flushing the significand the way arithmetic does. I have not independently re-derived that case from the ISA instruction pages, so I do not treat it as KNOWN here.

### 1.6 Double precision and the FPSCR (KNOWN, ISA §9.2 pp. 197–200 and §9.3)

Double precision is IEEE-754 binary64, two-way SIMD. Inf and NaN are defined. All four rounding modes are supported, independently per slice:

- FPSCR bits 20–21 = RN0 (slice 0), bits 22–23 = RN1 (slice 1)
- `00` nearest-even, `01` toward zero, `10` toward +∞, `11` toward −∞

IEEE exception flags (OVF, UNF, INX, INV, NaN, DENORM) are sticky; traps are not implemented. `fscrrd` / `fscrwr` read and write the register.

Single-precision arithmetic ignores these rounding fields (always toward zero). Cloth is a single-precision solver (the overlay counts in physics-cloth-1.md §1.3 are all single-precision opcodes). Double precision is documented here for completeness and is **ASSUMED** unused by the cloth image; **VERIFY** by grepping the disassembly for `d*` / `fesd` / `frds` if a later path needs it.

P `spu_helpers.h:615-616` states that the port's double path currently models only round-to-nearest and ignores `fscrwr`. That is a documented port limit, not an ISA rule.

### 1.7 What RPCS3 actually does by default (KNOWN)

Defaults in this commit, `system_config.h`:
- SPU decoder: LLVM (`system_config.h:27`).
- `spu_xfloat_accuracy`: **Approximate XFloat** (`system_config.h:66`).
- `Set DAZ and FTZ`: **false** (`system_config.h:26`). That switch is a host MXCSR debug/PPU option, not the SPU xfloat mode.

The enum (`system_config_types.h:386-392`; labels in `rpcs3qt/emu_settings.cpp:1523-1528`):

| setting | meaning (paraphrase) |
|---|---|
| Accurate XFloat | LLVM keeps suspected extended-range values in f64 so exponent 255 stays finite (`SPULLVMRecompiler.cpp`, many sites, e.g. FA at 8604–8616: `f64[4] + f64[4]`). This is the closest of the four modes to the ISA range. |
| Approximate XFloat (**default**) | LLVM uses host f32. Some Inf/NaN holes are patched (e.g. FM around 8670–8701). FA is a plain host add. FMA in the fast interpreter is a host multiply then a host add — two roundings, not a fused then-truncate (`SPUInterpreter.cpp:2092-2106`). |
| Relaxed XFloat | Approximate accuracy for only `fcgt`, `fnms`, `frest` and `frsqest` (enum comment, `system_config_types.h:390`). |
| Inaccurate XFloat | looser still. |

`frest`/`frsqest` in the default interpreter are a fraction LUT plus an exponent LUT (`SPUInterpreter.cpp:690-735`). P `spu_helpers.h:1667-1714` uses the same LUT method and comments that it matches RPCS3's measured tables. `fi` in the default interpreter is a host-float interpolation marked TODO (`SPUInterpreter.cpp:1523-1535`); the port's `spu_fi_ref` (`spu_helpers.h:1361-1393`) is an integer-exact evaluation of the ISA equation.

The interpreter also has a `spu_interpreter_precise::*` set (FREST at 2194, FRSQEST at 2219, FA/FM/FMA later). Physics-cloth-1.md §2 found no selection site in this commit and treated the default interpreter as the fast versions (ASSUMED). The default *decoder* is LLVM, not the interpreter, so a stock RPCS3 cloth run is LLVM + Approximate XFloat unless the user changed it.

**Reference we compare against:** a stock RPCS3 visual is Approximate XFloat + LLVM. An ISA-exact port can legally disagree with that reference in the last bits, and can even disagree with Accurate XFloat in any case the ISA leaves implementation-defined (ISA p. 195, implementation note). The way to bound "float noise" is to measure the RPCS3-accurate vs RPCS3-approximate spread on the same captured job (section 2). The port being stricter than the default reference is already noted in physics-cloth-1.md §2 and I agree.

### 1.8 How an x86 SSE/AVX recompiler or interpreter should emulate this

Recommendations, not a patch. Prefer the integer exact packers already in P `spu_helpers.h` when the goal is ISA-exact. If a fast SSE path is used:

| ISA rule | x86 habit that breaks it | What to do |
|---|---|---|
| Flush denormal inputs and outputs to zero; +0 only | Default MXCSR keeps denormals; SSE may produce −0 | Set DAZ and FTZ on the SPU thread. Force a zero result to +0 (AND off the sign, or max with +0 in the flush path). |
| Round toward zero | Default MXCSR is nearest-even | Set the MXCSR rounding field to toward-zero for SPU single-precision code. (Do not leave this on for PPU IEEE or for SPU double, which has its own FPSCR mode.) |
| Exponent 255 is finite Smax, no Inf/NaN | Host add/mul of large values produces Inf/NaN, which then poison later ops | After each op, if the host exponent is 255, rewrite the word to Smax with the intended sign (or do the pack in integers). Never let an x86 NaN survive in an SPU register. |
| `fma`/`fms`/`fnms` fuse then truncate once | `_mm_add_ps(_mm_mul_ps(...), ...)` rounds twice, which is what RPCS3's fast interpreter does | For ISA-exact: integer fused product-plus-addend, then one truncation. For "match default RPCS3": two host roundings are actually closer to Approximate XFloat. Pick the target explicitly. |
| `frest`/`frsqest` + `fi` | `_mm_rcp_ps` / `_mm_rsqrt_ps` are a *different* 12-ish-bit table, and they are not in the base-and-step format `fi` expects | Use the LUT (or an ISA-accurate equivalent) and implement `fi` as the packed-base/step interpolation. Do not feed `rcpps` output to `fi`. |
| `cflts`/`cfltu` truncate and saturate | `_mm_cvtps_epi32` saturates to i32 min/max only in some paths; unsigned needs a manual path; scale is 2^(173−I8) | Scale first (the scale is an exact power of two in 0..127), convert toward zero, then saturate to the ISA bounds. |
| `fcgt`/`fcmgt` | `_mm_cmpgt_ps` is IEEE-ordered and treats Inf/NaN differently | Flush denormal inputs to zero, treat exponent-255 words as finite, and keep +0/−0 from comparing greater. |

### 1.9 Which divergences matter for *this* cloth (ASSUMED, ranked against the pictures)

Physics-cloth-1.md §3 and §4 already ranked float math as H5 (low). I agree, for these reasons:

- The pictures show free particles that never move, and a strip or sheet locked to one stable far point. There is no jitter and no NaN-like explosion. A last-bit rounding miss, or even a consistent 1-ULP Newton bias, produces a slightly different drape, not a frozen pose. (KNOWN symptoms; ASSUMED causal ranking.)
- The port's helpers are ISA-exact; stock RPCS3 is Approximate XFloat and still draws Zhao Yun's back cloth correctly (physics-cloth-1.md §2, gfx-advisor H1a). So "we are not IEEE-exact" does not by itself explain the stretch.
- Overlay counts show a full `frest`/`frsqest`+`fi` pairing, so a missing-`fi` bug is unlikely unless the interpreter never reaches that code (which is H1, not H5).

Divergences that *would* be able to spoil a cloth solve, if the job is actually running, and that a parity replay should still watch for:

1. **1/0 and 1/√0.** The ISA returns Smax. Host IEEE returns Inf or NaN. A zero-length constraint (two coincident particles, or a fully slack edge at rest length 0) then either explodes or is silently skipped, depending on the later `fcgt`/`fcmgt` tests. Symptom would usually be a spike or a disappearing edge, not a frozen initial pose — unless the very first step hits this and writes garbage that then stays. **VERIFY** on a captured job if any rest length is 0.
2. **Two-rounding FMA vs fused-then-truncate**, accumulated over many constraint iterations. This is the RPCS3-default vs ISA-exact gap. Expect a small, slowly growing position error, inside the float-noise band of section 2 after calibration. If the replay error is already huge on frame 0, this is not the cause.
3. **Host nearest-even vs toward-zero.** Same class as (2): last bits, not a frozen sheet.
4. **Denormals.** The overlays contain a ~1e-6 epsilon (physics-cloth-1.md §1.3). Smin is ~1e-38, so ordinary residual tests will not enter the denormal range. Only a long underflow chain would care. Low priority for this title.

---

## 2. Offline-replay parity metric

### 2.1 Why a live side-by-side is not a parity test (KNOWN)

Physics-cloth-1.md §6 already rejected watching the same vertex buffer live in both programs over N frames: the RPCS3 GDB stub is PPU-only (`GDB.cpp:582`), and the two runs do not share animation phase, frame timing, or dt. I agree. The comparison has to be **the same input snapshot, one job (or one recorded frame) at a time**.

### 2.2 Method (proposed; the capture itself is VERIFY)

1. **Capture in RPCS3** (Interpreter or LLVM; record the `spu_xfloat_accuracy` setting used). On the PPU side, break at the import stub for `cellSpursLFQueuePushBody` (NID `0x8A85674D`) once in-stage. Record: the pushed item, the 48-byte header and 16-byte block identified in physics-cloth-1.md §1.2, and every input EA the job will GET (from a D2 DMA log on the port, or from an MFC trace on RPCS3). Break again at the next PushBody of the same queue, and record the PUT ranges. Sync on the job item contents, not on a frame number.
2. **Replay once in RPCS3 Accurate XFloat and once in Approximate XFloat** on that exact snapshot. The difference is the **calibration spread**: it is the float-semantics noise of the reference itself. **VERIFY**: this pair of replays has not been run yet. Do not treat the script's default bands as that spread.
3. **Replay the same snapshot in the port's interpreter** (box or a test copy; nothing on Saud's PC from this note). Diff the PUT vertex positions against the RPCS3 dump of the same setting you chose as the visual reference (Approximate, unless you are specifically checking ISA-exactness against Accurate).
4. **Score with the script below.** Repeat for a short sequence of captured jobs to see whether the error stays flat, drifts, or blows up.

A leftover live check, once replay is clean: D1 counters, D5 (the draw reads the buffer that was PUT), and a side-by-side visual. Those do not replace the replay.

### 2.3 Metrics (KNOWN definitions; thresholds ASSUMED until calibrated)

Per component, and per vertex, for each step/frame:

- **Bitwise ULP distance** of each f32 component, using the usual total order on binary32 bit patterns (+0 and −0 are 0 ULP apart). A NaN or IEEE Inf in either dump is recorded separately: those encodings are not SPU singles, so their presence is already a logic / emulation bug, not "a few ULP".
- **Max and RMS ULP** over all components of all vertices.
- **Max and RMS Euclidean position error**, then **normalised by the reference cloth bounding-box diagonal** (axis-aligned, from the reference vertices of that same frame). If the reference box is degenerate, the script falls back to the test box, then to 1, and sets `degenerate_bbox`.
- **First-divergence frame/step index**: the first index where any component differs at all, and (optionally) the first index that exceeds a stated tolerance.
- **Error growth**: the median ratio of consecutive frames' max normalised position error. A stable integrator stays near 1 (or grows slowly). A chaotic one roughly doubles or worse each step, once the error is out of the noise band.

Thresholds. Physics-cloth-1.md §6 said not to pick a number in advance, and I agree as a *verdict* rule. The script ships **illustrative uncalibrated bands** so it can classify its self-tests; they are tagged `calibrated=False` until replaced by the measured Accurate-vs-Approximate spread:

| band | uncalibrated default | role |
|---|---|---|
| noise, max pos / bbox diagonal | 1e-4 | "float-semantics noise" if the series stays at or under this and does not grow explosively |
| noise, RMS pos / bbox | 1e-5 | reported; not the primary cut |
| logic-bug, max pos / bbox | 5e-2 | a five-percent-of-the-scarf miss is not a rounding mode |
| growth, stable / chaotic | median ratio 1.25 / 2.0 | chaotic growth plus a noise-band miss → logic-bug |

Primary classifier is the **normalised position error**, not raw ULP. A 10^−6 miss at the origin is millions of ULPs (because ULP shrinks toward zero) and is still tiny against a one-metre scarf. ULP remains the right tool for "when did the first bit flip" and for mid-range values.

A frozen test pose against a moving reference, or a NaN/Inf, is classified as a logic bug even before the 5 % band is used. That is the pattern the scarf pictures suggest (physics-cloth-1.md §3).

### 2.4 Script

`/workspace/sf-shared/math-physics-joint/parity_metric.py`

- stdlib only (`json`, `struct`, `math`, `argparse`).
- `python3 parity_metric.py` runs the self-tests (30 checks passed on this box).
- `python3 parity_metric.py --ref ref.json --test test.json` scores a dump pair.
- `--calibrated-bands bands.json` plus the Accurate-vs-Approximate measurement is what turns the bucket into a verdict.
- `--demo` prints a two-frame worked example.

JSON shape: `{ "components": 3, "frames": [ { "frame": 0, "positions": [[x,y,z], ...] }, ... ] }`.

---

## 3. Shortcuts for lifting overlapping SPU overlays

### 3.1 What is already KNOWN about img 9000

From physics-cloth-1.md §1.1–1.2 (ELF headers, libovis table, disassembly):

- `sec_cloth` and `sec_ponytail` both load at **LS 0x3080**. They cannot be one flat compiled image: the same addresses hold two different instruction streams.
- Game DMA sizes (libovis entries) are 0x7600 and 0xB100, which are the ELF filesizes rounded up. Destination is always 0x3080. Sources are `table_EA + paddr − 0x40000` (paddr 0x40000 and 0x47600).
- Resident `.text` is 0xE180–0x16FF0, entry 0xE190, and does **not** overlap the overlay window. Overlays call back into resident helpers (0xEF68, 0x10918, 0x11A88, 0x16060).
- The libovis loader (0x15B58–0x15E0C) skips the load if the resident flag is set, otherwise issues plain GETs of at most 0x4000 bytes, then the unload (0x15B20) clears the flag. **Every job re-DMAs its overlay from the PPU-side table.**
- img 9000 currently runs interpreted because the two overlays overlap, which is why a lift shortcut is worth having. That is a performance / maintainability path, not the first explanation of the frozen scarf (H1 still leads).

### 3.2 Three lift strategies (methods; none is implemented here)

**A. Two compiled images, keyed by which overlay is resident. (ASSUMED workable; VERIFY by a harness.)**

Recompile `sec_cloth` as image 9000-A and `sec_ponytail` as 9000-B, each linked against the *same* lifted resident `.text` (and `.init`). A small overlay manager, or a hook on MFC GET completion, looks at the transfer that just landed at LS 0x3080:

- source offset 0 / paddr 0x40000 / size 0x7600 → dispatch into 9000-A once the tag completes.
- source offset 0x7600 / paddr 0x47600 / size 0xB100 → dispatch into 9000-B.

The switch happens only after the last 0x4000 chunk of that overlay has completed (the loader splits large GETs). Mid-transfer, the window is incomplete; do not dispatch into a compiled body then. The resident `.text` never needs to be swapped.

**B. Hash the resident LS range and jump to a precompiled block. (ASSUMED.)**

After each overlay GET-and-wait, hash LS 0x3080..0x3080+N (N = 0x7600 or the bytes actually written; do not hash past the shorter overlay into whatever stale ponytail bytes remain). Dispatch on the hash to the matching compiled block. Unknown hash → interpreter fallback, and log it.

This also catches a corrupted or partially written table (H2/D3) instead of silently running the wrong body. Cost is one hash per job, which is cheap next to the solve.

**C. Interpreter only for the overlapping window; keep resident `.text` lifted. (ASSUMED the smallest change.)**

Leave 0x3080–0xE17F interpreted. Rejoin lifted code when the PC enters 0xE180–0x16FF0. This is the opposite of today's risk in H1b (a *positive* image id rejoining a lifted function and ending the task). It only works if the rejoin is a call/return into resident helpers, not a "task finished" event, and if overlay→resident calls use the same register convention as the lifted helpers. **VERIFY** against `spu_interp.c` rejoin policy before anyone treats this as safe. Physics-cloth-1.md's "run MISS images as a negative interpreter id" is the prerequisite, not a substitute.

### 3.3 What I would actually try, in order

1. Fix the task contract (H1) so the interpreted job actually runs to completion every frame. A lift of a task that never leaves WAIT_SIGNAL will still look frozen.
2. Then C, as a low-risk speed-up of the resident loops, only after the negative-id interpreter change is in and confirmed.
3. Then A (explicit image A/B on DMA source), which is faster and easier to reason about than a hash, with B as a sanity check on the bytes that landed.

No change on Saud's PC is proposed from this section. These are methods for Salem to consider after H1 is settled, one change per build.

---

## 4. View on H1c (WAIT_SIGNAL / waiter-id mismatch)

### 4.1 What I think is already shown

I agree that **the cloth task is parked, and that a missed wake is the right family of causes**. I would not yet say the miss is specifically "the waiter id is the wrong width or the wrong endianness", because two other, equally concrete, defects in the same path can produce the same park.

Facts:

- **KNOWN (logs).** `SPU_INTERP_MISS` fires once for img=9000, entry 0xE190, in fix1650, the 19:33:14 sfauto run, and `putinputs1760` (`cloth-step1-logs.txt`). There is no later `interpreted task img=9000 ... stopped` line, and no `CROSS-IMAGE` / `unimplemented op` / `REJECTED img=9000` line. The interpreter run did not log an end.
- **KNOWN (logs).** Freeze tails already show the park site, not just a missing stop line: `[spu_workload] task 0 (taskset 0x14C02A80) sleeping 1s in WAIT_SIGNAL` (`freeze-1555/stderr_tail_155051-b9c979.txt:80`, also `saud_live/stderr_tail.txt:357` and `gI/ev/stderr_137700_137960.txt:254`). So "parked in WAIT_SIGNAL" for task 0 of 0x14C02A80 is observed, not only inferred from the pop code.
- **KNOWN (disassembly, physics-cloth-1.md §1.2).** The pop at 0x14BF0 issues WAIT_SIGNAL (`il r3,2` at 0x15030 and 0x151E8) when the queue is empty. The port's WAIT_SIGNAL handler reads the taskset EA from LS 0x27BC and the task id from LS 0x27D4 (context +0xD4), both big-endian (`P spu_channels.c:2387-2459`).
- **KNOWN (R `cellSync.h:293-361`).** The queue is 128 bytes, 128-aligned. `pop1.m_h1` at +0, `push1.m_h5` at +8, both BE u16; depth at +0x14, BE u32. `push2.pack` at +0x30 (BE u16, head in bits 10–14, tail in bits 0–4), `m_hs1[15]` at +0x32 (BE u16 waiter ids), `m_eaSignal` at +0x70 as a 64-bit BE pointer. Size is h5−h1, or h5−h1+2·depth when it wraps (R `cellSync.cpp:1527-1563`).
- **KNOWN (R `cellSync.cpp:1074-1091`).** On a completed push, if the waiter ring is not empty, RPCS3 reads `m_hs1[head]` and calls `fpSendSignal(ppu, eaSignal, that_id)`.
- **KNOWN (S `strikeforce_lfqueue.inc`).** The port override does the same ring walk, with `r16`/`w16` already byte-swapped to host (inc:107-109, wake around 105–125). It then calls `spu_taskset_signal_task(sig_ts, sig_task)` only when `sig_ts != 0` and `sig_task < 128`. `sig_ts` is `r32(q+0x74)`, i.e. the low half of the BE u64 at +0x70, which is the correct 32-bit EA if `m_eaSignal` was stored as a 64-bit pointer.
- **KNOWN (P `spu_workload.c:1405-1407`).** `spu_taskset_signal_task` returns immediately, with no log, if `taskset_ea == 0` or `taskId >= 128`. That is the ≥128 trap.
- **KNOWN (R `cellSpurs.cpp:4294-4299`; P `spu_workload.c:523`, `1376`).** Taskset bitsets use **task 0 = MSB** of the word: mask = `(1u << 31) >> (taskId % 32)`. A correct numeric id of 0 still wakes the wrong task if someone instead sets bit 0 (LSB).
- **KNOWN (logs, but capped).** Numbered `[sf-lfq] push#` stops at 24, all on `q=0x11095F80`. The "woke" lines stop at 16. Among those capped lines, **none** name the two queues created just before cloth ovis (`q=0x14C02900`, `q=0x14C02980`) or taskset `0x14C02A80`. Absence of a line after the cap is **not** evidence that those queues were never pushed. The cap itself is in S `strikeforce_lfqueue.inc` (push# `g_push_n++ < 24`, woke `sn++ < 16`).

### 4.2 Two other defects that look exactly like H1c

These are not alternatives to "the task is parked". They are alternative mechanisms for the missed wake, and they are already visible in the same logs.

**M1. The two cloth-adjacent queues were created with `dir=0` (KNOWN), and the port PushBody accepts only `dir=2` (KNOWN).**

`CELL_SYNC_QUEUE_SPU2SPU = 0`, `PPU2SPU = 2` (R `cellSync.h:285-291`). The log lines are:

- `[sf-lfq] init owner=0x00DB1301 q=0x14C02900 ... dir=0`
- `[sf-lfq] init owner=0x00DB1301 q=0x14C02980 ... dir=0`

S `strikeforce_lfqueue.inc` returns `E_PERM` (`0x80410909`) when `dir != 2` and does not write a slot. If the PPU really does call `cellSpursLFQueuePushBody` on those queues, the port silently refuses the job and the consumer, having popped empty, stays in WAIT_SIGNAL forever. If the producer is another SPU (dir=0 would then be honest), the PPU override is not on the path and the SPU complete-push / wake path has to be checked instead.

Whether `0x14C02900` / `0x14C02980` are in fact the cloth job queues is **ASSUMED** from timing (they are created immediately before the cloth ovis init) and from physics-cloth-1.md. **VERIFY** by matching r4.word0 (the LFQueue EA planted in the task) to those two addresses in a D0 dump.

**M2. `eaSignal` / owner is `0x00DB1301`, not the cloth taskset `0x14C02A80` (KNOWN owner value; ASSUMED that this is what the wake will signal).**

For the queues that *do* log a wake, the init `owner` equals the woken taskset (`0x14CE3880`, `0x14D4A900`, `0x14C7C800`). For the cloth-adjacent queues the owner is `0x00DB1301`, which sits in EBOOT space, not in the `0x14C0…` taskset range. The override stores that owner at `q+0x70` and later signals `r32(q+0x74)`. If that path is taken with `sig_task < 128`, the signal goes to whatever `0x00DB1301` is, not to taskset `0x14C02A80`. On hardware / RPCS3, `fpSendSignal(eaSignal, id)` is a callback; treating `eaSignal` as "the taskset EA" is only valid when the game passed a taskset.

`0x00DB1301` is also the owner of the later `0x1724…` queues, so it may be a shared send-signal function pointer. **VERIFY** by dumping `q+0x70..+0x77` of `0x14C02900` at push time and by checking whether `spu_taskset_signal_task` is ever called with `0x14C02A80`.

### 4.3 The concrete check that confirms or kills H1c itself

Do this read-only, on a test copy, no rebuild strictly required if the existing WAIT_SIGNAL and `[sf-lfq]` lines can be uncapped; a one-build diagnostic (physics D0 / V2) is cleaner.

For **one** park-and-wake of taskset `0x14C02A80` (or of whichever queue r4.word0 actually names), log raw bytes, then the interpreted integers, for all of:

1. **The token the waiter stored**
   - LS `0x27D4..0x27D7` (task id, BE) and LS `0x27BC..0x27BF` (taskset EA, BE), taken at the WAIT_SIGNAL entry.
   - The bytes the SPU pop wrote into the queue: `push2.pack` at `q+0x30` (2 bytes) and the `m_hs1[head]` slot at `q+0x32 + 2*idx` (2 bytes), before the push.
2. **The id the push side signals**
   - The same `m_hs1[idx]` bytes as read by the override (`r16`), the integer `sig_task`, `sig_ts = r32(q+0x74)`, and the 8 raw bytes at `q+0x70`.
   - Whether `spu_taskset_signal_task` was called, skipped because `sig_task >= 128`, skipped because `sig_ts == 0`, or skipped because `dir != 2` / `head == tail` / `pack == 0xFFFF`.
3. **The bit the taskset side actually sets**
   - Word `signalled[taskId/32]` before and after, and which bit was flipped. It must be the MSB-first mask for that numeric id (task 0 = bit 31 of word 0).

**H1c is confirmed** if any of these hold:

- the 2-byte `m_hs1` slot, read as BE, is not the same integer as LS `0x27D4` (byte-swapped, truncated, or a different id);
- that integer is ≥ 128, so `spu_taskset_signal_task` returns without a wake;
- the bit set in the taskset word is not the MSB-first bit for that id;
- `head == tail` at push even though a waiter is parked (the SPU did not publish a waiter, or packed the ring in a different layout / endianness).

**H1c-as-id-mismatch is killed** if the stored token, the BE `m_hs1` value, and the integer passed to `signal_task` are the same id < 128, the MSB-first bit is set, and the park still does not end. Then the miss is elsewhere: wrong `sig_ts` (M2), push refused on `dir` (M1), a push that never happens, or a wait on a different object than the one the push signals. Uncap the `[sf-lfq]` logs first so that conclusion is not an artefact of the 16/24 caps.

Either outcome is useful. I would run this before any further float or overlay work on cloth: a task that never leaves WAIT_SIGNAL will not be helped by a more accurate `fi`.

---

## 5. Split and next step

The split عالم الفيزياء proposed is fine with me: they own physics / SPU tasks (cloth image 9000, knockback, falls, hits, movement timing); I own the float semantics, the parity metric, and lift shortcuts.

Next, from my side, once Salem can take a read-only dump (no change on Saud's PC from this note):

1. The H1c confirm/kill log in §4.3, plus the dir=0 and `eaSignal` checks (M1, M2).
2. Only after the cloth job is actually completing: one captured job, RPCS3 Accurate vs Approximate vs the port, scored with `parity_metric.py` and with bands taken from that Accurate-vs-Approximate pair.

I am not asking for a lift of img 9000, and I am not asking for a float-helper change, until (1) says the task is running.
