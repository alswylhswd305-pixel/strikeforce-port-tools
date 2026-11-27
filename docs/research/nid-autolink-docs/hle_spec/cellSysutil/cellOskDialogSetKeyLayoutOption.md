---
nid: 0xB53C54FA
lib: cellSysutil
name: cellOskDialogSetKeyLayoutOption
status_pc: stub (strikeforce_osk.inc:63 hle_ok); LR 0x0049FDA8
verdict: ok-setting-sink
signature: s32 cellOskDialogSetKeyLayoutOption(u32 option /*r3*/)
outputs: 
poison_ret: yes
confidence: KNOWN (prototype, codes) / ASSUMED (validation rules)
owner_overlap: 
researched: 2026-11-27
---
# cellOskDialogSetKeyLayoutOption  (NID 0xB53C54FA, cellSysutil)

**Verdict: ok-setting-sink** (+ documented validation + log). Returning CELL_OK for valid input is
what hardware does. What is missing is the documented PARAM check and a log line.

## Prototype
`s32 cellOskDialogSetKeyLayoutOption(u32 option /*r3*/)`

## Hardware behaviour (ASSUMED: paraphrase of [rp_osk]; prototypes and enums from [psl1ght])
- Bit flags: 1 = 10KEY panel, 2 = FULLKEY panel. 0 or > 3 → PARAM. Otherwise it stores the flags and returns OK.

## Return codes (KNOWN: [pdw_err] and [rp_osk] agree)
`0x8002B501` IME_ALREADY_IN_USE, `0x8002B502` GET_SIZE_ERROR, `0x8002B503` UNKNOWN, `0x8002B504` **PARAM**.
**Port bug (KNOWN):** ps3recomp `cellOskDialog.h` and Saud's `strikeforce_osk.inc` use
`0x8002B30x`, which is the **MSGDIALOG** range (0x8002B301 = CELL_MSGDIALOG_ERROR_PARAM per
[pdw_err]). Any OSK error the game tests against will not match. Fix those constants in a separate,
approved build.

## Context
Strikeforce's name-entry dialog is answered automatically by `strikeforce_osk.inc` (SF_OSK_TEXT,
default "Saud"; it queues LOADED 0x0502 + FINISHED 0x0503). These Set*/Ext* calls are made just
before LoadAsync (LRs 0x0049FD9C..0x0049FDCC, KNOWN from [pc_report]) and configure how the real
system keyboard would look. No getter API exists, so the game cannot read the values back
(KNOWN: no Get* for them in [psl1ght] or [rp_osk]). The port's auto-answer has no visible keyboard,
so storing the values is complete behaviour.


## Minimal correct offline PC behaviour
Validate exactly as above (otherwise return 0x8002B504), store the value in the OSK state struct,
log once, and return 0. Nothing visual is needed while the name dialog is auto-answered.

## Error-path analysis
No offline or PC situation makes this fail on hardware. Only invalid arguments do. An error return
for valid input would be WRONG.

## Poison test (SF_POISON=cellOskDialogSetKeyLayoutOption)
r3 = 0xCDCDCDCD. If the name dialog still completes, the game ignores the return (expected). If it
skips or retries LoadAsync, the game checks the return. Record which.

## Acceptance test (in-game)
1. New game → name entry: the log shows this call with its argument value and `-> 0`.
2. LoadAsync → LOADED → FINISHED events arrive, and the name (SF_OSK_TEXT) appears in the save/HUD.
3. There is no UNRESOLVED line for this NID, and the call count matches one per dialog open.

## Sources
- [pdw_nid] psdevwiki NID page + ps3recomp nid_database.py: NID = first 4 bytes (LE) of SHA-1(name + suffix)
- [pdw_err] psdevwiki, Template:CELL_ERROR_FACILITY_SYSTEM_UTILITY_-_0x002 (error-code tables; fetched 2026-11-27)
- [psl1ght] PSL1GHT ppu/include/sysutil/osk.h (MIT): prototypes, enums, struct layouts
- [rp_osk] RPCS3 cellOskDialog.cpp/.h (GPL-2, behaviour only, nothing copied)
- [p3r_osk] ps3recomp libs/misc/cellOskDialog.h + osk_native.c (MIT)
- [sf_osk] port strikeforce_osk.inc (Saud's override: auto-answers the name dialog)
- [pc_report] pc-results/report.csv (Salem's read-only PC run, 2026-11-27)
