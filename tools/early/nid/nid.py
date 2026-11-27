#!/usr/bin/env python3
"""PS3 function NID helper (stdlib only).

NID = first 4 bytes, read little-endian, of SHA-1(function_name + 16-byte suffix
6759659904250490566427499489741A). This is the scheme RPCS3 uses
(rpcs3/Emu/Cell/PPUModule.cpp). ps3recomp's docs/NID_SYSTEM.md (v0.20.0) describes
an older/incorrect variant; trust this one.

Self-check (run with no args):  cellSysmoduleLoadModule -> 0x32267A31,
                                UCS2stoUTF8s            -> 0x2AD091C6

  python nid.py                         self-test
  python nid.py name NAME [NAME ...]    print NIDs for names
  python nid.py resolve LIST SRC_DIR... resolve '? ' entries of an unbound-imports list
                                        by hashing every identifier found in SRC_DIR
                                        (e.g. a local RPCS3 checkout's rpcs3/Emu/Cell/Modules)
"""
import hashlib, os, re, struct, sys

SUFFIX = bytes.fromhex("6759659904250490566427499489741A")

def nid(name: str) -> int:
    return struct.unpack("<I", hashlib.sha1(name.encode() + SUFFIX).digest()[:4])[0]

def selftest():
    for n, want in (("cellSysmoduleLoadModule", 0x32267A31), ("UCS2stoUTF8s", 0x2AD091C6)):
        got = nid(n); print("%-26s 0x%08X %s" % (n, got, "OK" if got == want else "MISMATCH (want 0x%08X)" % want))

def resolve(listfile, dirs):
    tab = {}
    for d in dirs:
        for root, _, files in os.walk(d):
            for fn in files:
                if fn.endswith((".c", ".cpp", ".h", ".hpp")):
                    for ident in set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\b", open(os.path.join(root, fn), errors="ignore").read())):
                        tab.setdefault(nid(ident), ident)
    for line in open(listfile, encoding="utf-8-sig", errors="ignore"):
        m = re.match(r"(\S+)\s+0x([0-9A-Fa-f]{8})\s+\?(.*)", line)
        if m: print("%-18s 0x%s %-44s%s" % (m.group(1), m.group(2).upper(), tab.get(int(m.group(2), 16), "?"), m.group(3)))
        else: print(line.rstrip())

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: selftest()
    elif a[0] == "name": [print("%-40s 0x%08X" % (n, nid(n))) for n in a[1:]]
    elif a[0] == "resolve" and len(a) >= 3: resolve(a[1], a[2:])
    else: print(__doc__)
