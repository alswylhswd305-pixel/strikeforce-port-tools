# Math-side tool ideas (باحث الرياضيات) — 2026-11-27

Rules: box-only build, Python stdlib, no GPL/RPCS3 code, log-only on Saud's PC (Salem runs, Saud approves), labels KNOWN / ASSUMED / VERIFY.

## 1. ATRAC frame-grid validator (easiest, highest immediate value)
- What it catches: every byte offset fed to the ATRAC decoder that is NOT on a frame boundary, and the first bad feed + its delta from the nearest frame start (e.g. off by the header size, or a stride computed for 2ch used on 6ch).
- Math: feed is valid iff (offset - data_start) mod frame_bytes == 0 and length is a multiple of frame_bytes (except the stream tail). frame_bytes comes from the stream header (block align). Delta pattern tells the cause: constant delta = wrong data_start; growing delta = wrong frame size; delta = k*(frame_6ch - frame_2ch) = channel-count mixup.
- Input: a log of (stream id, read offset, length) per decode/AddStreamData call, plus header bytes of the BGM file (header only; derived numbers back).
- KNOWN: physics agent reports 6ch BGM is fed bytes that aren't frame starts. ASSUMED: header carries block align in a standard RIFF/OMA field. VERIFY: exact AT3+ header layout and whether frame_bytes is per-channel-set or whole frame (web-check before coding).
- Effort: small (~150 lines, 1 day incl. self-tests).

## 2. SPU halt back-slicer + invariant probe generator
- What it catches: for a halt/heqi pc (e.g. 0x31C20 divide-by-zero guard), walks the SPU disassembly backwards to find which register is tested, which load/DMA produced it, and the LS address / effective address it came from. Then emits a log-only probe list: (pc, register, LS addr) to dump right before the halt, plus a bound check (index < size, divisor != 0) at the producing instruction.
- Same machinery found the mixer page-index overflow by hand (counter at LS 0x13200, no wrap compare). This automates it: generic "address = base + idx*stride, is idx ever > N" checker for every DMA ea in the image.
- Math: backward def-use slice over straight-line blocks + loop bound inference (counter increments with no compare against a constant = flagged "unbounded index").
- KNOWN: mixer image 391227015 disassembly exists (/workspace/ringwatch_tmp/mix/dis.txt). ASSUMED: most halts are guarded by heqi/hgti on a value 1-3 loads away. VERIFY: slice correctness on the already-solved mixer index case before trusting it on 0x31C20.
- Effort: medium (~500 lines, 2-3 days). Test oracle = the solved mixer case.

## 3. Lifetime / address-reuse interval checker + tolerant first-divergence finder
- What it catches: (a) SPU tasks/tasksets whose create..destroy intervals overlap a NEW object created at the same address (address reuse while old stage tasks still alive); tasks that never get a stop/destroy at stage change. (b) First real divergence between our trace and an RPCS3 trace, ignoring timing noise.
- Math: (a) interval graph per address: sort events, flag any address with two live intervals at once, and any interval still open at a stage boundary. (b) align the two event streams by sequence alignment (edit distance on event kinds, timestamps ignored), report first mismatch after the longest common prefix; event-count spread from repeated RPCS3 runs sets the noise floor (ties into parity_metric calibration).
- KNOWN: open hang family = old stage SPU tasks never stopped + taskset address reuse. ASSUMED: create/destroy/stop are all visible in existing HLE logs. VERIFY: RPCS3 log gives equivalent events (log-only, no code copied).
- Effort: (a) small, 1 day; (b) medium, 2 days.

## Already built (my side)
- nid_autolink v2 (system functions): /workspace/sf-shared/nid-autolink/ — ranked missing/stub imports, 98 specs, 0xCD poison mode.
- parity_metric.py: /workspace/sf-shared/math-physics-joint/ — calibration vs RPCS3 run-to-run spread still pending.

Suggested order: 1 (ATRAC grid) -> 3a (reuse checker) -> 2 (back-slicer for 0x31C20).
