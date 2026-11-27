---
nid: 0xC96E89E9
lib: cellSysutil
name: cellAudioOutSetCopyControl
status_pc: stub (cellAvconfExt.c:160 returns OK, no validation; registered ppu_hle_nids.cpp:1322)
verdict: ok-setting-sink
signature: s32 cellAudioOutSetCopyControl(u32 audioOut /*r3*/, u32 control /*r4*/)
outputs: 
poison_ret: yes
confidence: KNOWN (codes) / ASSUMED (validation rules)
owner_overlap: 
researched: 2026-11-27
---
# cellAudioOutSetCopyControl  (NID 0xC96E89E9, cellSysutil)

**Verdict: ok-setting-sink** (plus validation). It sets the copy-protection flag on the digital
audio output (SCMS: FREE 0, ONCE 1, NEVER 2). No API reads it back and a PC has no SCMS, so storing
it and returning OK is the correct, complete behaviour. Only the documented parameter checks are missing.

## Prototype (KNOWN: NID 0xC96E89E9 matches; [p3r_av] and [rp_ao] agree on args)
`s32 cellAudioOutSetCopyControl(u32 audioOut, u32 control)`

## Big-endian layout: CellAudioOutConfiguration, 16 bytes (KNOWN: [p3r_av] and [rp_ao] agree)
| off | type | field |
|---:|---|---|
| 0x0 | u8 | channel (2, 6 or 8) |
| 0x1 | u8 | encoder (0 = LPCM, 1 = AC3, 2 = DTS) |
| 0x2 | u8[10] | reserved |
| 0xC | be u32 | downMixer (0 NONE, 1 TYPE_A, 2 TYPE_B) |

audioOut: 0 = PRIMARY, 1 = SECONDARY.

## Return codes (KNOWN: [pdw_err] and [rp_ao] agree)
`0x8002B240` NOT_IMPLEMENTED, `0x8002B241` ILLEGAL_CONFIGURATION, `0x8002B242` ILLEGAL_PARAMETER,
`0x8002B243` PARAMETER_OUT_OF_RANGE, `0x8002B244` DEVICE_NOT_FOUND, `0x8002B245` UNSUPPORTED_AUDIO_OUT,
`0x8002B246` UNSUPPORTED_SOUND_MODE, `0x8002B247` CONDITION_BUSY.

## Hardware behaviour (ASSUMED: paraphrase of [rp_ao])
- control > 2 → ILLEGAL_PARAMETER.
- audioOut SECONDARY → UNSUPPORTED_AUDIO_OUT. Anything other than PRIMARY → ILLEGAL_PARAMETER.
- Otherwise stores the value and returns CELL_OK.

## What the game does with the result
VERIFY (callgraph ret_test). The current OK is the expected value for valid input.

## Minimal correct offline PC behaviour
Validate as above, store the value in a static, log once, and return 0.

## Error-path analysis
An error is correct ONLY for invalid input. The PC has no protected output, which is not an error
on hardware: the call succeeds there regardless of the connected device.

## Acceptance test
1. A one-time log line shows `control=N audioOut=0 -> 0`.
2. No behaviour change.
3. Poison run: r3 = 0xCDCDCDCD → does the game branch? (Expect: ignored.)

## Sources
- [pdw_nid] psdevwiki NID page + ps3recomp nid_database.py: NID = first 4 bytes (LE) of SHA-1(name + suffix)
- [pdw_err] psdevwiki, Template:CELL_ERROR_FACILITY_SYSTEM_UTILITY_-_0x002 (error-code tables; fetched 2026-11-27)
- [rp_ao] RPCS3 cellAudioOut.cpp/.h (GPL-2, read for BEHAVIOUR ONLY, nothing copied)
- [p3r_av] ps3recomp libs/misc/cellAvconfExt.c (MIT; this is what the port runs now)
- [pc_report] pc-results/report.csv (Salem's read-only PC run, 2026-11-27)
