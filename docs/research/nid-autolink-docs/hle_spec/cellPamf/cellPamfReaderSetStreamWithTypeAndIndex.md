---
nid: 0x28B4E2C1
lib: cellPamf
name: cellPamfReaderSetStreamWithTypeAndIndex
status_pc: missing (unresolved -> faked CELL_OK = 0)
verdict: needs-real-impl
signature: s32 cellPamfReaderSetStreamWithTypeAndIndex(CellPamfReader* pSelf /*r3*/, u8 streamType /*r4*/, u8 streamIndex /*r5*/)
outputs: 
poison_ret: yes
confidence: KNOWN (signature, error codes, file format) / ASSUMED (who fills the reader)
owner_overlap: movie-adjacent: overlaps Salem's cellSail work
researched: 2026-11-27
---
# cellPamfReaderSetStreamWithTypeAndIndex  (NID 0x28B4E2C1, cellPamf)

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
- [pdw_nid] psdevwiki NID page + ps3recomp nid_database.py: NID = first 4 bytes (LE) of SHA-1(name + suffix)
- [pdw_pamf] psdevwiki error-code tables, PAMF range 0x80610501-0x80610508 (fetched 2026-11-26)
- [rp_pamf] RPCS3 cellPamf.cpp/.h (GPL-2, behaviour + public PAMF file-format facts only, nothing copied)
- [pc_report] pc-results/report.csv (Salem's read-only PC run, 2026-11-27)
- [runs] 48/50 boot runs: unresolved-NID first-hit dumps (progress-src/runs, findings.json)
