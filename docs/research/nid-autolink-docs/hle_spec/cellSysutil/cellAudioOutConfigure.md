---
nid: 0x4692AB35
lib: cellSysutil
name: cellAudioOutConfigure
status_pc: stub (cellAvconfExt.c:219 returns 0, ignores config; registered ppu_hle_nids.cpp:1327)
verdict: needs-real-impl
signature: s32 cellAudioOutConfigure(u32 audioOut /*r3*/, CellAudioOutConfiguration* config /*r4*/, CellAudioOutOption* option /*r5*/, u32 waitForEvent /*r6*/)
outputs: 
poison_ret: yes
confidence: KNOWN (layout, codes) / ASSUMED (hardware behaviour details)
owner_overlap: 
researched: 2026-11-27
---
# cellAudioOutConfigure  (NID 0x4692AB35, cellSysutil)

**Verdict: needs-real-impl (small).** The call itself succeeds on hardware, so returning 0 is right.
What is missing is the **state**: the configuration the game asks for is thrown away. Later,
`cellAudioOutGetConfiguration` and `cellAudioOutGetState` (both linked) always report 2ch LPCM,
while `cellAudioOutGetDeviceInfo` advertises 2/6/8ch LPCM. If the game configures 6 or 8 channels
and then mixes for what it asked for, the host mixer and the game disagree. That is a candidate
link to the 6ch mixer leak (ASSUMED, VERIFY with the log line below).

## Prototype (KNOWN: NID 0x4692AB35 matches; args from [p3r_av] and [rp_ao] agree)
`s32 cellAudioOutConfigure(u32 audioOut, CellAudioOutConfiguration* config, CellAudioOutOption* option, u32 waitForEvent)`
`option` is normally NULL. waitForEvent≠0 means "return after the output has switched".

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

## Hardware behaviour (ASSUMED: paraphrase of [rp_ao], which documents it as observed on PS3)
- config NULL → ILLEGAL_PARAMETER.
- audioOut SECONDARY → UNSUPPORTED_AUDIO_OUT. Any other value that is not PRIMARY → ILLEGAL_PARAMETER.
- Stores channel and encoder. **downMixer > 2 is ignored and the previous value is kept.**
- Picks the matching sound mode if one exists, otherwise keeps the old one (still returns OK).
- Re-initialises the audio output when anything changed; with waitForEvent it does that before returning.
- Returns CELL_OK.

## Side effects
The new configuration must be visible to cellAudioOutGetConfiguration and GetState (byte 1 encoder,
+4 downMixer, soundMode.channel at +9), and ideally to the host mixer's channel count.

## What the game does with the result
VERIFY with `--mode callgraph`: is r3 tested? Which channel count does it pass? The registered
port body prints `[cellAvconfExt] AudioOutConfigure(audioOut=N) -> ok`. Grep an existing PC log for
it (read-only) to learn how often it is called and when.

## Minimal correct offline PC behaviour
1. Validate as above.
2. Keep a static `{channel, encoder, downMixer}` (default 2, LPCM, NONE). Read the struct
   byte-wise from guest memory (u8 at +0 and +1, be32 at +0xC) and apply the downMixer rule.
3. Make GetConfiguration and GetState return the stored values instead of the hard-coded 2ch.
4. Log `cfg ch=%u enc=%u dmx=%u wait=%u`.
5. Do NOT change the host mixer in the same build: one change per build. A host mixer change is a
   separate step after this log shows what the game asks for.

## Error-path analysis
No offline situation makes this fail on hardware: PRIMARY always exists. An error return would be
WRONG for a valid call. The current "return 0" is right for the return value and wrong for the state.

## Poison test (SF_POISON=cellAudioOutConfigure)
r3 = 0xCDCDCDCD. If boot/audio still behaves the same, the game ignores the return, and the only
thing that matters is the stored state.

## Acceptance test (in-game)
1. The log shows the exact config the game asked for (channel / encoder / downMixer).
2. GetConfiguration and GetState called after it return the same values (one log line each).
3. Title → village → battle with audio intact; no audio-thread error; the mixer channel count in
   the existing mixer log matches the configured count.

## Sources
- [pdw_nid] psdevwiki NID page + ps3recomp nid_database.py: NID = first 4 bytes (LE) of SHA-1(name + suffix)
- [pdw_err] psdevwiki, Template:CELL_ERROR_FACILITY_SYSTEM_UTILITY_-_0x002 (error-code tables; fetched 2026-11-27)
- [rp_ao] RPCS3 cellAudioOut.cpp/.h (GPL-2, read for BEHAVIOUR ONLY, nothing copied)
- [p3r_av] ps3recomp libs/misc/cellAvconfExt.c (MIT; this is what the port runs now)
- [pc_report] pc-results/report.csv (Salem's read-only PC run, 2026-11-27)
