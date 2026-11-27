# Salem — tool ideas for the Strikeforce port (2026-11-27 18:35 Kuwait)
All box-side, offline/log-only, no GPL / no RPCS3-derived code.

## My votes on the physicist's 4 candidates
- (4) Deterministic input replay — USE FIRST. It's the base for everything else; T-38 auto-tester is already building the pad driver/teleport route, so share it (one script = one repro, no presses in cutscenes).
- (1) First-divergence finder — USE. Highest payoff for hangs like gate/village; depends on (4). Start with HLE call sequence + stage-load markers only, add SPU DMA hashes second (cost is RPCS3-side logging).
- (2) Taskset/SPU lifecycle timeline — USE NOW for the village hang. Cheap: our stderr already has most create/dispatch lines; the new lifecycle log build fills the rest.
- (3) sfdiag CLI + shared schema — useful glue, lower priority; do it once (1)(2) exist so the schema matches real needs.

## My own top 3
1. **Stage-transition leak checker** (easy, ~1 day)
   At every stage unload/load: list tasksets/tasks/LFQueues/event flags still alive from the previous stage, reused addresses, queues holding CDCDCDCD. Flags the exact village-hang pattern (taskset 0x16FA2000 re-created while 361927206 still spins). Could be a mode of (2).
2. **Same-spot graphics diff vs RPCS3** (medium, ~2-3 days)
   Same replay point (from 4) → PrintWindow shot from port + RPCS3 shot → aligned image diff with red boxes, plus a dump of the port's per-draw state (polygon offset, depth func/bias, depth clear value, viewport/scissor). Catches shadow acne (polygon offset not applied on D3D12), the left-edge blue strip, black/missing textures.
3. **Audio stream validator** (easy-medium, ~1-2 days)
   From SF_ATRAC_LOG: check every fed ATRAC frame starts on a real frame header and matches the file bytes at that offset; flag seeks without flush and garbage frames; per-channel RMS vs RPCS3 recording. Catches the 'jee taan taan' BGM corruption and voice/music balance (T-31).

## Suggested order
(4) → (2)+leak checker → (1) → graphics diff → audio validator → (3) sfdiag wrapping all of them.
