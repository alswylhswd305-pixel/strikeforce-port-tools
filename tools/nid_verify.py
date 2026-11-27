#!/usr/bin/env python3
"""Verify PS3 NIDs: nid = little-endian u32 of SHA-1(name + fixed suffix)[:4].
Usage: nid_verify.py 0xNID=name [...]   (lookup-only helper; no external data bundled)"""
import hashlib, struct, sys
SUF = bytes.fromhex('6759659904250490566427499489741A')
def nid(name): return struct.unpack('<I', hashlib.sha1(name.encode() + SUF).digest()[:4])[0]
ok = True
for a in sys.argv[1:]:
    v, n = a.split('=', 1); good = nid(n) == int(v, 16); ok &= good
    print(f"{v} {n} {'OK' if good else 'MISMATCH (computed 0x%08X)' % nid(n)}")
sys.exit(0 if ok else 1)
