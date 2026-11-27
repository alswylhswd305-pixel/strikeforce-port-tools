---
nid: 0x53E39DF3
lib: cellSysutil
name: cellOskDialogSetSeparateWindowOption
status_pc: stub (ppu_hle_nids.cpp:1758)
verdict: ok-setting-sink
signature: s32 cellOskDialogSetSeparateWindowOption(CellOskDialogSeparateWindowOption* opt /*r3*/)
outputs: 
poison_ret: yes
confidence: KNOWN (prototype, codes) / ASSUMED (validation rules)
owner_overlap: 
researched: 2026-11-27
---
# cellOskDialogSetSeparateWindowOption  (NID 0x53E39DF3, cellSysutil)

**Verdict: ok-setting-sink** (+ documented validation + log). Returning CELL_OK for valid input is
what hardware does. What is missing is the documented PARAM check and a log line.

## Prototype
`s32 cellOskDialogSetSeparateWindowOption(CellOskDialogSeparateWindowOption* opt /*r3*/)`

## Big-endian layout (KNOWN: [psl1ght], 28 bytes)
| off | type | field |
|---:|---|---|
| 0x00 | be u32 | continuousMode (0 NONE, 1 REMAIN_OPEN, 2 HIDE, 3 SHOW) |
| 0x04 | be s32 | deviceMask (0 or 0xFF = pad) |
| 0x08 | be s32 | inputFieldWindowWidth |
| 0x0C | be f32 | inputFieldBackgroundTrans |
| 0x10 | be u32 ptr | inputFieldLayoutInfo → {be s32 layoutMode; be f32 x; be f32 y} (required) |
| 0x14 | be u32 ptr | inputPanelLayoutInfo (optional) |
| 0x18 | be u32 | reserved (must be 0) |

## Hardware behaviour (ASSUMED: paraphrase of [rp_osk]; prototypes and enums from [psl1ght])
- PARAM if: opt NULL, inputFieldLayoutInfo NULL, reserved ≠ 0, continuousMode > 3, or deviceMask > 0xFF.
- Otherwise: separate-window mode on; stores mode, mask, width, transparency (clamped 0..1), and the field layout. The panel layout is optional (NULL keeps the default). Returns OK.

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

## Poison test (SF_POISON=cellOskDialogSetSeparateWindowOption)
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
