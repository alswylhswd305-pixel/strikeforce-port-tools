#!/usr/bin/env python3
"""Writes the hand-researched HLE specs (docs/hle_spec/<lib>/<func>.md).
Behaviour is paraphrased from public docs; no GPL code is copied.
Re-run is safe: it overwrites only the files listed here."""
import os, sys, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from nid_autolink import nid_of

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "hle_spec")
DATE = "2026-11-27"

SRC = {
 "pdw_err": "psdevwiki, Template:CELL_ERROR_FACILITY_SYSTEM_UTILITY_-_0x002 (error-code tables; fetched %s)" % DATE,
 "pdw_pamf": "psdevwiki error-code tables, PAMF range 0x80610501-0x80610508 (fetched 2026-11-26)",
 "pdw_nid": "psdevwiki NID page + ps3recomp nid_database.py: NID = first 4 bytes (LE) of SHA-1(name + suffix)",
 "rp_ao": "RPCS3 cellAudioOut.cpp/.h (GPL-2, read for BEHAVIOUR ONLY, nothing copied)",
 "rp_pamf": "RPCS3 cellPamf.cpp/.h (GPL-2, behaviour + public PAMF file-format facts only, nothing copied)",
 "rp_np": "RPCS3 sceNp.cpp/.h (GPL-2, behaviour only; function marked 'todo' there = not hardware-verified)",
 "rp_osk": "RPCS3 cellOskDialog.cpp/.h (GPL-2, behaviour only, nothing copied)",
 "psl1ght": "PSL1GHT ppu/include/sysutil/osk.h (MIT): prototypes, enums, struct layouts",
 "p3r_av": "ps3recomp libs/misc/cellAvconfExt.c (MIT; this is what the port runs now)",
 "p3r_osk": "ps3recomp libs/misc/cellOskDialog.h + osk_native.c (MIT)",
 "sf_osk": "port strikeforce_osk.inc (Saud's override: auto-answers the name dialog)",
 "pc_report": "pc-results/report.csv (Salem's read-only PC run, 2026-11-27)",
 "runs": "48/50 boot runs: unresolved-NID first-hit dumps (progress-src/runs, findings.json)",
}

def write(lib, name, fm, body):
    nid = nid_of(name)
    d = os.path.join(ROOT, lib); os.makedirs(d, exist_ok=True)
    head = ["---", "nid: 0x%08X" % nid, "lib: %s" % lib, "name: %s" % name]
    for k in ("status_pc", "verdict", "signature", "outputs", "poison_ret", "confidence", "owner_overlap"):
        head.append("%s: %s" % (k, fm.get(k, "")))
    head += ["researched: %s" % DATE, "---", ""]
    txt = "\n".join(head) + "# %s  (NID 0x%08X, %s)\n\n" % (name, nid, lib) + body.strip() + "\n"
    open(os.path.join(d, name + ".md"), "w", encoding="utf-8").write(txt)
    return nid

def srcs(*keys):
    return "\n".join("- [%s] %s" % (k, SRC[k]) for k in keys)

# ---------------------------------------------------------------- cellPamf
write("cellPamf", "cellPamfReaderSetStreamWithTypeAndIndex", dict(
 status_pc="missing (unresolved -> faked CELL_OK = 0)", verdict="needs-real-impl",
 signature="s32 cellPamfReaderSetStreamWithTypeAndIndex(CellPamfReader* pSelf /*r3*/, u8 streamType /*r4*/, u8 streamIndex /*r5*/)",
 outputs="", poison_ret="yes", confidence="KNOWN (signature, error codes, file format) / ASSUMED (who fills the reader)",
 owner_overlap="movie-adjacent: overlaps Salem's cellSail work"), f"""
**Verdict: needs-real-impl** (ASSUMED until the call graph confirms it is reached). On success the
real function does NOT return CELL_OK: it returns the *overall* stream index it selected (a
non-negative number). The unresolved fake returns 0, which means "stream #0 selected" and does not
update the reader. If the game asks for the first AUDIO stream and stream 0 is the video stream, it
gets the wrong stream. That is a real bug, not cosmetic.

> Overlap: this is movie-adjacent. **Salem owns cellSail/movies.** Write and land this only
> after agreeing with Salem, because his cellSail work may already feed the same reader.

## Prototype (KNOWN: NID matches SHA-1 of the name; arg types from [rp_pamf])
`s32 cellPamfReaderSetStreamWithTypeAndIndex(CellPamfReader* pSelf, u8 streamType, u8 streamIndex)`
r3 = guest pointer to the 128-byte reader; r4 = stream type (low 8 bits); r5 = index among
streams of that type (low 8 bits).

## Big-endian guest layouts (ASSUMED: [rp_pamf] says these match the system library, and its size check says 128)
CellPamfReader (128 bytes, written by the game's own PAMF reader code):

| off | type | field |
|---:|---|---|
| 0x00 | be u64 | headerSize |
| 0x08 | be u64 | dataSize |
| 0x10 | be u32 | attribute |
| 0x14 | be u16 | isPsmf (0 = PAMF) |
| 0x16 | be u16 | version |
| 0x18 | be u32 | currentGroupingPeriodIndex |
| 0x1C | be u32 | currentGroupIndex |
| 0x20 | be u32 | **currentStreamIndex** (written by this call) |
| 0x24 | be u32 ptr | header |
| 0x28 | be u32 ptr | sequenceInfo |
| 0x2C | be u32 ptr | currentGroupingPeriod |
| 0x30 | be u32 ptr | **currentGroup** (read by this call) |
| 0x34 | be u32 ptr | **currentStream** (written by this call) |
| 0x38 | u32[18] | reserved |

PamfGroup (inside the .pam file, unaligned, big-endian): +0 be u32 size, +4 u8 reserved,
**+5 u8 stream_num**, +6 the stream headers, **48 bytes each**:
+0 u8 stream_coding_type, +1..3 reserved, +4 u8 stream_id, +5 u8 private_stream_id,
+6 be u16 p_std_buffer, +8 be u32 ep_offset, +12 be u32 ep_num, +16 32 bytes of codec info.

**WARNING (KNOWN):** ps3recomp's own `CellPamfReader` (libs/codec/cellPamf.h) is a host-side
invented layout. Do NOT use it here: the game's own code built the reader with the layout above.

Coding type → stream type (PAMF, not PSMF): 0x1B AVC→0, 0x02 M2V→1, 0xDC ATRAC3PLUS→2,
0x80 LPCM→3, 0x81 AC3→4, 0xDD USER_DATA→5. Group types used in requests: VIDEO=20 matches AVC or
M2V; AUDIO=21 matches ATRAC3PLUS, AC3 or LPCM. Any other request value must equal the exact type.
(ASSUMED: [rp_pamf] mapping; type 22 "UNK" exists there but is not understood.) For PSMF
(isPsmf≠0) the stream type comes from stream_id/private_stream_id, and the system library
reportedly stores the per-type index rather than the overall one. Strikeforce PSMF use is
unknown (VERIFY).

## Return codes (KNOWN: [pdw_pamf]; ps3recomp's cellPamf.h uses the WRONG range 0x806103xx, which collides with ATRAC)
- `>= 0`: success, the overall index i of the selected stream.
- `0x80610503` CELL_PAMF_ERROR_INVALID_ARG: streamIndex >= currentGroup->stream_num.
- `0x80610501` CELL_PAMF_ERROR_STREAM_NOT_FOUND: fewer than streamIndex+1 streams of that type.
- The system library does not check pSelf for NULL (ASSUMED, [rp_pamf] comment).

## Side effects
On success it writes reader+0x20 = i (PAMF) and reader+0x34 = address of stream header i.
Nothing else changes.

## What the game does with the result
VERIFY. Run `--mode callgraph` on the PC: the `ret_test` for each call site tells whether the game
branches on `r3 < 0` (error path) or uses r3 as an index. No call was logged in the 48/50 boot runs,
so it is not on the boot path (KNOWN from [runs] + [pc_report]: no LR recorded).

## Minimal correct single-player offline PC behaviour
Pure parsing of guest memory. No host resource is involved, so there is NO offline excuse:
1. Read the currentGroup pointer at reader+0x30, then stream_num at group+5.
2. If streamIndex >= stream_num, return INVALID_ARG.
3. Walk the stream headers at group+6+48*i, map each coding type, count the matches and stop at
   match number streamIndex+1.
4. Write +0x20 and +0x34, then return i. If nothing matches, return STREAM_NOT_FOUND.

Do all reads and writes byte-wise big-endian (vm_read8 / vm_write32).

## Error-path analysis
A documented error is correct only when the file really lacks the stream (for example a movie with
no audio). Returning an error, or the fake 0, for a valid file is WRONG.

## Poison test (diagnostic, SF_POISON=cellPamfReaderSetStreamWithTypeAndIndex)
r3 = 0xCDCDCDCD (negative). If a movie/cutscene then fails differently than with the fake 0,
the game tests the return. Only useful once we know which scene reaches it (callgraph first).

## Acceptance test (in-game)
1. The scene that reaches it is identified from callers.json (and the LR in the stub log).
2. The log shows `type=21 index=0 -> i` with i equal to the audio stream's position (usually 1).
3. That movie/cutscene plays with the correct audio track and no `[hle] UNRESOLVED NID 0x28B4E2C1`.
4. Regression check: Salem's cellSail movies are unchanged.

## Sources
{srcs("pdw_nid", "pdw_pamf", "rp_pamf", "pc_report", "runs")}
""")

# ---------------------------------------------------------------- cellAudioOut
AO_COMMON = """
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
"""
write("cellSysutil", "cellAudioOutConfigure", dict(
 status_pc="stub (cellAvconfExt.c:219 returns 0, ignores config; registered ppu_hle_nids.cpp:1327)",
 verdict="needs-real-impl", signature="s32 cellAudioOutConfigure(u32 audioOut /*r3*/, CellAudioOutConfiguration* config /*r4*/, CellAudioOutOption* option /*r5*/, u32 waitForEvent /*r6*/)",
 outputs="", poison_ret="yes", confidence="KNOWN (layout, codes) / ASSUMED (hardware behaviour details)"), f"""
**Verdict: needs-real-impl (small).** The call itself succeeds on hardware, so returning 0 is right.
What is missing is the **state**: the configuration the game asks for is thrown away. Later,
`cellAudioOutGetConfiguration` and `cellAudioOutGetState` (both linked) always report 2ch LPCM,
while `cellAudioOutGetDeviceInfo` advertises 2/6/8ch LPCM. If the game configures 6 or 8 channels
and then mixes for what it asked for, the host mixer and the game disagree. That is a candidate
link to the 6ch mixer leak (ASSUMED, VERIFY with the log line below).

## Prototype (KNOWN: NID 0x4692AB35 matches; args from [p3r_av] and [rp_ao] agree)
`s32 cellAudioOutConfigure(u32 audioOut, CellAudioOutConfiguration* config, CellAudioOutOption* option, u32 waitForEvent)`
`option` is normally NULL. waitForEvent≠0 means "return after the output has switched".
{AO_COMMON}
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
2. Keep a static `{{channel, encoder, downMixer}}` (default 2, LPCM, NONE). Read the struct
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
{srcs("pdw_nid", "pdw_err", "rp_ao", "p3r_av", "pc_report")}
""")

write("cellSysutil", "cellAudioOutSetCopyControl", dict(
 status_pc="stub (cellAvconfExt.c:160 returns OK, no validation; registered ppu_hle_nids.cpp:1322)",
 verdict="ok-setting-sink", signature="s32 cellAudioOutSetCopyControl(u32 audioOut /*r3*/, u32 control /*r4*/)",
 outputs="", poison_ret="yes", confidence="KNOWN (codes) / ASSUMED (validation rules)"), f"""
**Verdict: ok-setting-sink** (plus validation). It sets the copy-protection flag on the digital
audio output (SCMS: FREE 0, ONCE 1, NEVER 2). No API reads it back and a PC has no SCMS, so storing
it and returning OK is the correct, complete behaviour. Only the documented parameter checks are missing.

## Prototype (KNOWN: NID 0xC96E89E9 matches; [p3r_av] and [rp_ao] agree on args)
`s32 cellAudioOutSetCopyControl(u32 audioOut, u32 control)`
{AO_COMMON}
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
{srcs("pdw_nid", "pdw_err", "rp_ao", "p3r_av", "pc_report")}
""")

# ---------------------------------------------------------------- sceNp
write("sceNp", "sceNpBasicGetCustomInvitationEntryCount", dict(
 status_pc="missing (unresolved -> fake CELL_OK, *count NOT written); hit 2x per boot in 48/50 runs, lr 0x00037920",
 verdict="needs-real-impl", signature="s32 sceNpBasicGetCustomInvitationEntryCount(u32* count /*r3*/)",
 outputs="r3:4", poison_ret="no", confidence="KNOWN (NID, error codes, call evidence) / ASSUMED (exact hardware checks)"), f"""
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
{srcs("pdw_nid", "pdw_err", "rp_np", "runs", "pc_report")}
""")

# ---------------------------------------------------------------- OSK
OSK_CODES = """## Return codes (KNOWN: [pdw_err] and [rp_osk] agree)
`0x8002B501` IME_ALREADY_IN_USE, `0x8002B502` GET_SIZE_ERROR, `0x8002B503` UNKNOWN, `0x8002B504` **PARAM**.
**Port bug (KNOWN):** ps3recomp `cellOskDialog.h` and Saud's `strikeforce_osk.inc` use
`0x8002B30x`, which is the **MSGDIALOG** range (0x8002B301 = CELL_MSGDIALOG_ERROR_PARAM per
[pdw_err]). Any OSK error the game tests against will not match. Fix those constants in a separate,
approved build.
"""
OSK_CTX = """## Context
Strikeforce's name-entry dialog is answered automatically by `strikeforce_osk.inc` (SF_OSK_TEXT,
default "Saud"; it queues LOADED 0x0502 + FINISHED 0x0503). These Set*/Ext* calls are made just
before LoadAsync (LRs 0x0049FD9C..0x0049FDCC, KNOWN from [pc_report]) and configure how the real
system keyboard would look. No getter API exists, so the game cannot read the values back
(KNOWN: no Get* for them in [psl1ght] or [rp_osk]). The port's auto-answer has no visible keyboard,
so storing the values is complete behaviour.
"""
def osk(lib, name, sig, rule, layout="", conf="KNOWN (prototype, codes) / ASSUMED (validation rules)", extra="", status="stub (hle_ok)"):
    write(lib, name, dict(status_pc=status, verdict="ok-setting-sink", signature=sig, outputs="",
                          poison_ret="yes", confidence=conf), f"""
**Verdict: ok-setting-sink** (+ documented validation + log). Returning CELL_OK for valid input is
what hardware does. What is missing is the documented PARAM check and a log line.

## Prototype
`{sig}`
{layout}
## Hardware behaviour (ASSUMED: paraphrase of [rp_osk]; prototypes and enums from [psl1ght])
{rule}

{OSK_CODES}
{OSK_CTX}
{extra}
## Minimal correct offline PC behaviour
Validate exactly as above (otherwise return 0x8002B504), store the value in the OSK state struct,
log once, and return 0. Nothing visual is needed while the name dialog is auto-answered.

## Error-path analysis
No offline or PC situation makes this fail on hardware. Only invalid arguments do. An error return
for valid input would be WRONG.

## Poison test (SF_POISON={name})
r3 = 0xCDCDCDCD. If the name dialog still completes, the game ignores the return (expected). If it
skips or retries LoadAsync, the game checks the return. Record which.

## Acceptance test (in-game)
1. New game → name entry: the log shows this call with its argument value and `-> 0`.
2. LoadAsync → LOADED → FINISHED events arrive, and the name (SF_OSK_TEXT) appears in the save/HUD.
3. There is no UNRESOLVED line for this NID, and the call count matches one per dialog open.

## Sources
{srcs("pdw_nid", "pdw_err", "psl1ght", "rp_osk", "p3r_osk", "sf_osk", "pc_report")}
""")

osk("cellSysutil", "cellOskDialogAddSupportLanguage", "s32 cellOskDialogAddSupportLanguage(u32 supportLanguage /*r3*/)",
    "- No validation. Stores the language bit-mask (Korean 0x1000, Danish 0x20000, ... per [psl1ght]) and returns OK.",
    status="stub (strikeforce_osk.inc:62 hle_ok); LR 0x0049FD9C")
osk("cellSysutil", "cellOskDialogSetInitialKeyLayout", "s32 cellOskDialogSetInitialKeyLayout(u32 initialKeyLayout /*r3*/)",
    "- Values: 0 SYSTEM, 1 10KEY, 2 FULLKEY. A value > 2 → PARAM.\n- Applied only when it is allowed by the current KeyLayoutOption bits; otherwise it is silently ignored and still returns OK.",
    status="stub (ppu_hle_nids.cpp:1756)")
osk("cellSysutil", "cellOskDialogSetKeyLayoutOption", "s32 cellOskDialogSetKeyLayoutOption(u32 option /*r3*/)",
    "- Bit flags: 1 = 10KEY panel, 2 = FULLKEY panel. 0 or > 3 → PARAM. Otherwise it stores the flags and returns OK.",
    status="stub (strikeforce_osk.inc:63 hle_ok); LR 0x0049FDA8")
osk("cellSysutil", "cellOskDialogSetLayoutMode", "s32 cellOskDialogSetLayoutMode(s32 layoutMode /*r3*/)",
    "- OR of alignment flags: H right 0x200, H center 0x400, H left 0x800, V bottom 0x1000, V center 0x2000, V top 0x4000. No validation. Stores the flags and returns OK.",
    status="stub (ppu_hle_nids.cpp:1757)")
osk("cellSysutil", "cellOskDialogDisableDimmer", "s32 cellOskDialogDisableDimmer(void)",
    "- No args, no validation. Turns off background dimming while the OSK is open and returns OK.",
    status="stub (strikeforce_osk.inc:64 hle_ok)")
osk("cellSysutil", "cellOskDialogSetInitialInputDevice", "s32 cellOskDialogSetInitialInputDevice(u32 inputDevice /*r3*/)",
    "- 0 = PAD, 1 = KEYBOARD. A value > 1 → PARAM. Otherwise it stores the device and returns OK.",
    status="stub (ppu_hle_nids.cpp:1755)",
    extra="Note: the game also reads the keyboard via cellKbRead (stub, LR 0x0049E1B0). That is a separate spec.\n")
osk("cellSysutil", "cellOskDialogSetSeparateWindowOption", "s32 cellOskDialogSetSeparateWindowOption(CellOskDialogSeparateWindowOption* opt /*r3*/)",
    "- PARAM if: opt NULL, inputFieldLayoutInfo NULL, reserved ≠ 0, continuousMode > 3, or deviceMask > 0xFF.\n- Otherwise: separate-window mode on; stores mode, mask, width, transparency (clamped 0..1), and the field layout. The panel layout is optional (NULL keeps the default). Returns OK.",
    layout="""
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
""", status="stub (ppu_hle_nids.cpp:1758)")
osk("cellOskExtUtility", "cellOskDialogExtRegisterForceFinishCallback",
    "s32 cellOskDialogExtRegisterForceFinishCallback(cb /*r3*/)  // cb: bool(void) guest OPD pointer",
    "- cb NULL → PARAM. Otherwise it stores the callback and returns OK.\n- The system calls it only when the PS button would interrupt a hidden continuous-mode OSK, asking the game whether it may close the dialog. A PC port has no PS-button overlay, so it is never called (correct).",
    status="stub (strikeforce_osk.inc:66 hle_ok); LR 0x0049FDCC")
osk("cellOskExtUtility", "cellOskDialogExtSetInitialScale",
    "s32 cellOskDialogExtSetInitialScale(f32 initialScale /*f1, NOT r3*/)",
    "- The float arrives in **f1** (PPU ABI), so a ctx handler must read ctx->fpr[1]. The same trap is documented in [p3r_av] for VideoOutSetGamma.\n- Range 0.80 .. 1.05 (ASSUMED: [rp_osk] header constants; VERIFY on psdevwiki). Out of range → PARAM. Otherwise it stores the scale and returns OK.",
    status="stub (strikeforce_osk.inc:65 hle_ok); LR 0x0049FDC0")
osk("cellOskExtUtility", "cellOskDialogExtInputDeviceLock", "s32 cellOskDialogExtInputDeviceLock(void)",
    "- No args. Sets a flag so the OSK ignores pad/keyboard events (while the game itself uses the device), and returns OK.",
    status="missing (unresolved fake OK); never logged in [runs]")
osk("cellOskExtUtility", "cellOskDialogExtInputDeviceUnlock", "s32 cellOskDialogExtInputDeviceUnlock(void)",
    "- No args. Clears that flag and returns OK.", status="missing (unresolved fake OK)")
osk("cellOskExtUtility", "cellOskDialogExtRegisterConfirmWordFilterCallback",
    "s32 cellOskDialogExtRegisterConfirmWordFilterCallback(cb /*r3*/)  // cb: int(u16* utf16Str, s32 len)",
    "- cb NULL → PARAM. Otherwise it stores the callback and returns OK.\n- On hardware the system calls it when the user confirms text, so the game can reject a word (for example a profanity filter for the officer name).",
    status="missing (unresolved fake OK)",
    extra="**Fidelity note (ASSUMED):** with the auto-answer, a filter that would reject SF_OSK_TEXT is never consulted. For full fidelity the auto-answer could call the stored callback once with the text before sending FINISHED. That needs guest-callback plumbing, so it is optional and a separate build.\n")
osk("cellOskExtUtility", "cellOskDialogExtRegisterKeyboardEventHookCallback",
    "s32 cellOskDialogExtRegisterKeyboardEventHookCallback(u16 hookEventMode /*r3*/, cb /*r4*/)",
    "- hookEventMode is a bit mask of 1 = FUNCTION_KEY and 2 = ASCII_KEY (ASSUMED, [rp_osk]). 0 or > 3 → PARAM. cb NULL → PARAM (ASSUMED).\n- On hardware the hook sees hardware-keyboard keys while the OSK is open. Not reachable with the auto-answer.",
    status="missing (unresolved fake OK)")

print("specs written under", ROOT)
