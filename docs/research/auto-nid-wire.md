# auto_nid_wire.py — prototype HLE wiring helper

2026-11-26, Asia/Kuwait (UTC+3). Built and self-tested on the box only.
Never run against Saud's Strikeforce build. Skeletons are not implementations.

Tool: `/workspace/sf-shared/tools/auto_nid_wire.py`
Testdata: `/workspace/sf-shared/tools/auto_nid_wire_testdata/synthetic.log`

## What it does

Five-step pipeline:

1. **Parse** a runtime log of unhandled-NID calls and rank them by call count.
2. **Name** each NID: first by ps3recomp's SHA-1 formula against a candidate
   name list, then by a local `nids.txt` lookup that is SHA-1-verified again.
3. **Prototype**: look the name up in PSL1GHT headers (MIT). Classify every
   pointer parameter as input / output / in-out, tagged `KNOWN` or `ASSUMED`.
4. **Generate** a C HLE skeleton in ps3recomp style (`s32` handler +
   `ps3_hle_register_ctx` thunk, same idea as `strikeforce_sail.inc`):
   log the arguments, zero classified output params, return `CELL_OK`, and
   leave a TODO that summarises RPCS3 behaviour **in our own words** with a
   file:line citation. No GPL is copied.
5. **Checklist**: a same-call comparison against an RPCS3 log of that function.

## Usage

```bash
# Built-in tests (synthetic log + the six named cellSail/cellPamf NIDs +
# a few PSL1GHT prototypes). This is what was run on the box.
python3 /workspace/sf-shared/tools/auto_nid_wire.py --self-test

# A real port log, once Salem emits one:
python3 auto_nid_wire.py --log stderr.log --out ./wire-out

# Also accepted: sfauto findings.json, an imports list, and/or a NID list.
python3 auto_nid_wire.py \
    --log findings.json \
    --nids 0x0D0C2F0C,0x15FD6A2A,0xC044FAB1,0xD1D55A90,0xDDEBD2A5,0x28B4E2C1 \
    --nids-txt /path/to/nids.txt \
    --psl1ght /path/to/PSL1GHT \
    --ps3recomp /path/to/ps3recomp \
    --rpcs3 /path/to/rpcs3 \
    --out ./wire-out
```

Defaults on this box (used if the flags are omitted and the path exists):

- PSL1GHT: `/workspace/ghtools/ps3dev_PSL1GHT` (already fetched, MIT)
- nids.txt: `/workspace/nidlookup/nids.txt` (lookup only — see below)
- ps3recomp: `/workspace/ps3-research/ps3recomp`
- RPCS3 sources: `/workspace/ps3-research/rpcs3src` (citation only)

`--fetch-psl1ght` will `git clone --depth 1 https://github.com/ps3dev/PSL1GHT`
into `tools/_cache/PSL1GHT` if no tree is found.

Outputs in `--out`:

| file                    | contents                                              |
|-------------------------|--------------------------------------------------------|
| `unresolved_ranked.txt` | NIDs sorted by call count                              |
| `skeletons.c`           | C handlers + ctx thunks                                |
| `register.inc`          | `ps3_hle_register_ctx(..., "[skel]", ...)` lines       |
| `checklist.md`          | per-NID same-call RPCS3 checks                         |
| `report.json`           | machine-readable copy of the same facts                |

## Log formats

### What ps3recomp already prints

`runtime/ppu/ppu_hle.cpp` (`ps3_hle_unresolved`) prints each **distinct**
unresolved NID **once**, plus a 3–4 line register dump:

```
[hle] UNRESOLVED NID 0xC044FAB1 -> faking CELL_OK (unregistered import; ...)
[hle]   0xC044FAB1 tid=1   r3 =... r4 =... r5 =... r6 =...
[hle]   0xC044FAB1          r7 =... r8 =... r9 =... r10=...
[hle]   0xC044FAB1          sp =... lr =...
[hle]   0xC044FAB1          arg9=... arg10=... arg11=... arg12=...  @SP+112
```

The `hits[]` array is updated but **never printed**, so a first-hit-only log
gives `hits=1` with `count_complete=False`. sfauto `findings.json`
(`unresolved_nids` / `unresolved_ctx`) is parsed the same way.

### What Salem should emit (in addition, not instead)

Per call (optional, e.g. behind `PS3_HLE_UNRESOLVED_LOG=all`):

```
[hle] UNRESOLVED CALL nid=0x%08X lib=%s name=%s hits=%u tid=%u lr=0x%08X r3=%016llX r4=%016llX r5=%016llX r6=%016llX r7=%016llX r8=%016llX r9=%016llX r10=%016llX
```

Once at process exit (required for real counts — dump the existing `hits[]`):

```
[hle] UNRESOLVED SUMMARY nid=0x%08X hits=%u lib=%s
```

`hits=` on a CALL line is a running counter (the tool takes the maximum). If
every CALL for a NID has `hits=1` and there is no SUMMARY, the tool counts
the lines. A SUMMARY always wins.

## Name resolution

Order is strict:

1. SHA-1(`name` + 16-byte suffix `67 59 65 99 04 25 04 90 56 64 27 49 94 89 74 1A`),
   first 4 bytes little-endian — the same formula as `tools/nid_database.py` /
   `tools/nid_verify.py`. Candidates come from: the ten already-verified
   Strikeforce names baked into the tool, `--names`, names harvested from
   PSL1GHT and `--extra-headers`, and `nid_database.py` builtins if
   `--ps3recomp` is set.
2. `nids.txt`, **then the name is hashed again**. A hash mismatch is rejected,
   not trusted.

`zecoxao/sce_symbols` `nids.txt` has **no licence**. Lookup only. Do not copy
that file into the port, the tool output, or a commit.

The six cellSail / cellPamf names (and `sceNpBasicGetCustomInvitationEntryCount`)
resolve by SHA-1 with no `nids.txt` at all. That was confirmed in `--self-test`.

## Prototypes

PSL1GHT is the first source, and a hit there is the only `KNOWN` signature
source. Official PSL1GHT (`ppu/include`) has **no** `cellSail` / `cellPamf`
headers — confirmed: 677 declarations indexed, zero of the six names present.

When PSL1GHT has nothing:

- Optional fallback: `--extra-headers` / `ps3recomp/libs/*.h` (tagged
  `ps3recomp-header`, not claimed as PSL1GHT).
- Then a small `ASSUMED_PROTOS` table for the six named functions, from
  naming, neighbour declarations, and the *arity* of the RPCS3 binding
  (not the body). Every parameter is `ASSUMED`. Open / SetEs / AviMovie
  arity is especially uncertain — those RPCS3 bindings declare no parameters.
- Otherwise a ctx stub that logs r3–r10 and zeroes nothing.

Classification of pointer parameters:

| rule                                         | direction | tag     |
|----------------------------------------------|-----------|---------|
| `const T *`                                  | input     | KNOWN   |
| scalar / by-value                            | input     | KNOWN   |
| first-arg `pSelf` / `reader` / `player` / …  | in-out    | ASSUMED (object is not zeroed) |
| non-const pointer on a Get/Check-like name   | output    | ASSUMED |
| name looks like `value` / `handle` / `buf`   | output    | ASSUMED |
| name looks like `param` / `src` on Set-like  | input     | ASSUMED |
| anything else non-const                      | in-out    | ASSUMED (not zeroed) |

Output pointers are initialised with `vm_write32` (or 8/16/64 as the type
suggests). A struct of unknown size only has its first 4 bytes cleared, with
a comment that a human must size it.

## RPCS3 notes

RPCS3 is GPL. The tool never copies a body. For the six named functions the
TODO is a paraphrase with a citation, written by hand from a read of the
reference:

- `cellSailDescriptorOpen` / `Close` / `SetEs` / `AviMovieGetStreamByTypeAndIndex`
  are unimplemented stubs that log and return success
  (`cellSail.cpp` 149, 155, 161, 592).
- `cellSailPlayerSetPaused` (`cellSail.cpp:1009`) takes a player pointer and
  a paused flag, logs a TODO, returns success, and does **not** update the
  pause flag that `IsPaused` reads.
- `cellPamfReaderSetStreamWithTypeAndIndex` (`cellPamf.cpp:969`) is a real
  implementation: it selects a stream by type and type-local index, returns
  the overall index on success, or invalid-argument / stream-not-found.
  Reimplement from that description and a same-call log; do not copy the body.

`--rpcs3` can classify *other* names as "unimplemented stub" / "TODO stub" /
"a definition exists at file:line" by looking at a short window around the
definition. That is a lead, not a licence to paste.

## What is automatic

- Reading the existing first-hit log, the new CALL/SUMMARY lines, and
  `findings.json`.
- Ranking by call count when a SUMMARY or per-call hits exist.
- Naming a NID whose name is in the candidate list or in `nids.txt`, with a
  SHA-1 check either way.
- Finding a PSL1GHT prototype when one exists, and tagging pointer directions.
- Emitting a skeleton, a registration line, and a checklist.

## What is not automatic (still needs a human)

- **Real behaviour.** A skeleton that returns `CELL_OK` and zeroes a few
  out-params is the same class of lie as today's unresolved path, just more
  visible. `cellPamfReaderSetStreamWithTypeAndIndex` in particular will
  mislead a title if it always returns success and never selects a stream.
- **Prototypes for cellSail / cellPamf.** They are not in PSL1GHT. Assumed
  arities can be wrong. Confirm against a register dump and, if needed, the
  SDK docs.
- **Call counts** on a current first-hit-only log. Add the SUMMARY lines.
- **Registering** the thunk. Do not include `register.inc` in a release
  build until the body is filled in and the checklist has been walked.
- **The other 69 of the 72 unresolved NIDs** that have not been seen at
  runtime. Naming them is easy; knowing whether the title ever calls them
  is not.
- **Anything that needs GPL.** Do not paste RPCS3 into the port.
- **This has not been run on Saud's PC or against a live Strikeforce
  stderr log from the current in-game build.**

## Self-test status

`python3 auto_nid_wire.py --self-test` passed on this box (2026-11-26,
Asia/Kuwait): synthetic log counts, SHA-1 of the six names without
`nids.txt`, rejection of a lying `nids.txt` row, PSL1GHT classification of
`sysGameGetParamInt` / `BootCheck` / `SetParamString` / `DataCheck`, and
skeleton/checklist emission for the six. It does **not** prove the tool
against a real game run.
