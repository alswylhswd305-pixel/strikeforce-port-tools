#!/usr/bin/env python3
# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
"""auto_nid_wire.py — prototype HLE wiring helper for ps3recomp.

Pipeline:
  1. Parse a runtime log of unhandled-NID calls, ranked by call count.
  2. Resolve names: SHA-1 NID formula against a candidate list, then nids.txt.
  3. Look up the prototype in PSL1GHT headers (MIT). Classify pointer params
     as input/output, tagging each KNOWN or ASSUMED.
  4. Emit a C HLE skeleton in ps3recomp handler style: log args, zero every
     output param, return CELL_OK, and a TODO that summarises RPCS3 behaviour
     in our own words (file:line only; no GPL is copied).
  5. Emit a test checklist that compares the same call against an RPCS3 log.

This is a prototype, tested on synthetic input and on the six already-named
cellSail/cellPamf NIDs. It has never been run against Saud's Strikeforce
build. Skeletons are not implementations. A human must review the prototype,
fill in behaviour, and compare against RPCS3 before registering a handler.

nids.txt (zecoxao/sce_symbols) has no licence: lookup only, never vendor it
into the port. RPCS3 is GPL: behaviour reference only, no code copy.

Usage:
    python3 auto_nid_wire.py --self-test
    python3 auto_nid_wire.py --log game.stderr.log --out ./wire-out
    python3 auto_nid_wire.py --nids 0x0D0C2F0C,0x15FD6A2A --out ./wire-out \
        --nids-txt /path/to/nids.txt --psl1ght /path/to/PSL1GHT
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import sys
import textwrap
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

# Official Sony NID suffix used by ps3recomp tools/nid_database.py and
# tools/nid_verify.py: first 4 bytes of SHA-1(name + suffix), little-endian.
NID_SUFFIX = bytes([
    0x67, 0x59, 0x65, 0x99, 0x04, 0x25, 0x04, 0x90,
    0x56, 0x64, 0x27, 0x49, 0x94, 0x89, 0x74, 0x1A,
])

# ---------------------------------------------------------------------------
# Log formats
# ---------------------------------------------------------------------------
#
# Current ps3recomp (runtime/ppu/ppu_hle.cpp, ps3_hle_unresolved):
#   Each DISTINCT unresolved NID is printed once, with a 3-4 line register
#   dump. The hits[] counter is kept but is NOT printed at process end, so a
#   first-hit-only log cannot give a real call count (count_complete=False).
#
# Preferred Salem format — please emit these in addition, not instead:
#
#   Per call (optional; set e.g. PS3_HLE_UNRESOLVED_LOG=all):
#     [hle] UNRESOLVED CALL nid=0x%08X lib=%s name=%s hits=%u tid=%u lr=0x%08X
#           r3=%016llX r4=%016llX r5=%016llX r6=%016llX
#           r7=%016llX r8=%016llX r9=%016llX r10=%016llX
#
#   Once at process exit (required for counts; dump the hits[] array):
#     [hle] UNRESOLVED SUMMARY nid=0x%08X hits=%u lib=%s
#
# lib= and name= are optional. hits= on CALL lines is a running counter for
# that NID (the tool takes the maximum). If every CALL for a NID has hits=1
# and there is no SUMMARY, the tool counts the lines instead.
#
# Also accepted:
#   - sfauto findings.json  ({"unresolved_nids": [...], "unresolved_ctx": {nid: lr}})
#   - "cellSail  0x0D0C2F0C  cellSailDescriptorSetEs"  (imports list; no counts)
#   - "0x0D0C2F0C cellSailDescriptorSetEs" / "nid=0x.. hits=N lib=.."

RX_FIRSTHIT = re.compile(
    r"\[hle\] UNRESOLVED NID 0x([0-9A-Fa-f]{8})\s*->\s*faking\s+(\S+)"
)
RX_DUMP_R3 = re.compile(
    r"\[hle\]\s+0x([0-9A-Fa-f]{8})\s+tid=\s*(\d+)\s+"
    r"r3\s*=\s*([0-9A-Fa-f]+)\s+r4\s*=\s*([0-9A-Fa-f]+)\s+"
    r"r5\s*=\s*([0-9A-Fa-f]+)\s+r6\s*=\s*([0-9A-Fa-f]+)"
)
RX_DUMP_R7 = re.compile(
    r"\[hle\]\s+0x([0-9A-Fa-f]{8})\s+"
    r"r7\s*=\s*([0-9A-Fa-f]+)\s+r8\s*=\s*([0-9A-Fa-f]+)\s+"
    r"r9\s*=\s*([0-9A-Fa-f]+)\s+r10\s*=\s*([0-9A-Fa-f]+)"
)
RX_DUMP_SP = re.compile(
    r"\[hle\]\s+0x([0-9A-Fa-f]{8})\s+"
    r"sp\s*=\s*([0-9A-Fa-f]+)\s+lr\s*=\s*([0-9A-Fa-f]+)"
)
RX_DUMP_ARG9 = re.compile(
    r"\[hle\]\s+0x([0-9A-Fa-f]{8})\s+"
    r"arg9=([0-9A-Fa-f]+)\s+arg10=([0-9A-Fa-f]+)\s+"
    r"arg11=([0-9A-Fa-f]+)\s+arg12=([0-9A-Fa-f]+)"
)
RX_CALL = re.compile(
    r"\[hle\] UNRESOLVED CALL\s+nid=0x([0-9A-Fa-f]{8})"
    r"(?:\s+lib=(\S+))?(?:\s+name=(\S+))?"
    r"(?:\s+hits=(\d+))?(?:\s+tid=(\d+))?(?:\s+lr=0x([0-9A-Fa-f]+))?"
    r"(.*)$"
)
RX_SUMMARY = re.compile(
    r"\[hle\] UNRESOLVED SUMMARY\s+nid=0x([0-9A-Fa-f]{8})\s+hits=(\d+)"
    r"(?:\s+lib=(\S+))?(?:\s+name=(\S+))?"
)
RX_KV_REG = re.compile(r"\b(r(?:1[0-2]|\d)|arg(?:9|10|11|12))=([0-9A-Fa-f]+)")
RX_IMPORT_LINE = re.compile(
    r"^(?:(?P<lib>[A-Za-z_]\w*)\s+)?0x(?P<nid>[0-9A-Fa-f]{8})\s+(?P<name>[A-Za-z_?]\w*)"
)
RX_NID_HITS = re.compile(
    r"(?:nid=)?0x([0-9A-Fa-f]{8}).*?\bhits=(\d+)", re.I
)

# Names independently verified with compute_nid() (see nid-names-1435.txt and
# github-tools-new-2026.md). Stored here so SHA-1 resolution works without
# nids.txt. Re-checked at runtime; a mismatch is a hard error.
VERIFIED_NAMES: dict[int, tuple[str, str]] = {
    0x0D0C2F0C: ("cellSail", "cellSailDescriptorSetEs"),
    0x15FD6A2A: ("cellSail", "cellSailDescriptorClose"),
    0xC044FAB1: ("cellSail", "cellSailDescriptorOpen"),
    0xD1D55A90: ("cellSail", "cellSailPlayerSetPaused"),
    0xDDEBD2A5: ("cellSail", "cellSailAviMovieGetStreamByTypeAndIndex"),
    0x28B4E2C1: ("cellPamf", "cellPamfReaderSetStreamWithTypeAndIndex"),
    0x7EB8D6B5: ("cellSail", "cellSailSoundAdapterGetFrame"),
    0xEEC22809: ("cellSail", "cellSailSoundAdapterUpdateAvSync"),
    0xF25F197D: ("cellSail", "cellSailSoundAdapterGetFormat"),
    0xA8AFA7D4: ("sceNp", "sceNpBasicGetCustomInvitationEntryCount"),
}

SIX_SAIL_PAMF = (
    0x0D0C2F0C,
    0x15FD6A2A,
    0xC044FAB1,
    0xD1D55A90,
    0xDDEBD2A5,
    0x28B4E2C1,
)

# ASSUMED signatures for the six, used only when PSL1GHT has no prototype
# (official PSL1GHT does not ship cellSail/cellPamf headers). Sources:
# naming, neighbour declarations in ps3recomp's own headers, and the
# parameter list of the RPCS3 *binding* (arity only, not the body).
# Every parameter is tagged ASSUMED. Arity for Open / SetEs / AviMovie is
# especially uncertain because those RPCS3 bindings declare no parameters.
ASSUMED_PROTOS: dict[str, str] = {
    "cellSailDescriptorClose":
        "s32 cellSailDescriptorClose(CellSailDescriptor* pSelf)",
    "cellSailDescriptorOpen":
        "s32 cellSailDescriptorOpen(CellSailDescriptor* pSelf)",
    "cellSailDescriptorSetEs":
        "s32 cellSailDescriptorSetEs(CellSailDescriptor* pSelf, s32 type, s32 index)",
    "cellSailPlayerSetPaused":
        "s32 cellSailPlayerSetPaused(CellSailPlayer* pSelf, u8 paused)",
    "cellSailAviMovieGetStreamByTypeAndIndex":
        "s32 cellSailAviMovieGetStreamByTypeAndIndex("
        "CellSailAviMovie* pSelf, s32 type, s32 index, void* pStream)",
    "cellPamfReaderSetStreamWithTypeAndIndex":
        "s32 cellPamfReaderSetStreamWithTypeAndIndex("
        "CellPamfReader* pSelf, u8 streamType, u8 streamIndex)",
}

# RPCS3 behaviour in OUR words, with a file:line citation. No GPL code.
RPCS3_NOTES: dict[str, str] = {
    "cellSailDescriptorOpen":
        "Unimplemented stub: it logs that the call is unfinished and "
        "returns success without updating descriptor state. "
        "Cite: rpcs3/Emu/Cell/Modules/cellSail.cpp:149.",
    "cellSailDescriptorClose":
        "Unimplemented stub: it logs that the call is unfinished and "
        "returns success without updating descriptor state. "
        "Cite: rpcs3/Emu/Cell/Modules/cellSail.cpp:155.",
    "cellSailDescriptorSetEs":
        "Unimplemented stub: it logs that the call is unfinished and "
        "returns success; elementary-stream selection is not applied. "
        "Cite: rpcs3/Emu/Cell/Modules/cellSail.cpp:161.",
    "cellSailAviMovieGetStreamByTypeAndIndex":
        "Unimplemented stub: it logs that the call is unfinished and "
        "returns success without writing a stream record. "
        "Cite: rpcs3/Emu/Cell/Modules/cellSail.cpp:592.",
    "cellSailPlayerSetPaused":
        "Binding takes a player pointer and a paused flag. The body logs a "
        "TODO with those two arguments and returns success; it does not "
        "update the player pause flag (the sibling IsPaused call still "
        "reads that flag). Cite: rpcs3/Emu/Cell/Modules/cellSail.cpp:1009.",
    "cellPamfReaderSetStreamWithTypeAndIndex":
        "This one is actually implemented on the reference. It takes a "
        "reader, a stream type and a type-local stream index, walks the "
        "current group for streams of that type, and on success records "
        "the current stream and returns the overall stream index as a "
        "non-error value. Out-of-range index is an invalid-argument error; "
        "no match is a stream-not-found error. PSMF and PAMF paths differ "
        "slightly in how the index is stored. Do not copy that body; "
        "reimplement from this description and a same-file RPCS3 log. "
        "Cite: rpcs3/Emu/Cell/Modules/cellPamf.cpp:969.",
}

OBJECT_PARAM_NAMES = {
    "pself", "self", "pthis", "this", "pplayer", "player",
    "pdescriptor", "descriptor", "pdesc", "desc", "preader", "reader",
    "padapter", "adapter", "phandle_obj",
}

OUTPUT_NAME_RE = re.compile(
    r"^(p|pp)?(out|output|result|retval|ret|dst|dest|handle|phandle|"
    r"value|size|sizekb|type|attributes|config|info|state|count|"
    r"num|number|portnum|eventq|queuekey|buf|buffer)s?$",
    re.I,
)
INPUT_NAME_RE = re.compile(
    r"^(p|pp)?(param|params|attr|attribute|attributes|resource|src|source|"
    r"in|input|arg|args|cb|callback|funcs|command|path|uri|name|dirname|"
    r"filename|usrdirpath)$",
    re.I,
)
GET_LIKE_RE = re.compile(
    r"(Get|Is|Query|Check|BootCheck|DataCheck)",
)
SET_LIKE_RE = re.compile(
    r"(Set|Add|Send|Write|Update|Register|Put|Select|Remove|Delete)",
)
C_KEYWORDS = {
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if",
    "inline", "int", "long", "register", "restrict", "return", "short",
    "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
    "unsigned", "void", "volatile", "while", "asm", "__asm__", "__inline__",
    "__volatile__", "bool", "true", "false", "nullptr",
}

DEFAULT_PSL1GHT_CANDIDATES = [
    # Optional local checkouts; pass --psl1ght to set one explicitly.
]
DEFAULT_NIDS_TXT_CANDIDATES = [
    # Optional. Do not vendor nids.txt into this tree. Pass --nids-txt if you have one.
]
DEFAULT_RPCS3_CANDIDATES = [
    # Optional behavioural reference only. Pass --rpcs3. No RPCS3/GPL code is included here.
]
DEFAULT_PS3RECOMP_CANDIDATES = [
    # Optional. Pass --ps3recomp pointing at your own checkout.
]


def compute_nid(name: str, suffix: bytes = NID_SUFFIX) -> int:
    digest = hashlib.sha1(name.encode("utf-8") + suffix).digest()
    return struct.unpack("<I", digest[:4])[0]


def fmt_nid(nid: int) -> str:
    return f"0x{nid:08X}"


def parse_nid(text: str) -> int:
    text = text.strip()
    if text.lower().startswith("nid="):
        text = text.split("=", 1)[1]
    return int(text, 16) if text.lower().startswith("0x") else int(text, 0)


def verify_builtin_names() -> None:
    bad = []
    for nid, (_lib, name) in VERIFIED_NAMES.items():
        got = compute_nid(name)
        if got != nid:
            bad.append(f"{fmt_nid(nid)} {name} computed {fmt_nid(got)}")
    if bad:
        raise RuntimeError("VERIFIED_NAMES failed SHA-1 check: " + "; ".join(bad))


def lib_from_name(name: str) -> str:
    for prefix, lib in (
        ("cellSail", "cellSail"),
        ("cellPamf", "cellPamf"),
        ("sceNpTus", "sceNpTus"),
        ("sceNp2", "sceNp2"),
        ("sceNp", "sceNp"),
        ("cellSysutilAvc2", "cellSysutilAvc2"),
        ("cellSysutil", "cellSysutil"),
        ("cellOsk", "cellOskExtUtility"),
        ("cellGame", "cellGame"),
        ("cellGcm", "cellGcmSys"),
        ("cellFs", "sys_fs"),
        ("cellPad", "sys_io"),
        ("cellKb", "sys_io"),
        ("cellResc", "cellResc"),
        ("cellSpurs", "cellSpurs"),
        ("cellAtrac", "cellAtrac"),
        ("cellL10n", "cellL10n"),
        ("sys_net", "sys_net"),
        ("sys_fs", "sys_fs"),
        ("sys_", "sysPrxForUser"),
    ):
        if name.startswith(prefix):
            return lib
    return "unknown"

@dataclass
class FirstDump:
    tid: int | None = None
    lr: int | None = None
    sp: int | None = None
    regs: dict[str, int] = field(default_factory=dict)


@dataclass
class UnresolvedHit:
    nid: int
    hits: int = 0
    count_complete: bool = False
    lib: str = ""
    name_in_log: str = ""
    fake: str = ""
    first: FirstDump = field(default_factory=FirstDump)
    sources: list[str] = field(default_factory=list)
    call_lines: int = 0
    summary_hits: int | None = None
    firsthit_seen: bool = False
    running_hits: list[int] = field(default_factory=list)

    def finalize(self) -> None:
        if self.summary_hits is not None:
            self.hits = self.summary_hits
            self.count_complete = True
            return
        if self.running_hits:
            if all(h == 1 for h in self.running_hits):
                self.hits = len(self.running_hits)
            else:
                self.hits = max(max(self.running_hits), len(self.running_hits))
            self.count_complete = True
            return
        if self.firsthit_seen:
            self.hits = max(self.hits, 1)
            self.count_complete = False
            return
        self.count_complete = False


def _bucket(table: dict[int, UnresolvedHit], nid: int) -> UnresolvedHit:
    rec = table.get(nid)
    if rec is None:
        rec = UnresolvedHit(nid=nid)
        table[nid] = rec
    return rec


def _apply_regs(dump: FirstDump, pairs: Iterable[tuple[str, int]]) -> None:
    if dump.regs and all(k in dump.regs for k, _v in pairs):
        return
    for k, v in pairs:
        dump.regs.setdefault(k, v)


def parse_log_text(text: str, source: str = "log") -> dict[int, UnresolvedHit]:
    table: dict[int, UnresolvedHit] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = RX_SUMMARY.match(line)
        if m:
            rec = _bucket(table, int(m.group(1), 16))
            rec.summary_hits = int(m.group(2))
            if m.group(3) and not rec.lib:
                rec.lib = m.group(3)
            if m.group(4) and not rec.name_in_log:
                rec.name_in_log = m.group(4)
            rec.sources.append(source + ":summary")
            continue
        m = RX_CALL.match(line)
        if m:
            rec = _bucket(table, int(m.group(1), 16))
            rec.call_lines += 1
            if m.group(2) and not rec.lib:
                rec.lib = m.group(2)
            if m.group(3) and not rec.name_in_log:
                rec.name_in_log = m.group(3)
            if m.group(4):
                rec.running_hits.append(int(m.group(4)))
            else:
                rec.running_hits.append(1)
            if m.group(5) and rec.first.tid is None:
                rec.first.tid = int(m.group(5))
            if m.group(6) and rec.first.lr is None:
                rec.first.lr = int(m.group(6), 16)
            tail = m.group(7) or ""
            if not rec.first.regs:
                rec.first.regs = {k: int(v, 16) for k, v in RX_KV_REG.findall(tail)}
            rec.sources.append(source + ":call")
            continue
        m = RX_FIRSTHIT.search(line)
        if m:
            rec = _bucket(table, int(m.group(1), 16))
            rec.firsthit_seen = True
            rec.fake = m.group(2)
            rec.sources.append(source + ":firsthit")
            continue
        m = RX_DUMP_R3.search(line)
        if m:
            rec = _bucket(table, int(m.group(1), 16))
            if rec.first.tid is None:
                rec.first.tid = int(m.group(2))
            _apply_regs(rec.first, [
                ("r3", int(m.group(3), 16)),
                ("r4", int(m.group(4), 16)),
                ("r5", int(m.group(5), 16)),
                ("r6", int(m.group(6), 16)),
            ])
            continue
        m = RX_DUMP_R7.search(line)
        if m:
            rec = _bucket(table, int(m.group(1), 16))
            _apply_regs(rec.first, [
                ("r7", int(m.group(2), 16)),
                ("r8", int(m.group(3), 16)),
                ("r9", int(m.group(4), 16)),
                ("r10", int(m.group(5), 16)),
            ])
            continue
        m = RX_DUMP_SP.search(line)
        if m:
            rec = _bucket(table, int(m.group(1), 16))
            if rec.first.sp is None:
                rec.first.sp = int(m.group(2), 16)
            if rec.first.lr is None:
                rec.first.lr = int(m.group(3), 16)
            continue
        m = RX_DUMP_ARG9.search(line)
        if m:
            rec = _bucket(table, int(m.group(1), 16))
            if "arg9" not in rec.first.regs:
                rec.first.regs["arg9"] = int(m.group(2), 16)
                rec.first.regs["arg10"] = int(m.group(3), 16)
                rec.first.regs["arg11"] = int(m.group(4), 16)
                rec.first.regs["arg12"] = int(m.group(5), 16)
            continue
        m = RX_NID_HITS.search(line)
        if m and "UNRESOLVED" not in line:
            rec = _bucket(table, int(m.group(1), 16))
            rec.summary_hits = max(rec.summary_hits or 0, int(m.group(2)))
            rec.sources.append(source + ":hits-line")
            continue
        m = RX_IMPORT_LINE.match(line)
        if m and "?" not in (m.group("name") or ""):
            rec = _bucket(table, int(m.group("nid"), 16))
            if m.group("lib") and not rec.lib:
                rec.lib = m.group("lib")
            if m.group("name") and m.group("name") != "?" and not rec.name_in_log:
                rec.name_in_log = m.group("name")
            rec.sources.append(source + ":import-list")
            continue
        m2 = re.match(r"^(?P<lib>[A-Za-z_]\w*)\s+0x(?P<nid>[0-9A-Fa-f]{8})\s+\?", line)
        if m2:
            rec = _bucket(table, int(m2.group("nid"), 16))
            if not rec.lib:
                rec.lib = m2.group("lib")
            rec.sources.append(source + ":import-list")
    for rec in table.values():
        rec.finalize()
    return table


def parse_findings_json(path: Path) -> dict[int, UnresolvedHit]:
    data = json.loads(path.read_text(encoding="utf-8"))
    table: dict[int, UnresolvedHit] = {}
    nids = data.get("unresolved_nids") or []
    ctx = data.get("unresolved_ctx") or {}
    for item in nids:
        nid = parse_nid(str(item))
        rec = _bucket(table, nid)
        rec.firsthit_seen = True
        rec.sources.append(str(path) + ":findings")
        lr = ctx.get(str(item)) or ctx.get(fmt_nid(nid)) or ctx.get(fmt_nid(nid).lower())
        if lr and rec.first.lr is None:
            rec.first.lr = parse_nid(str(lr))
    for k, lr in ctx.items():
        try:
            nid = parse_nid(str(k))
        except ValueError:
            continue
        rec = _bucket(table, nid)
        rec.firsthit_seen = True
        if rec.first.lr is None:
            rec.first.lr = parse_nid(str(lr))
        rec.sources.append(str(path) + ":findings-ctx")
    for rec in table.values():
        rec.finalize()
    return table


def parse_input_path(path: Path) -> dict[int, UnresolvedHit]:
    if path.suffix.lower() == ".json":
        return parse_findings_json(path)
    return parse_log_text(path.read_text(encoding="utf-8", errors="replace"), str(path))


def merge_hits(dst: dict[int, UnresolvedHit], src: dict[int, UnresolvedHit]) -> None:
    for nid, rec in src.items():
        if nid not in dst:
            dst[nid] = rec
            continue
        a = dst[nid]
        a.hits = max(a.hits, rec.hits)
        a.count_complete = a.count_complete or rec.count_complete
        a.lib = a.lib or rec.lib
        a.name_in_log = a.name_in_log or rec.name_in_log
        a.fake = a.fake or rec.fake
        a.firsthit_seen = a.firsthit_seen or rec.firsthit_seen
        a.call_lines += rec.call_lines
        a.running_hits.extend(rec.running_hits)
        if a.summary_hits is None:
            a.summary_hits = rec.summary_hits
        elif rec.summary_hits is not None:
            a.summary_hits = max(a.summary_hits, rec.summary_hits)
        a.sources.extend(rec.sources)
        if a.first.tid is None:
            a.first.tid = rec.first.tid
        if a.first.lr is None:
            a.first.lr = rec.first.lr
        if a.first.sp is None:
            a.first.sp = rec.first.sp
        if not a.first.regs:
            a.first.regs = dict(rec.first.regs)
        a.finalize()


def ranked(table: dict[int, UnresolvedHit]) -> list[UnresolvedHit]:
    return sorted(table.values(), key=lambda r: (-r.hits, r.nid))

@dataclass
class NameHit:
    nid: int
    name: str
    lib: str
    source: str
    verified: bool


def load_name_list(paths: list[Path]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if not path or not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line and line.lower().startswith("0x"):
                _, name = line.split("=", 1)
                name = name.strip()
            else:
                parts = line.split()
                if len(parts) >= 2 and re.match(r"0x[0-9A-Fa-f]{8}$", parts[0]):
                    name = parts[1]
                elif len(parts) >= 3 and re.match(r"0x[0-9A-Fa-f]{8}$", parts[1]):
                    name = parts[2]
                else:
                    name = parts[-1]
            name = name.strip().strip(",")
            if name in ("?", "OK", "MISMATCH") or not re.match(r"^[A-Za-z_]\w*$", name):
                continue
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def harvest_header_names(roots: list[Path]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for root in roots:
        if not root:
            continue
        base = root / "ppu" / "include" if (root / "ppu" / "include").is_dir() else root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix.lower() not in {".h", ".hpp", ".c"}:
                continue
            try:
                text = path.read_text(encoding="latin-1")
            except OSError:
                continue
            for m in re.finditer(
                r"\b((?:cell|sce|sys|audio|pad|kb|mouse|gcm)[A-Za-z_]\w*)\s*\(",
                text,
            ):
                n = m.group(1)
                if n not in seen and n not in C_KEYWORDS:
                    seen.add(n)
                    names.append(n)
    return names


def load_nids_txt(path: Path) -> dict[int, str]:
    """Lookup map from a nids.txt. Do not copy this file into the port."""
    out: dict[int, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"0x([0-9A-Fa-f]{8})\s+(\S+)", line)
        if not m:
            continue
        out[int(m.group(1), 16)] = m.group(2)
    return out


def resolve_name(
    nid: int,
    candidates: list[str],
    nids_map: dict[int, str] | None,
    log_name: str = "",
    log_lib: str = "",
) -> NameHit:
    tried: list[str] = []
    if log_name and re.match(r"^[A-Za-z_]\w*$", log_name) and log_name != "?":
        tried.append(log_name)
    for name in candidates:
        if name not in tried:
            tried.append(name)
    for name in tried:
        if compute_nid(name) == nid:
            lib = log_lib or lib_from_name(name)
            source = "sha1-candidates"
            if name == log_name:
                source = "sha1-log-name"
            elif name in {v[1] for v in VERIFIED_NAMES.values()}:
                source = "sha1-verified-list"
            return NameHit(nid, name, lib, source, verified=True)
    if nids_map and nid in nids_map:
        name = nids_map[nid]
        if compute_nid(name) == nid:
            return NameHit(nid, name, log_lib or lib_from_name(name),
                           "nids.txt+sha1-verified", verified=True)
        return NameHit(
            nid, "", log_lib,
            f"nids.txt-MISMATCH (said {name}, hash {fmt_nid(compute_nid(name))})",
            verified=False,
        )
    return NameHit(nid, "", log_lib, "unresolved", verified=False)


@dataclass
class Param:
    raw: str
    type: str
    name: str
    is_pointer: bool
    is_const: bool
    direction: str
    confidence: str
    reason: str


@dataclass
class Prototype:
    name: str
    return_type: str
    params: list[Param]
    raw: str
    source_file: str
    source_kind: str
    found: bool


def strip_c_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//.*?$", " ", text, flags=re.M)
    return text


def _split_params(param_src: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in param_src:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def parse_param(raw: str, index: int) -> Param:
    s = " ".join(raw.strip().split())
    if s in ("", "void"):
        return Param(raw=s, type="void", name="", is_pointer=False,
                     is_const=False, direction="none", confidence="KNOWN",
                     reason="no parameter")
    fp = re.match(r"^(?P<t>.*?)\(\s*\*\s*(?P<n>[A-Za-z_]\w*)\s*\)(?P<a>\(.*\))$", s)
    if fp:
        return Param(
            raw=s, type=(fp.group("t") + "(*)" + fp.group("a")).strip(),
            name=fp.group("n"), is_pointer=False, is_const=False,
            direction="input", confidence="ASSUMED",
            reason="function pointer passed by value, treated as input",
        )
    is_const = bool(re.search(r"\bconst\b", s))
    is_pointer = "*" in s or "[" in s
    m = re.match(r"^(?P<t>.*?)(?P<n>[A-Za-z_]\w*)\s*(?:\[\s*\d*\s*\])?$", s)
    if m and m.group("n") not in C_KEYWORDS:
        typ, name = m.group("t").strip(), m.group("n")
    else:
        typ, name = s, f"arg{index}"
    typ = typ.strip() or "s32"
    return Param(
        raw=s, type=typ, name=name, is_pointer=is_pointer, is_const=is_const,
        direction="input", confidence="KNOWN", reason="pending",
    )


def classify_param(fn_name: str, param: Param, index: int, nparams: int) -> Param:
    if param.direction == "none" or not param.name and param.type == "void":
        param.confidence = "KNOWN"
        param.reason = "no parameter"
        return param
    if not param.is_pointer:
        param.direction = "input"
        param.confidence = "KNOWN"
        param.reason = "scalar / passed by value"
        return param
    if param.is_const:
        param.direction = "input"
        param.confidence = "KNOWN"
        param.reason = "const pointer (input)"
        return param
    lname = param.name.lower().lstrip("_")
    if lname in OBJECT_PARAM_NAMES or (index == 0 and lname in {
        "pcontext", "ctx", "pmutex", "mutex",
    }):
        param.direction = "in-out"
        param.confidence = "ASSUMED"
        param.reason = "object / self pointer (do not zero the object)"
        return param
    if GET_LIKE_RE.search(fn_name) and not SET_LIKE_RE.search(fn_name):
        param.direction = "output"
        param.confidence = "ASSUMED"
        param.reason = f"non-const pointer on a Get/Check-like name ({fn_name})"
        return param
    if OUTPUT_NAME_RE.match(lname) or "out" in lname:
        param.direction = "output"
        param.confidence = "ASSUMED"
        param.reason = f"non-const pointer named '{param.name}' looks like an out-param"
        return param
    if INPUT_NAME_RE.match(lname):
        param.direction = "input"
        param.confidence = "ASSUMED"
        param.reason = f"non-const pointer named '{param.name}' looks like an in-param"
        return param
    if SET_LIKE_RE.search(fn_name):
        param.direction = "input"
        param.confidence = "ASSUMED"
        param.reason = f"non-const pointer on a Set/Add-like name ({fn_name})"
        return param
    param.direction = "in-out"
    param.confidence = "ASSUMED"
    param.reason = "non-const pointer, direction unclear; not zeroed"
    return param


def parse_prototype_text(decl: str, source_file: str, source_kind: str) -> Prototype | None:
    s = " ".join(strip_c_comments(decl).split())
    s = s.rstrip(";")
    m = re.match(
        r"^(?P<ret>[\w\s\*]+?)\b(?P<name>[A-Za-z_]\w*)\s*\((?P<params>.*)\)\s*$",
        s,
    )
    if not m:
        return None
    name = m.group("name")
    if name in C_KEYWORDS:
        return None
    ret = m.group("ret").strip()
    raw_params = m.group("params").strip()
    bits = _split_params(raw_params) if raw_params else []
    if bits == ["void"] or bits == [""]:
        bits = []
    params = [classify_param(name, parse_param(b, i), i, len(bits))
              for i, b in enumerate(bits)]
    return Prototype(
        name=name, return_type=ret or "s32", params=params, raw=s + ";",
        source_file=source_file, source_kind=source_kind, found=True,
    )

def iter_header_decls(text: str) -> list[tuple[str, int]]:
    cleaned = strip_c_comments(text)
    decls: list[tuple[str, int]] = []
    rx = re.compile(
        r"^(?P<decl>(?:extern\s+)?(?:(?:unsigned|signed|const|volatile|struct|enum|union|"
        r"s32|s64|u32|u64|u8|s8|f32|int|void|char|short|long|uint32_t|int32_t|"
        r"uint64_t|int64_t|uint8_t|bool|size_t|sys\w+|cell\w+|audio\w+|Cell\w+)\s+)+\*?\s*"
        r"(?P<name>[A-Za-z_]\w*)\s*\([^;]*\))\s*;",
        re.M,
    )
    for m in rx.finditer(cleaned):
        name = m.group("name")
        if name in C_KEYWORDS:
            continue
        line = cleaned[: m.start()].count("\n") + 1
        decls.append((m.group("decl"), line))
    return decls


class HeaderIndex:
    def __init__(self) -> None:
        self.by_name: dict[str, Prototype] = {}

    def add_root(self, root: Path, kind: str) -> int:
        added = 0
        include = root / "ppu" / "include"
        search = include if include.is_dir() else root
        if not search.exists():
            return 0
        for path in search.rglob("*"):
            if path.suffix.lower() not in {".h", ".hpp"}:
                continue
            try:
                text = path.read_text(encoding="latin-1")
            except OSError:
                continue
            rel = str(path)
            for decl, line in iter_header_decls(text):
                proto = parse_prototype_text(decl, f"{rel}:{line}", kind)
                if proto and proto.name not in self.by_name:
                    self.by_name[proto.name] = proto
                    added += 1
        return added

    def find(self, name: str) -> Prototype | None:
        return self.by_name.get(name)


def assumed_prototype(name: str) -> Prototype | None:
    decl = ASSUMED_PROTOS.get(name)
    if not decl:
        if name.endswith("Close") or name.endswith("Destroy") or name.endswith("End"):
            decl = f"s32 {name}(void* pSelf)"
        else:
            return None
    proto = parse_prototype_text(decl, "ASSUMED_PROTOS table (not PSL1GHT)",
                                 "assumed-heuristic")
    if proto:
        for p in proto.params:
            if p.confidence == "KNOWN" and p.is_pointer:
                p.confidence = "ASSUMED"
                p.reason += " [signature itself is ASSUMED]"
            elif p.confidence == "KNOWN" and not p.is_pointer:
                p.confidence = "ASSUMED"
                p.reason = "scalar in an ASSUMED signature"
    return proto


def missing_prototype(name: str) -> Prototype:
    return Prototype(
        name=name, return_type="s32", params=[],
        raw="", source_file="", source_kind="missing", found=False,
    )


def scan_rpcs3_note(rpcs3_root: Path | None, name: str) -> str:
    if name in RPCS3_NOTES:
        return RPCS3_NOTES[name]
    if not rpcs3_root:
        return (
            "No canned note and no --rpcs3 tree. Look the name up in "
            "rpcs3/Emu/Cell/Modules/ and summarise the behaviour in your "
            "own words. Do not copy GPL code."
        )
    modules = rpcs3_root / "rpcs3" / "Emu" / "Cell" / "Modules"
    search_dirs = [modules] if modules.is_dir() else [rpcs3_root]
    rx_def = re.compile(
        rf"^\s*(?:error_code|s32|int|u32|uint32_t|void)\s+{re.escape(name)}\s*\(",
        re.M,
    )
    for d in search_dirs:
        if not d.exists():
            continue
        for path in sorted(d.glob("*.cpp")):
            try:
                text = path.read_text(encoding="latin-1")
            except OSError:
                continue
            m = rx_def.search(text)
            if not m:
                continue
            line = text[: m.start()].count("\n") + 1
            window = text[m.start(): m.start() + 800]
            rel = path.as_posix()
            if "Modules/" in rel:
                rel = "rpcs3/Emu/Cell/Modules/" + rel.split("Modules/", 1)[1]
            if "UNIMPLEMENTED_FUNC" in window:
                return (
                    f"Unimplemented stub at {rel}:{line}: the reference logs "
                    f"that the call is unfinished and (typically) returns "
                    f"success. Confirm in a same-call log. Do not copy the body."
                )
            if ".todo(" in window and re.search(r"return\s+CELL_OK", window):
                return (
                    f"Logged as a TODO at {rel}:{line} and appears to "
                    f"return success without a full implementation. "
                    f"Confirm against a same-call log. Do not copy the body."
                )
            return (
                f"A definition exists at {rel}:{line}. Read it as a behaviour "
                f"reference only, summarise in your own words, and reimplement. "
                f"Do not copy GPL code."
            )
    return (
        f"No definition of {name} was found under the RPCS3 tree. "
        "Search rpcs3/Emu/Cell/Modules/ by NID if the name is new."
    )


def c_ident(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name) or "arg"


def short_log_name(fn: str) -> str:
    for p in ("cellSail", "cellPamf", "sceNpBasic", "sceNp", "cell", "sce", "sys"):
        if fn.startswith(p) and len(fn) > len(p):
            return fn[len(p):]
    return fn


def guest_width(typ: str) -> int:
    t = typ.replace("const", " ").replace("*", " ")
    t = " ".join(t.split())
    if any(x in t for x in ("u64", "s64", "uint64", "int64", "f64", "double")):
        return 8
    if any(x in t for x in ("u8", "s8", "char", "int8", "uint8")):
        return 1
    if any(x in t for x in ("u16", "s16", "short", "int16", "uint16")):
        return 2
    return 4

def generate_skeleton(
    nid: int,
    hit: NameHit,
    proto: Prototype,
    note: str,
    first: FirstDump | None = None,
    hits: int = 0,
    count_complete: bool = False,
) -> str:
    lib = hit.lib or lib_from_name(hit.name or "unknown")
    fn = hit.name or f"fn_{nid:08X}"
    use_ctx = (not proto.found) or proto.source_kind == "missing"

    lines: list[str] = []
    lines.append(f"/* NID {fmt_nid(nid)}  {fn}")
    lines.append(f" * name source : {hit.source}" + (" (SHA-1 verified)" if hit.verified else ""))
    if proto.found:
        lines.append(f" * prototype   : {proto.raw}")
        lines.append(f" * proto source: {proto.source_kind} ({proto.source_file})")
    else:
        lines.append(" * prototype   : NOT FOUND in PSL1GHT (or fallback headers).")
        lines.append(" *               Emitting a ctx stub that logs r3-r10.")
    lines.append(f" * TODO RPCS3  : {note}")
    count_s = str(hits) if count_complete else f"{hits}+ (count incomplete; first-hit log only)"
    lines.append(f" * observed    : hits={count_s}")
    if first and first.lr is not None:
        lines.append(f" * first lr    : {fmt_nid(first.lr)}  tid={first.tid}")
    lines.append(" *")
    lines.append(" * AUTO-GENERATED SKELETON — not an implementation.")
    lines.append(" * Do not register this in a release build until a human has")
    lines.append(" * filled in real behaviour and compared a same-call RPCS3 log.")
    lines.append(" * No GPL code was copied.")
    lines.append(" */")

    if use_ctx or not hit.name:
        lines.append(f"static void hle_{c_ident(fn)}(ppu_context* ctx)")
        lines.append("{")
        lines.append(f'    printf("[{lib}] {short_log_name(fn)}(untyped) "')
        lines.append('           "r3=%08X r4=%08X r5=%08X r6=%08X "')
        lines.append('           "r7=%08X r8=%08X r9=%08X r10=%08X\\n",')
        lines.append("           (u32)ctx->gpr[3], (u32)ctx->gpr[4],")
        lines.append("           (u32)ctx->gpr[5], (u32)ctx->gpr[6],")
        lines.append("           (u32)ctx->gpr[7], (u32)ctx->gpr[8],")
        lines.append("           (u32)ctx->gpr[9], (u32)ctx->gpr[10]);")
        lines.append("    /* No output params are known, so none are zeroed.")
        lines.append("     * If a later prototype shows an out-pointer in rN,")
        lines.append("     * write a zero (vm_write32) to that guest EA. */")
        lines.append("    ctx->gpr[3] = (u64)(u32)CELL_OK;")
        lines.append("}")
        return "\n".join(lines) + "\n"

    c_params: list[str] = []
    printf_fmt: list[str] = []
    printf_args: list[str] = []
    decl_names: list[str] = []
    for i, p in enumerate(proto.params):
        pname = c_ident(p.name or f"arg{i}")
        decl_names.append(pname)
        if p.is_pointer:
            c_params.append(f"u32 {pname}")
            printf_fmt.append(f"{p.name}=0x%08X")
            printf_args.append(pname)
        else:
            typ = p.type.strip() or "s32"
            if typ not in {"s32", "u32", "s16", "u16", "s8", "u8", "s64", "u64",
                           "int", "unsigned", "char", "b8", "f32", "f64"}:
                typ = "s32"
            c_params.append(f"{typ} {pname}")
            if typ in {"s64", "u64"}:
                printf_fmt.append(f"{p.name}=%lld")
                printf_args.append(f"(long long){pname}")
            else:
                printf_fmt.append(f"{p.name}=%d")
                printf_args.append(f"(int){pname}")

    sig_params = ", ".join(c_params) if c_params else "void"
    lines.append(f"s32 {fn}({sig_params})")
    lines.append("{")
    fmt = ", ".join(printf_fmt) if printf_fmt else "void"
    if printf_args:
        lines.append(f'    printf("[{lib}] {short_log_name(fn)}({fmt})\\n",')
        lines.append("           " + ", ".join(printf_args) + ");")
    else:
        lines.append(f'    printf("[{lib}] {short_log_name(fn)}()\\n");')

    any_out = False
    for i, p in enumerate(proto.params):
        pname = decl_names[i]
        tag = f"{p.direction} {p.confidence}"
        if p.direction == "output" and p.is_pointer:
            any_out = True
            width = guest_width(p.type)
            lines.append(f"    /* {pname}: {tag} — {p.reason} */")
            lines.append(f"    if ({pname}) {{")
            if width == 8:
                lines.append(f"        vm_write64({pname}, 0);")
            elif width == 1:
                lines.append(f"        vm_write8({pname}, 0);")
            elif width == 2:
                lines.append(f"        vm_write16({pname}, 0);")
            else:
                lines.append(f"        vm_write32({pname}, 0);")
                if "struct" in p.type or (p.type and p.type[:1].isupper()):
                    lines.append("        /* ASSUMED size: only the first 4 bytes were")
                    lines.append("         * cleared. Confirm the struct size and zero")
                    lines.append(f"         * the rest (see {p.type}). */")
            lines.append("    }")
        else:
            lines.append(f"    /* {pname}: {tag} — {p.reason} */")
            if p.direction == "in-out" and p.is_pointer:
                lines.append(f"    (void){pname}; /* do not zero the object */")
            elif not p.is_pointer:
                lines.append(f"    (void){pname};")
    if not any_out:
        lines.append("    /* No classified output pointers to initialise. */")
    lines.append("    return CELL_OK;")
    lines.append("}")
    lines.append("")
    lines.append(f"static void hle_{c_ident(fn)}(ppu_context* ctx)")
    lines.append("{")
    args = []
    simple = {"s32", "u32", "s16", "u16", "s8", "u8", "s64", "u64", "b8"}
    for i, p in enumerate(proto.params):
        if i < 8:
            reg = f"ctx->gpr[{3+i}]"
        else:
            reg = f"/* arg{i+1} lives at SP+112+{(i-8)*8}; fill me */ 0"
        typ = "u32" if p.is_pointer else (p.type.strip() if p.type.strip() in simple else "s32")
        args.append(f"({typ}){reg}")
    call = ", ".join(args)
    lines.append(f"    ctx->gpr[3] = (u64)(u32){fn}({call});")
    lines.append("}")
    return "\n".join(lines) + "\n"


def generate_register_inc(entries: list[tuple[int, NameHit]]) -> str:
    lines = [
        "/* AUTO-GENERATED registration thunks. Review before including.",
        " * Style matches port strikeforce_sail.inc (ps3_hle_register_ctx).",
        " * Rename the [skel] suffix once the body is a real implementation.",
        " */",
        "",
    ]
    for nid, hit in entries:
        if not hit.name:
            lines.append(f"/* {fmt_nid(nid)} still unnamed — no registration emitted. */")
            continue
        fn = hit.name
        lines.append(
            f'ps3_hle_register_ctx({fmt_nid(nid)}u, "{fn}[skel]", hle_{c_ident(fn)});'
        )
    lines.append("")
    return "\n".join(lines)


def generate_checklist(entries: list[dict[str, Any]]) -> str:
    blocks = [
        "# Auto-wire test checklist",
        "",
        "Each skeleton returns `CELL_OK` and at most zeroes classified",
        "output parameters. That is **not** enough to land the handler.",
        "Compare one real call in the port against the **same call** in",
        "RPCS3 (same boot / same `.pam` / same menu path).",
        "",
        "How to get an RPCS3 log: raise the `cellSail` / `cellPamf` /",
        "`sceNp` log level, run to the same point, and grep the function",
        "name. The port should emit the `UNRESOLVED CALL` / `SUMMARY`",
        "lines (or, after the handler is registered, the `printf` from",
        "the skeleton).",
        "",
        "Do not copy RPCS3 source into the port.",
        "",
    ]
    for e in entries:
        nid = e["nid"]
        name = e.get("name") or "(unnamed)"
        lib = e.get("lib") or ""
        blocks.append(f"## {nid}  {name}")
        blocks.append("")
        blocks.append(f"- Library: `{lib}`")
        blocks.append(f"- Name source: {e.get('name_source')}  verified={e.get('verified')}")
        blocks.append(f"- Hits in the input log: {e.get('hits')}  complete={e.get('count_complete')}")
        if e.get("lr"):
            blocks.append(f"- First-hit LR (port): `{e['lr']}`  tid={e.get('tid')}")
        blocks.append(f"- Prototype: {e.get('proto_source')}")
        if e.get("proto"):
            blocks.append(f"  `{e['proto']}`")
        if e.get("params"):
            blocks.append("- Parameters:")
            for p in e["params"]:
                blocks.append(
                    f"  - `{p['name']}`: {p['direction']} {p['confidence']}"
                    f" — {p['reason']}"
                )
        blocks.append(f"- RPCS3 note: {e.get('rpcs3_note')}")
        blocks.append("")
        blocks.append("Checks:")
        blocks.append("1. Return value (r3 / error code) matches RPCS3 for a")
        blocks.append("   successful path **and** for at least one failure path")
        blocks.append("   (NULL self, bad index) if the reference fails those.")
        blocks.append("2. Every out-param / guest struct field the title reads")
        blocks.append("   after the call matches RPCS3 (not just 'we wrote 0').")
        blocks.append("3. The next HLE calls in both logs are the same set, in")
        blocks.append("   a reasonable order (a fake CELL_OK often skips a path")
        blocks.append("   or lets the title walk off into the next call too soon).")
        blocks.append("4. Argument values in the port CALL line (r3-r10) line up")
        blocks.append("   with the arguments RPCS3 logged for the same call.")
        blocks.append("5. Play the same scene / boot path on both; note whether")
        blocks.append("   the title continues, errors, or hangs.")
        blocks.append("6. Keep the handler unregistered (or behind a knob) until")
        blocks.append("   those checks pass or a real implementation is written.")
        blocks.append("")
    return "\n".join(blocks)

def first_existing(paths: Iterable[Path | None]) -> Path | None:
    for p in paths:
        if p and Path(p).exists():
            return Path(p)
    return None


def fetch_psl1ght(dest: Path) -> Path:
    dest = dest.resolve()
    if (dest / "ppu" / "include").is_dir():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = "https://github.com/ps3dev/PSL1GHT.git"
    print(f"cloning {url} -> {dest} (MIT, headers only needed)", file=sys.stderr)
    import subprocess
    subprocess.check_call(["git", "clone", "--depth", "1", url, str(dest)])
    return dest


@dataclass
class WireResult:
    nid: int
    hit: UnresolvedHit
    name: NameHit
    proto: Prototype
    note: str
    skeleton: str


def run_pipeline(
    table: dict[int, UnresolvedHit],
    candidates: list[str],
    nids_map: dict[int, str] | None,
    psl1ght_index: HeaderIndex,
    fallback_index: HeaderIndex | None,
    rpcs3_root: Path | None,
) -> list[WireResult]:
    out: list[WireResult] = []
    for rec in ranked(table):
        name = resolve_name(rec.nid, candidates, nids_map, rec.name_in_log, rec.lib)
        proto = missing_prototype(name.name or f"fn_{rec.nid:08X}")
        if name.name:
            proto = (
                psl1ght_index.find(name.name)
                or (fallback_index.find(name.name) if fallback_index else None)
                or assumed_prototype(name.name)
                or missing_prototype(name.name)
            )
        if not name.lib and name.name:
            name.lib = lib_from_name(name.name)
        if not name.lib:
            name.lib = rec.lib
        note = scan_rpcs3_note(rpcs3_root, name.name) if name.name else (
            "Name unresolved; cannot look up RPCS3 behaviour yet."
        )
        skel = generate_skeleton(
            rec.nid, name, proto, note, rec.first, rec.hits, rec.count_complete,
        )
        out.append(WireResult(rec.nid, rec, name, proto, note, skel))
    return out


def write_outputs(results: list[WireResult], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    banner = textwrap.dedent("""\
        /*
         * AUTO-GENERATED by auto_nid_wire.py. Not an implementation.
         * Review every TODO, fill in behaviour, compare against RPCS3.
         * No GPL code was copied. Do not vendor nids.txt.
         */
        #include <stdio.h>
        #include <string.h>
        /* Adjust these includes to the port's tree. */
        #include "ps3emu/guest_call.h"
        #include "../../runtime/ppu/ppu_memory.h"  /* vm_write32 / vm_write64 */

        #ifndef CELL_OK
        #define CELL_OK 0
        #endif

        """)
    (out_dir / "skeletons.c").write_text(
        banner + "\n\n".join(r.skeleton for r in results), encoding="utf-8"
    )
    (out_dir / "register.inc").write_text(
        generate_register_inc([(r.nid, r.name) for r in results]),
        encoding="utf-8",
    )
    report = []
    checklist_entries = []
    ranked_lines = ["# nid  hits  complete  lib  name  name_source  proto_source", ""]
    for r in results:
        rec = r.hit
        entry = {
            "nid": fmt_nid(r.nid),
            "hits": rec.hits,
            "count_complete": rec.count_complete,
            "lib": r.name.lib,
            "name": r.name.name,
            "name_source": r.name.source,
            "verified": r.name.verified,
            "lr": fmt_nid(rec.first.lr) if rec.first.lr is not None else None,
            "tid": rec.first.tid,
            "regs": {k: fmt_nid(v) if v > 0xFFFF else hex(v) for k, v in rec.first.regs.items()},
            "proto": r.proto.raw if r.proto.found else None,
            "proto_source": f"{r.proto.source_kind}:{r.proto.source_file}" if r.proto.found else "missing",
            "params": [
                {
                    "name": p.name,
                    "type": p.type,
                    "direction": p.direction,
                    "confidence": p.confidence,
                    "reason": p.reason,
                }
                for p in r.proto.params
            ],
            "rpcs3_note": r.note,
        }
        report.append(entry)
        checklist_entries.append(entry)
        ranked_lines.append(
            f"{fmt_nid(r.nid):12} {rec.hits:6}  {str(rec.count_complete):5}  "
            f"{r.name.lib or '-':16} {r.name.name or '?':48} "
            f"{r.name.source:24} {entry['proto_source']}"
        )
    (out_dir / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "unresolved_ranked.txt").write_text(
        "\n".join(ranked_lines) + "\n", encoding="utf-8"
    )
    (out_dir / "checklist.md").write_text(
        generate_checklist(checklist_entries), encoding="utf-8"
    )

def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def run_self_test(repo_tool_dir: Path) -> int:
    verify_builtin_names()
    testdata = repo_tool_dir / "auto_nid_wire_testdata" / "synthetic.log"
    _assert(testdata.is_file(), f"missing {testdata}")
    table = parse_log_text(testdata.read_text(encoding="utf-8"), "synthetic")

    a = table[0xA8AFA7D4]
    _assert(a.hits == 12 and a.count_complete, f"summary should win: {a}")
    _assert(a.lib == "sceNp", a)
    _assert(a.first.lr == 0x00037920, a)

    b = table[0x0D0C2F0C]
    _assert(b.hits == 3 and b.count_complete, f"running counter: {b}")
    _assert(b.first.lr == 0x005C9B84, b)
    _assert(b.first.regs.get("r4") == 1, b.first.regs)

    c = table[0xC044FAB1]
    _assert(c.hits == 1 and not c.count_complete, f"first-hit incomplete: {c}")
    _assert(c.first.lr == 0x005C9B3C, c)
    _assert(c.fake.startswith("CELL_OK"), c.fake)

    d = table[0x11111111]
    _assert(d.hits == 3 and d.count_complete, f"line-count: {d}")

    e = table[0x28B4E2C1]
    _assert(e.hits == 1 and not e.count_complete, e)

    order = [r.nid for r in ranked(table)]
    _assert(order[0] == 0xA8AFA7D4, f"rank {order}")
    _assert(set(order[:3]) == {0xA8AFA7D4, 0x0D0C2F0C, 0x11111111}, order)

    candidates = [name for _lib, name in VERIFIED_NAMES.values()]
    for nid in SIX_SAIL_PAMF:
        hit = resolve_name(nid, candidates, nids_map=None)
        _assert(hit.verified and hit.name == VERIFIED_NAMES[nid][1], hit)
        _assert(hit.lib == VERIFIED_NAMES[nid][0], hit)

    mystery_nid = compute_nid("cellRescSetWaitFlip")
    fake_ok = {mystery_nid: "cellRescSetWaitFlip"}
    hit = resolve_name(mystery_nid, candidates, fake_ok)
    _assert(hit.verified and hit.source.startswith("nids.txt"), hit)
    hit_bad = resolve_name(0xDEADBEEF, candidates, {0xDEADBEEF: "thisNameWillNotHashToDeadBeef"})
    _assert(not hit_bad.verified and "MISMATCH" in hit_bad.source, hit_bad)

    psl_cands = [Path(x) for x in os.environ.get("SF_PSL1GHT", "").split(os.pathsep) if x]
    psl_cands.extend(DEFAULT_PSL1GHT_CANDIDATES)
    psl = first_existing(psl_cands)
    if psl is None:
        print("self-test: skip PSL1GHT header checks (set SF_PSL1GHT to your PSL1GHT checkout)")
        print("self-test: synthetic log + NID resolve checks passed")
        return 0
    idx = HeaderIndex()
    added = idx.add_root(psl, "PSL1GHT")
    _assert(added > 50, f"too few PSL1GHT decls: {added}")

    g = idx.find("sysGameGetParamInt")
    _assert(g is not None, "sysGameGetParamInt missing")
    _assert(len(g.params) == 2, g.params)
    _assert(g.params[0].direction == "input" and g.params[0].confidence == "KNOWN", g.params[0])
    _assert(g.params[1].is_pointer and g.params[1].direction == "output", g.params[1])
    _assert(g.params[1].confidence == "ASSUMED", g.params[1])

    boot = idx.find("sysGameBootCheck")
    _assert(boot is not None, "sysGameBootCheck missing")
    _assert(all(p.is_pointer and p.direction == "output" for p in boot.params), boot.params)
    _assert(all(p.confidence == "ASSUMED" for p in boot.params), boot.params)

    st = idx.find("sysGameSetParamString")
    _assert(st is not None, st)
    _assert(st.params[1].is_const and st.params[1].direction == "input", st.params[1])
    _assert(st.params[1].confidence == "KNOWN", st.params[1])

    data = idx.find("sysGameDataCheck")
    _assert(data is not None, data)
    _assert(data.params[1].is_const and data.params[1].direction == "input"
            and data.params[1].confidence == "KNOWN", data.params[1])
    _assert(data.params[2].direction == "output" and data.params[2].confidence == "ASSUMED",
            data.params[2])

    for nid in SIX_SAIL_PAMF:
        nm = VERIFIED_NAMES[nid][1]
        _assert(idx.find(nm) is None, f"{nm} unexpectedly in PSL1GHT")

    rpcs3 = first_existing(DEFAULT_RPCS3_CANDIDATES)
    for nid in SIX_SAIL_PAMF:
        if nid not in table:
            rec = UnresolvedHit(nid=nid, hits=0, count_complete=False)
            rec.lib = VERIFIED_NAMES[nid][0]
            rec.finalize()
            table[nid] = rec

    results = run_pipeline(table, candidates, nids_map=None, psl1ght_index=idx,
                           fallback_index=None, rpcs3_root=rpcs3)
    by_nid = {r.nid: r for r in results}
    for nid in SIX_SAIL_PAMF:
        r = by_nid[nid]
        _assert(r.name.verified, r.name)
        _assert(r.proto.found or r.proto.source_kind == "assumed-heuristic", r.proto)
        _assert(r.proto.source_kind != "PSL1GHT", r.proto.source_kind)
        _assert("Do not copy" in r.skeleton or "No GPL" in r.skeleton, "banner")
        _assert("CELL_OK" in r.skeleton, r.skeleton)
        _assert("TODO" in r.skeleton or "RPCS3" in r.skeleton, r.skeleton)
        if r.name.name in ASSUMED_PROTOS:
            _assert(r.proto.source_kind == "assumed-heuristic", r.proto)
            _assert(r.name.name in r.skeleton, r.skeleton[:200])

    pamf = by_nid[0x28B4E2C1]
    _assert(any(p.name == "pSelf" and p.direction == "in-out" for p in pamf.proto.params),
            pamf.proto.params)
    _assert("do not zero the object" in pamf.skeleton, pamf.skeleton)

    avi = by_nid[0xDDEBD2A5]
    stream = [p for p in avi.proto.params if p.name == "pStream"]
    _assert(stream and stream[0].direction == "output", avi.proto.params)
    _assert("vm_write32(pStream, 0)" in avi.skeleton, avi.skeleton)

    paused = by_nid[0xD1D55A90]
    _assert(paused.proto.params[1].name == "paused" and not paused.proto.params[1].is_pointer,
            paused.proto.params)
    _assert("cellSail.cpp:1009" in paused.note, paused.note)

    extra = UnresolvedHit(nid=compute_nid("sysGameGetParamInt"), hits=1, count_complete=True)
    extra.finalize()
    results2 = run_pipeline({extra.nid: extra}, ["sysGameGetParamInt"], None, idx, None, None)
    r2 = results2[0]
    _assert(r2.proto.source_kind == "PSL1GHT", r2.proto)
    _assert("vm_write32(value, 0)" in r2.skeleton, r2.skeleton)
    _assert("KNOWN" in r2.skeleton and "ASSUMED" in r2.skeleton, r2.skeleton)

    out_dir = Path("/tmp/auto_nid_wire_selftest")
    if out_dir.exists():
        for p in out_dir.iterdir():
            if p.is_file():
                p.unlink()
    write_outputs(results, out_dir)
    for fn in ("skeletons.c", "register.inc", "checklist.md",
               "report.json", "unresolved_ranked.txt"):
        _assert((out_dir / fn).is_file() and (out_dir / fn).stat().st_size > 0, fn)
    check = (out_dir / "checklist.md").read_text(encoding="utf-8")
    _assert("cellSailDescriptorClose" in check, "checklist names")
    _assert("same call" in check.lower(), check[:200])
    _assert("RPCS3" in check, "checklist mentions RPCS3")
    reg = (out_dir / "register.inc").read_text(encoding="utf-8")
    _assert("ps3_hle_register_ctx" in reg and "cellSailDescriptorClose[skel]" in reg, reg)

    sample = {
        "unresolved_nids": ["0xC044FAB1", "0x0D0C2F0C"],
        "unresolved_ctx": {"0xC044FAB1": "0x005C9B3C", "0x0D0C2F0C": "0x005C9B84"},
    }
    tmpj = Path("/tmp/auto_nid_wire_findings.json")
    tmpj.write_text(json.dumps(sample), encoding="utf-8")
    fj = parse_findings_json(tmpj)
    _assert(fj[0xC044FAB1].first.lr == 0x005C9B3C, fj)
    _assert(fj[0xC044FAB1].hits == 1 and not fj[0xC044FAB1].count_complete, fj)

    print("self-test: OK")
    print(f"  PSL1GHT decls indexed: {added}  root={psl}")
    print("  six sail/pamf names resolved by SHA-1, prototypes ASSUMED (not in PSL1GHT)")
    print(f"  outputs written to {out_dir}")
    return 0

def build_candidates(args: argparse.Namespace, psl1ght: Path | None,
                     extra_roots: list[Path]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()

    def add(seq: Iterable[str]) -> None:
        for n in seq:
            if n and n not in seen:
                seen.add(n)
                names.append(n)

    add(name for _lib, name in VERIFIED_NAMES.values())
    if args.names:
        add(load_name_list([Path(p) for p in args.names]))
    if psl1ght:
        add(harvest_header_names([psl1ght]))
    add(harvest_header_names(extra_roots))
    if args.ps3recomp:
        db = Path(args.ps3recomp) / "tools" / "nid_database.py"
        if db.is_file():
            sys.path.insert(0, str(db.parent))
            try:
                import nid_database as ndb  # type: ignore
                if hasattr(ndb, "_BUILTIN_FUNCTIONS"):
                    add(fn for _mod, fn in ndb._BUILTIN_FUNCTIONS)
            except Exception as exc:
                print(f"warning: could not import nid_database.py: {exc}", file=sys.stderr)
    return names


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Prototype HLE auto-wire helper for ps3recomp. "
                    "Skeletons are not implementations."
    )
    ap.add_argument("--log", action="append", default=[],
                    help="Runtime log, findings.json, or import list. Repeatable.")
    ap.add_argument("--nids", default="",
                    help="Comma-separated NIDs to include even if absent from the log.")
    ap.add_argument("--names", action="append", default=[],
                    help="Candidate name list (one name per line, or '0xNID name').")
    ap.add_argument("--nids-txt", default="",
                    help="Path to zecoxao/sce_symbols nids.txt (lookup only, not vendored).")
    ap.add_argument("--psl1ght", default="",
                    help="Path to a PSL1GHT checkout (ppu/include).")
    ap.add_argument("--fetch-psl1ght", action="store_true",
                    help="git clone ps3dev/PSL1GHT into tools/_cache if missing.")
    ap.add_argument("--extra-headers", action="append", default=[],
                    help="Extra header roots (e.g. ps3recomp/libs). Second-choice prototypes.")
    ap.add_argument("--ps3recomp", default="",
                    help="ps3recomp root (nid_database.py + optional libs headers).")
    ap.add_argument("--rpcs3", default="",
                    help="RPCS3 source root, used only to cite file:line and classify stubs.")
    ap.add_argument("--out", default="",
                    help="Output directory for skeletons.c, register.inc, checklist.md, report.json.")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--print-log-format", action="store_true",
                    help="Print the preferred Salem log format and exit.")
    args = ap.parse_args(argv)

    if args.print_log_format:
        print(__doc__)
        return 0

    tool_dir = Path(__file__).resolve().parent
    if args.self_test:
        return run_self_test(tool_dir)

    if not args.log and not args.nids:
        ap.error("pass --log and/or --nids (or --self-test)")

    verify_builtin_names()

    table: dict[int, UnresolvedHit] = {}
    for log in args.log:
        merge_hits(table, parse_input_path(Path(log)))
    if args.nids:
        for part in args.nids.split(","):
            part = part.strip()
            if not part:
                continue
            nid = parse_nid(part)
            if nid not in table:
                rec = UnresolvedHit(nid=nid)
                rec.finalize()
                table[nid] = rec

    psl1ght = first_existing(
        [Path(args.psl1ght) if args.psl1ght else None] + DEFAULT_PSL1GHT_CANDIDATES
    )
    if args.fetch_psl1ght and (psl1ght is None or not (psl1ght / "ppu" / "include").is_dir()):
        psl1ght = fetch_psl1ght(tool_dir / "_cache" / "PSL1GHT")
    if psl1ght is None:
        print("warning: no PSL1GHT tree found; prototypes will be missing/ASSUMED. "
              "Pass --psl1ght or --fetch-psl1ght.", file=sys.stderr)

    ps3recomp = first_existing(
        [Path(args.ps3recomp) if args.ps3recomp else None] + DEFAULT_PS3RECOMP_CANDIDATES
    )
    extra_roots = [Path(p) for p in args.extra_headers]
    if ps3recomp and (ps3recomp / "libs").is_dir():
        extra_roots.append(ps3recomp / "libs")
    if args.ps3recomp:
        extra_roots.append(Path(args.ps3recomp))

    nids_path = first_existing(
        [Path(args.nids_txt) if args.nids_txt else None] + DEFAULT_NIDS_TXT_CANDIDATES
    )
    nids_map = load_nids_txt(nids_path) if nids_path else None
    if nids_path:
        print(f"nids.txt lookup: {nids_path} ({len(nids_map or {})} entries) — "
              "lookup only, not copied into the output.", file=sys.stderr)

    candidates = build_candidates(
        argparse.Namespace(
            names=args.names,
            ps3recomp=str(ps3recomp) if ps3recomp else args.ps3recomp,
        ),
        psl1ght,
        extra_roots,
    )

    psl_index = HeaderIndex()
    if psl1ght:
        n = psl_index.add_root(psl1ght, "PSL1GHT")
        print(f"PSL1GHT index: {n} declarations from {psl1ght}", file=sys.stderr)
    fb = HeaderIndex()
    for root in extra_roots:
        kind = "ps3recomp-header" if "ps3recomp" in str(root) else "extra-header"
        fb.add_root(root, kind)

    rpcs3 = first_existing(
        [Path(args.rpcs3) if args.rpcs3 else None] + DEFAULT_RPCS3_CANDIDATES
    )

    results = run_pipeline(table, candidates, nids_map, psl_index, fb, rpcs3)

    out_dir = Path(args.out) if args.out else Path.cwd() / "auto_nid_wire_out"
    write_outputs(results, out_dir)

    print(f"wired {len(results)} NID(s) -> {out_dir}")
    unnamed = [r for r in results if not r.name.name]
    assumed = [r for r in results if r.proto.source_kind == "assumed-heuristic"]
    missing = [r for r in results if not r.proto.found]
    print(f"  named={len(results) - len(unnamed)}  unnamed={len(unnamed)}  "
          f"PSL1GHT proto={sum(1 for r in results if r.proto.source_kind == 'PSL1GHT')}  "
          f"assumed proto={len(assumed)}  no proto={len(missing)}")
    print("  ranked:")
    for r in results:
        flag = "" if r.hit.count_complete else "  (count incomplete)"
        print(f"    {fmt_nid(r.nid)}  hits={r.hit.hits:<6}  "
              f"{r.name.name or '?':48}  {r.name.source}{flag}")
    print("Skeletons are not implementations. Do not claim this ran on Saud's build.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
