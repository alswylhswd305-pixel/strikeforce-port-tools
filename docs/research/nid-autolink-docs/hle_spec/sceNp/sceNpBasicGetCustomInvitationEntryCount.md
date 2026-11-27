---
nid: 0xA8AFA7D4
lib: sceNp
name: sceNpBasicGetCustomInvitationEntryCount
status_pc: missing (unresolved -> fake CELL_OK, *count NOT written); hit 2x per boot in 48/50 runs, lr 0x00037920
verdict: needs-real-impl
signature: s32 sceNpBasicGetCustomInvitationEntryCount(u32* count /*r3*/)
outputs: r3:4
poison_ret: no
confidence: KNOWN (NID, error codes, call evidence) / ASSUMED (exact hardware checks)
owner_overlap: 
researched: 2026-11-27
---
# sceNpBasicGetCustomInvitationEntryCount  (NID 0xA8AFA7D4, sceNp)

**Verdict: needs-real-impl (tiny): it must WRITE the output.** Today the unresolved path returns 0
(success) and leaves `*count` untouched, so the game reads whatever was on its stack as the number
of custom invitations. Offline the right answer is a count of 0 (or a documented "not signed in"
error). Either way the output must be defined.

## Prototype (KNOWN: NID 0xA8AFA7D4 = SHA-1 of the name; one pointer arg per [rp_np])
`s32 sceNpBasicGetCustomInvitationEntryCount(u32* count)`. r3 = guest pointer to a be u32.

## Return codes (KNOWN values: [pdw_err])
`0x8002A662` SCE_NP_BASIC_ERROR_NOT_INITIALIZED, `0x8002A665` INVALID_ARGUMENT,
`0x8002A66D` NOT_REGISTERED, `0x8002AA06` SCE_NP_ERROR_ID_NOT_FOUND.

## Hardware behaviour (ASSUMED: [rp_np] marks the function "todo", so this is not hardware-verified)
Checks in order: NP not initialised → NOT_INITIALIZED; no basic handler registered →
NOT_REGISTERED; count NULL → INVALID_ARGUMENT; not signed in → SCE_NP_ERROR_ID_NOT_FOUND.
Otherwise it writes *count (0 when there are none) and returns OK.

## What the game does with the result
KNOWN: it is called twice per boot from lr 0x00037920 ([runs]). VERIFY the branch with
`--mode callgraph`: does the code at 0x0003791C test r3 before loading *count? If it tests r3 < 0
first, the NOT-signed-in error is safe. If it loads *count without testing, ONLY "write 0 + OK"
is safe.

## Minimal correct single-player offline PC behaviour
The port reports the NP manager as OFFLINE (sceNp.c sceNpManagerGetStatus). Recommended
(safest whichever way the game branches): **if count≠0, write be32 0 to *count**, then return
`0x8002AA06` when the call graph shows r3 is tested, else return 0. Until the call graph is in,
**write 0 and return 0**. That is never worse than today and removes the uninitialised read.
Log the first call.

## Error-path analysis
"Offline / not signed in" IS the real situation for this port, so the documented ID_NOT_FOUND is
acceptable only if the game handles it (VERIFY). Count = 0 is consistent with hardware in every case.

## Poison test (SF_POISON=sceNpBasicGetCustomInvitationEntryCount)
Fills *count with 0xCDCDCDCD and returns 0. If the game then shows an invitation UI, hangs, or
loops at lr 0x37920, it READS *count, which proves the fake is a live bug.

## Acceptance test (in-game)
1. Boot log: two calls, `count<-0`, and no `[hle] UNRESOLVED NID 0xA8AFA7D4`.
2. Title → main menu → village with no invitation/NP popup.
3. The poison run differs from the fixed run (or not: report which).

## Sources
- [pdw_nid] psdevwiki NID page + ps3recomp nid_database.py: NID = first 4 bytes (LE) of SHA-1(name + suffix)
- [pdw_err] psdevwiki, Template:CELL_ERROR_FACILITY_SYSTEM_UTILITY_-_0x002 (error-code tables; fetched 2026-11-27)
- [rp_np] RPCS3 sceNp.cpp/.h (GPL-2, behaviour only; function marked 'todo' there = not hardware-verified)
- [runs] 48/50 boot runs: unresolved-NID first-hit dumps (progress-src/runs, findings.json)
- [pc_report] pc-results/report.csv (Salem's read-only PC run, 2026-11-27)
