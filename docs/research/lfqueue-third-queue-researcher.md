# Strikeforce: the third LFQueue (0x14D89700) is never pushed. Research notes (2026-11-26, 08:5x UTC+3)

Pins:
- **P** = ps3recomp `e85647a33ce5f9391788f0e3f52ab395a7fe6a89` → https://github.com/sp00nznet/ps3recomp/blob/e85647a33ce5f9391788f0e3f52ab395a7fe6a89/
- **R** = RPCS3 `0ca5eb0efe50ec4e8aa07892ab86d57842246eb4` → https://github.com/RPCS3/rpcs3/blob/0ca5eb0efe50ec4e8aa07892ab86d57842246eb4/

Source tags used below:
- **[SRC]** = upstream source I read.
- **[WB]** = Saud's 2026-11-01 PS3AIWorkbench files in `/workspace/sf-shared/event-queue-files/`.
- **[LOG]** = Salem's `loading_hang_chblock.txt`.
- **[REPO]** = `/workspace/strikeforce-recomp-repo/port/strikeforce_lfqueue.inc`. This is the older override; the push-wake version on Saud's PC was not available to me.

## 1. The CellSyncLFQueue / CellSpursLFQueue contract

KNOWN [SRC]: `CellSpursLFQueue` is `CellSyncLFQueue` (R `rpcs3/Emu/Cell/Modules/cellSpurs.h#L947`). The layout is R `cellSync.h#L293-L361`; 128 B, BE:

| off | field | meaning (from R cellSync.cpp) |
|---|---|---|
| 0x00 | pop1.m_h1 | pop **completed** index. The pusher's "free slots" test reads it |
| 0x02 | pop1.m_h2 | pop completion bitmap |
| 0x04 | pop1.m_h3 | pop-side waiter flag (3 = blocked consumer using the lv2 event queue) |
| 0x06 | pop1.m_h4 | pop **reserved** index |
| 0x08 | push1.m_h5 | push **completed** index. The consumer's "not empty" test reads it |
| 0x0A | push1.m_h6 | push completion bitmap |
| 0x0C | push1.m_h7 | push-side waiter flag (3 = blocked producer) |
| 0x0E | push1.m_h8 | push **reserved** index |
| 0x10 / 0x14 | m_size / m_depth | |
| 0x18 | m_buffer | u64, bit0 = ANY2ANY |
| 0x20 | m_bs[4] | init writes -1 |
| 0x24 | m_direction | 0 = SPU2SPU, 1 = SPU2PPU, 2 = PPU2SPU, 3 = ANY2ANY |
| 0x28 | m_v1 | |
| 0x2C | init | |
| 0x30 | push2.pack | 3 × 5-bit fields: ring of **consumers to signal when a push completes** |
| 0x32 | m_hs1[15] | waiter tokens for that ring |
| 0x50 | pop2.pack | ring of **producers to signal when a pop completes** |
| 0x52 | m_hs2[15] | waiter tokens for that ring |
| 0x70 | m_eaSignal | u64; for SPURS = taskset/spurs EA (R `cellSpurs.cpp#L3846`) |
| 0x78 | m_v2 | |
| 0x7C | m_eq_id | lv2 event queue, set by Attach |

**Rules** [SRC] (R `rpcs3/Emu/Cell/Modules/cellSync.cpp`):
- Init (`#L727-L765`): pop1 = {0,0,h3,0}, push1 = {0,0,h7,0}, m_bs = -1, m_v1 = 0, push2 = pop2 = 0, hs1 = hs2 = 0, eq_id = 0.
- GetPushPointer (`#L876-L965`): full ⇔ `(h8 − h1) mod 2d ≥ d`. Reserve = h8++. If blocking with useEventQueue: set h7 = 3, then `sys_event_queue_receive(m_eq_id)`.
- CompletePushPointer (`#L975-L1106`): advances h5/h6. If the push2 ring is non-empty and `var2+var4 ≤ 15`, it calls `fpSendSignal(m_eaSignal, m_hs1[head])` and advances the head (`pack>>10`).
- PushBody (`#L1116-L1173`) loops on AGAIN when blocking, then memcpy into `buffer + size*(pos mod d)`, then CompletePush.
- GetPopPointer (`#L1175-L1264`): empty ⇔ `(h5 − h4) mod 2d == 0`. Reserve = h4++.
- CompletePopPointer (`#L1274-L1406`): advances h1/h2. If the pop2 ring is non-empty, it signals `m_hs2[head]`.

**What a consumer must write back so the producer can continue** (KNOWN [SRC]):
1. **h1** (pop completed). The producer's full test uses h1, not h4.
2. If a producer registered in pop2/m_hs2, the signal to it.

For a **PPU** producer that blocks, the wake goes through `m_eq_id`. That requires `cellSpursLFQueueAttachLv2EventQueue`.

**RPCS3 is not an oracle for these entry points.**
- KNOWN [SRC]: RPCS3's HLE `_cellSpursLFQueuePushBody`, `PopBody`, `AttachLv2EventQueue` and `GetTasksetAddress` are `todo`/UNIMPLEMENTED (R `cellSpurs.cpp#L3849-L3878`).
- RPCS3 runs libsre **LLE** by default (R `rpcs3/Emu/Cell/lv2/sys_prx.cpp#L115`). So in RPCS3, the real `libsre` does the push.
- `cellSync.cpp` is the best public statement of the line protocol.

## 2. What ps3recomp master does

All KNOWN [SRC]:
- **`_cellSpursLFQueueInitialize`** (P `libs/spurs/cellSpurs.c#L4123-L4189`) writes **depth at +0x0C** (`#L4168`). That is push1.m_h7/m_h8: it makes **h8 = depth**, so a fresh queue looks **full** to an RPCS3-style producer.
  - It does not write m_bs = -1, direction or init.
  - It writes eaSignal = owner.
- **`cellSpursLFQueueAttachLv2EventQueue`** (`#L4191`) only logs and returns OK, so m_eq_id stays 0.
- **No `_cellSpursLFQueuePushBody` (NID 0x8A85674D) and no `_cellSpursLFQueuePopBody` (0x35DAE22B)** in P (git grep). Unresolved calls fake CELL_OK.
- The HLE task dispatch path (`runtime/spu/spu_workload.c`) does not write the SPU kernel LS word 0x1DC (`wklCurrentId`, R `cellSpurs.h#L1210`). Only the policy-module path does (P `runtime/spu/spurs_policy.c#L355`, `#L740`).
  - So async-dispatched tasks likely see wid 0 there. ASSUMED from grep; HOW TO VERIFY: dump LS 0x1DC of tasks 7902-7904.

## 3. What Saud's Nov-1 Workbench work established [WB]

These are Saud's own conclusions. They were not re-run here.
- **Line protocol (KNOWN [WB], consistent with [SRC]).** "The actual SPU image reserves h4 against h5 and completes h1; the PPU reserves h8 against h1 and completes h5" (`run-004/evidence/managed/actual-queue-push/native-lfqueue-push.patch`, header comment).
  - Also: "+0x0C belongs to push1, NOT depth" (`actual-lfqueue/native-lfqueue.patch`, header).
- **The SPU waiter token comes from kernel LS 0x1DC.** `strict-native-wid0-only.patch` says "the real queue helper forms its waiter token from kernelLS1DC". It admitted only WID0 tasks and wrote LS 0x1DC = 0 explicitly.
  - Token 0 is a **valid** WID0/task0 token, not "empty" (`independent-lfqueue-push-final-review.json`, `contract.no_notification_proof`).
- **The game's push call site retries forever on a nonzero result.** "Actual PPU 51FC74 compares r3 with 0, then retries nonzero at 51FC54" (same review, `contract.callsite`).
  - That was the graphics queue (dir 2, size 16, depth 2048, buffer = q+0x80). ASSUMED the MOC push sites behave the same way.
- **The earlier push was deliberately narrow.** It required push2/pop2 packs == 0 and h5 == h8, refused blocking pushes, and sent no task signals (`native-lfqueue-push.patch`). Salem's new waiter-ring wake goes beyond that.
- **Event flag 0x00DBA900 belongs to taskset 0xDB8F80 / WID1** (image 391227015) and was attached to lv2 event queue 65, port 16, capacity 1 (`docs/Strikeforce_EventQueue_20261101/RESULT.json`, `eventqueue-actual-result.json`). That run's first semantic stop was WAIT_SIGNAL of image 391227015.

## 4. The repo override [REPO] (older version)

- Init: zeroes the line, then writes size, depth, buffer, m_bs = -1, direction, v1 and eaSignal = owner. It returns E_STAT if init ≠ 0 and ≠ 2.
- Push: holds a lock, checks `(h8 − h1) mod 2d ≥ d` → AGAIN, copies the payload, then sets **h8 = h5 = next**. It does not touch h6/h7 or push2/m_hs1 and does no wake. A blocking push sleep-spins inside the HLE.
- **Its push log is capped at 24 lines total** (`g_push_n++ < 24`) and the "full" log at 4.
  - If the newer version keeps similar caps, or logs only pushes that wake a waiter (the excerpt shows only `woke` lines), then **"q3 never pushed" may be a logging artefact**. VERIFY first.

## 5. Why the PPU never feeds queue 3: ranked (all ASSUMED until checked)

**Evidence that frames the question** [LOG]:
- Tasks 7902-7904 (image 454077064) are all parked at 0xA70 with r3 = 2 (WAIT_SIGNAL).
- q1 and q2 got 3 pushes and wakes each.
- Main thread tid 1 is **not in a syscall or HLE**: `cia=0x00000000`, while every other thread shows a 0x0080xxxx HLE stub.
  - lr = 0x0011A258 (func_0011A230+0x28), r4 = 0x14D22800, r29 = 3.
  - Watchdog chain: func_0011A230 ← func_000F89C8 ← func_000ECB18.
- tid 7 waits on EF 0x00DBA900 about 80 times a second, ~10.6 ms each. The waits **complete**, so that flag is being set.
- tids 15-20 are in `sys_lwcond_wait`.

**Hypotheses:**

**H1: the main thread is in a game-side retry loop.** The PPU spins in guest code, so it shows no HLE cia. Two variants:
- (a) It retries a call whose nonzero result it treats as "try again" (the [WB] pattern at 0x51FC54/74). Example: a push to q3 that returns AGAIN/STAT/PERM because q3's line looks full or invalid.
  - Possible causes: the upstream init wrote h8 = depth for q3 (if q3 was initialised by a path the override does not catch); q3 was initialised with init ≠ 0 so the override returned E_STAT; or direction ≠ 2.
- (b) It calls a NULL function pointer. ps3recomp returns quietly from `bctr` to 0, and the caller retries forever (P `runtime/ppu/ppu_loader.cpp#L2915-L3005`; on by default, `[null-call]` / `bctr to NULL` logs).
  - `cia=0` is consistent with this but does not prove it (ASSUMED; the watchdog may print 0 for "inside lifted code").

**H2: q3 is gated on results from tasks 1-2, and those never arrive.**
- The tasks wake, pop and re-park. But if they do not **complete the pop (h1)** or do not produce their output (DMA PUT of results, a completion counter in their arg block, an SPU-side event flag set or signal), the main thread's stage-3 setup waits on that result. Its r4 = 0x14D22800 is task 3's arg block.
- Specific risk: the consumer re-parks because the wake arrived but the line showed nothing new (h4 == h5 at its GETLLAR).
  - Example: the wake was sent **before** h5 was published, or `spu_coh_notify_write` did not break its reservation.
  - Then it waits again, never consumes, and h1 never moves.

**H3: wrong waiter-ring handling on wake.**
- In RPCS3, CompletePush signals **only the head entry** of push2/m_hs1 and advances the head field (`pack = (pack & 0x83ff) | ((head+1)<<10)`), wrapping at 0x1d (`cellSync.cpp#L1044-L1074`).
- If the wake does not advance the head, or signals by eaSignal/task 0 instead of decoding the token, then:
  - the ring stays non-empty, so `var2+var4 ≤ 15` can fail and later pushes take the wrong path;
  - or the wrong task (task 0 of the eaSignal taskset) is woken.
- The [WB] note says the token comes from LS 0x1DC (the wid) plus the task id. If ps3recomp leaves LS 0x1DC = 0, all three tokens look like WID0.

**H4: the event flag.** ASSUMED **unrelated** to q3:
- 0x00DBA900 belongs to the WID1 taskset 0xDB8F80 [WB], not the MOC tasksets.
- Its waits complete about 80 times a second [LOG].
- Check anyway that no MOC task does an SPU-side EventFlagSet on it.

**H5: the lwcond workers (tids 15-20).** These are probably a job pool idling. A cause only if the main thread is supposed to signal them after q3 work. Low priority.

## 6. Fastest checks (in order; each takes minutes)

1. **grep the existing log** for `[null-call]`, `bctr to NULL` and `tid=1` (H1b), and for `[sf-lfq] init`: are there **three** init lines, with q3's direction, depth and rc?
2. **Log every push** with no cap and no "woke-only" filter: `q, rc, h1, h4, h5, h8, push2.pack, pop2.pack`. Seeing AGAIN/STAT repeating for q3 → H1a. No q3 call at all → H1b, H2 or H5.
3. **Dump the three 128-B lines** at hang time (0x14CBB600, 0x14D22680, 0x14D89700). Use the full-dump `.writemem` or `PS3_DEBUG mem` if the port has it. Decode them with the table in §1:
   - q1/q2: is **h1 == h4 == h5 == 3**? If h1 < h5, the consumer did not complete → H2. If h4 < h5, it never reserved → wake/visibility (H2/H3).
   - push2.pack (0x30) head ≠ tail after the wakes → H3.
   - q3: h8 vs h1 vs depth, direction (0x24), init (0x2C), m_bs.
4. **Dump the three tasks' LS 0x1DC** and the m_hs1 tokens. Compare the decoded token to (wid, taskId) (H3).
5. **Read the lifted C around func_0011A230+0x20..0x28 and func_000F89C8+0x49C** in the port's `src/recomp`. Check whether it is `mtctr/bctrl` through a loaded pointer (H1b), a compare-and-retry around a call (H1a), or a poll of a word in 0x14D22800 (H2: then identify which task should write it).
6. **RPCS3 oracle** (Interpreter decoder, needed for breakpoints, R `rpcs3/Emu/Cell/PPUThread.cpp#L1253`):
   - Break on the game's `_cellSpursLFQueuePushBody` import stub (NID 0x8A85674D; address from `imports.json`). Log r3 (queue) and LR for every hit.
   - This gives the real order of pushes (does q3 follow right after q1/q2, or only after something else?) and the LR of the q3 push. Compare that LR with func_0011A230/F89C8.
   - Then dump the same three lines at the first q3 push (`rpcs3_objsnap.py dump`).

## 7. Suggested direction (sketch, VERIFY)

- Make Init RPCS3-exact for all directions, including m_bs = -1 and direction/init. Handle re-init when init == 2.
- Implement CompletePush exactly: h5/h6 bitmap, and the push2 head pop with a signal to the **decoded** `m_hs1[head]` token through `_cellSpursSendSignal(eaSignal-taskset, taskId)`.
- Make sure h5 is published (and the reservation line notified) **before** the wake.
- Give AttachLv2EventQueue a real lv2 queue in `m_eq_id`, so a blocking PPU push can actually sleep and be woken by a pop.
- Write LS 0x1DC = wid for async-dispatched tasks.
